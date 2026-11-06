//! Transcript storage is local, exclusive, byte preserving, and never executable.
use minifycli::{minify, select_matcher, Matcher};
use std::ffi::OsString;
use std::fs;
use std::io::{self, Write};
use std::path::PathBuf;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

#[path = "../src/recording.rs"]
mod recording;
use recording::{load_replay, Metadata, Record, Stream, TeeWriter};

static NEXT: AtomicUsize = AtomicUsize::new(0);

struct Workspace(PathBuf);
impl Workspace {
    fn new() -> Self {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let path = std::env::temp_dir().join(format!(
            "minifycli-recording-{}-{nonce}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&path).unwrap();
        Self(path)
    }
    fn record(&self) -> PathBuf {
        self.0.join("capture")
    }
}
impl Drop for Workspace {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn metadata(command: &[&str], exit_code: i32) -> Metadata {
    let command = command.iter().map(OsString::from).collect::<Vec<_>>();
    Metadata {
        matcher: select_matcher(&command),
        command,
        exit_code,
        failed: exit_code != 0,
        cancelled: false,
        spilled: [false; 2],
        max_line_chars: None,
        complete: true,
    }
}

fn save(workspace: &Workspace, metadata: Metadata, stdout: &[u8], stderr: &[u8]) {
    let mut record = Record::create(&workspace.record()).unwrap();
    record
        .take_raw(Stream::Stdout)
        .unwrap()
        .write_all(stdout)
        .unwrap();
    record
        .take_raw(Stream::Stderr)
        .unwrap()
        .write_all(stderr)
        .unwrap();
    record
        .take_filtered(Stream::Stdout)
        .unwrap()
        .write_all(stdout)
        .unwrap();
    record
        .take_filtered(Stream::Stderr)
        .unwrap()
        .write_all(stderr)
        .unwrap();
    record.finish(metadata).unwrap();
}

#[test]
fn record_is_exclusive_and_private() {
    let workspace = Workspace::new();
    let mut record = Record::create(&workspace.record()).unwrap();
    assert_eq!(
        Record::create(&workspace.record()).err().unwrap().kind(),
        io::ErrorKind::AlreadyExists
    );
    record.take_raw(Stream::Stdout).unwrap();
    assert!(record.take_raw(Stream::Stdout).is_err());
    assert!(!workspace.record().join("metadata.json").exists());
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        assert_eq!(
            fs::metadata(workspace.record())
                .unwrap()
                .permissions()
                .mode()
                & 0o077,
            0
        );
        for name in [
            "stdout.raw",
            "stderr.raw",
            "stdout.filtered",
            "stderr.filtered",
        ] {
            assert_eq!(
                fs::metadata(workspace.record().join(name))
                    .unwrap()
                    .permissions()
                    .mode()
                    & 0o077,
                0
            );
        }
    }
}

#[test]
fn replay_preserves_binary_streams_literal_argv_and_exit_status_without_execution() {
    let workspace = Workspace::new();
    let marker = workspace.0.join("must-not-exist");
    let command = vec![
        OsString::from("not-an-executable"),
        OsString::from(format!("$(touch {})", marker.display())),
        OsString::from(""),
    ];
    let mut meta = metadata(&["unused"], 37);
    meta.command = command.clone();
    meta.matcher = Matcher::Passthrough;
    let stdout = b"binary\0\xff\xfe\n";
    let stderr = b"diagnostic\0without newline";
    save(&workspace, meta, stdout, stderr);
    let replay = load_replay(&workspace.record(), 1024).unwrap();
    assert_eq!(replay.command, command);
    assert_eq!(replay.exit_code, 37);
    assert!(replay.failed);
    assert_eq!(replay.matcher, Matcher::Passthrough);
    assert_eq!(replay.render(), [stdout.to_vec(), stderr.to_vec()]);
    assert!(!marker.exists());
}

#[test]
fn replay_uses_current_filter_and_preserves_failure_suffix() {
    let workspace = Workspace::new();
    let tail = b"test broken ... FAILED\nfailures:\nthread 'broken' panicked at src/lib.rs:2:3:\nuseful diagnostic\ntest result: FAILED. 1 passed; 1 failed\n";
    let mut stdout = b"running 2 tests\ntest good ... ok\n".to_vec();
    stdout.extend_from_slice(tail);
    save(
        &workspace,
        metadata(&["cargo", "test"], 101),
        &stdout,
        b"stderr diagnostic\n",
    );
    let replay = load_replay(&workspace.record(), 4096).unwrap();
    let [output, errors] = replay.render();
    assert_eq!(replay.exit_code, 101);
    assert!(output.ends_with(tail));
    assert!(!String::from_utf8_lossy(&output).contains("test good ... ok"));
    assert_eq!(errors, b"stderr diagnostic\n");
}

#[cfg(unix)]
#[test]
fn unix_argv_round_trips_invalid_utf8_quotes_and_newlines() {
    use std::os::unix::ffi::{OsStrExt, OsStringExt};
    let workspace = Workspace::new();
    let mut meta = metadata(&["tool"], 0);
    let original = OsString::from_vec(b"quotes\"\\new\nline\xff".to_vec());
    meta.command.push(original.clone());
    save(&workspace, meta, b"", b"");
    let replay = load_replay(&workspace.record(), 1).unwrap();
    assert_eq!(
        replay.command[1].as_os_str().as_bytes(),
        original.as_os_str().as_bytes()
    );
    let text = fs::read_to_string(workspace.record().join("metadata.json")).unwrap();
    assert!(text.contains("\"argv_encoding\": \"unix-bytes-hex\""));
    assert!(!text.contains("quotes"));
}

#[test]
fn incomplete_cancelled_and_spilled_records_are_not_replayed() {
    for case in 0..4 {
        let workspace = Workspace::new();
        if case == 0 {
            Record::create(&workspace.record()).unwrap();
        } else {
            let mut meta = metadata(&["cargo", "test"], 0);
            match case {
                1 => meta.complete = false,
                2 => meta.cancelled = true,
                3 => meta.spilled[0] = true,
                _ => unreachable!(),
            }
            save(&workspace, meta, b"unfiltered", b"");
        }
        assert!(load_replay(&workspace.record(), 1024).is_err());
    }
}

#[test]
fn replay_checks_all_file_lengths_and_enforces_memory_limit() {
    let workspace = Workspace::new();
    save(&workspace, metadata(&["echo"], 0), b"four", b"");
    assert!(load_replay(&workspace.record(), 3).is_err());
    assert_eq!(
        load_replay(&workspace.record(), usize::MAX).unwrap().stdout,
        b"four"
    );
    fs::write(workspace.record().join("stderr.filtered"), b"changed").unwrap();
    assert!(load_replay(&workspace.record(), 1024).is_err());
}

#[test]
fn malformed_duplicate_unknown_and_oversized_metadata_fail_closed() {
    let workspace = Workspace::new();
    save(&workspace, metadata(&["echo"], 0), b"", b"");
    let path = workspace.record().join("metadata.json");
    let original = fs::read_to_string(&path).unwrap();
    let variants = [
        original.replace("\"schema_version\": 1", "\"schema_version\": 2"),
        original.replace(
            "\"failed\": false",
            "\"failed\": false,\n  \"failed\": false",
        ),
        original.replace("\"failed\": false", "\"unknown\": false"),
        original.replace("\"complete\": true", "\"complete\": true,"),
        original.replace("\"exit_code\": 0", "\"exit_code\": +0"),
        original.replace("\"failed\": false", "\"failed\": true"),
        "x".repeat(70_000),
    ];
    for text in variants {
        fs::write(&path, text).unwrap();
        assert!(load_replay(&workspace.record(), 1024).is_err());
    }
}

#[test]
fn finishing_never_replaces_an_existing_completion_marker() {
    let workspace = Workspace::new();
    let record = Record::create(&workspace.record()).unwrap();
    let marker = workspace.record().join("metadata.json");
    fs::write(&marker, b"must remain unchanged").unwrap();
    assert_eq!(
        record.finish(metadata(&["echo"], 0)).unwrap_err().kind(),
        io::ErrorKind::AlreadyExists
    );
    assert_eq!(fs::read(marker).unwrap(), b"must remain unchanged");
}

#[cfg(unix)]
#[test]
fn replay_rejects_symlink_directories_and_streams() {
    use std::os::unix::fs::symlink;
    let workspace = Workspace::new();
    save(&workspace, metadata(&["echo"], 0), b"bytes", b"");
    let alias = workspace.0.join("alias");
    symlink(workspace.record(), &alias).unwrap();
    assert!(load_replay(&alias, 1024).is_err());
    let stream = workspace.record().join("stdout.raw");
    fs::rename(&stream, workspace.0.join("outside")).unwrap();
    symlink(workspace.0.join("outside"), stream).unwrap();
    assert!(load_replay(&workspace.record(), 1024).is_err());
}

struct PartialWriter(Vec<u8>);
impl Write for PartialWriter {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        let count = bytes.len().min(2);
        self.0.extend_from_slice(&bytes[..count]);
        Ok(count)
    }
    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

#[test]
fn tee_records_partial_writes_without_duplication() {
    let workspace = Workspace::new();
    let mut record = Record::create(&workspace.record()).unwrap();
    let mut tee = TeeWriter::new(
        PartialWriter(Vec::new()),
        record.take_filtered(Stream::Stdout).unwrap(),
    );
    tee.write_all(b"one\0two\xff").unwrap();
    tee.flush().unwrap();
    drop(tee);
    record.finish(metadata(&["echo"], 0)).unwrap();
    assert_eq!(
        fs::read(workspace.record().join("stdout.filtered")).unwrap(),
        b"one\0two\xff"
    );
}

#[cfg(unix)]
mod cli {
    use super::*;
    use std::os::unix::fs::PermissionsExt;
    use std::process::{Command, Output};

    fn script(workspace: &Workspace, name: &str, body: &str) -> PathBuf {
        let path = workspace.0.join(name);
        fs::write(&path, format!("#!/bin/sh\nset -eu\n{body}\n")).unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o755)).unwrap();
        path
    }

    fn mini() -> Command {
        Command::new(env!("CARGO_BIN_EXE_mini"))
    }

    fn assert_status(output: &Output, expected: i32) {
        assert_eq!(
            output.status.code(),
            Some(expected),
            "{}",
            String::from_utf8_lossy(&output.stderr)
        );
    }

    #[test]
    fn cli_records_one_execution_and_replays_deleted_executable_with_original_failure_status() {
        let workspace = Workspace::new();
        let marker = workspace.0.join("must-not-exist");
        let argv_log = workspace.0.join("arguments.log");
        let cargo = script(&workspace, "cargo", "printf '<%s>\\n' \"$@\" > \"$MINI_TEST_ARGV\"\ncat \"$MINI_TEST_OUT\"\ncat \"$MINI_TEST_ERR\" >&2\nexit 101");
        let stdout = b"running 2 tests\ntest good ... ok\ntest broken ... FAILED\nfailures:\nthread 'broken' panicked at src/lib.rs:4:5:\nkeep this diagnostic\ntest result: FAILED. 1 passed; 1 failed\n";
        let stderr = b"original stderr without a newline";
        let out_path = workspace.0.join("original.stdout");
        let err_path = workspace.0.join("original.stderr");
        fs::write(&out_path, stdout).unwrap();
        fs::write(&err_path, stderr).unwrap();
        let literal = format!("$(touch {})", marker.display());
        let output = mini()
            .arg("--stats")
            .arg("--record")
            .arg(workspace.record())
            .arg(&cargo)
            .args(["test", "arg with spaces", literal.as_str(), ""])
            .env("MINI_TEST_ARGV", &argv_log)
            .env("MINI_TEST_OUT", out_path)
            .env("MINI_TEST_ERR", err_path)
            .output()
            .unwrap();
        assert_status(&output, 101);
        let expected = minify(stdout, Matcher::Cargo, true, None);
        assert_eq!(output.stdout, expected);
        assert!(output.stderr.starts_with(stderr));
        assert!(String::from_utf8_lossy(&output.stderr).contains("[mini] matcher=cargo"));
        assert_eq!(
            fs::read(workspace.record().join("stdout.raw")).unwrap(),
            stdout
        );
        assert_eq!(
            fs::read(workspace.record().join("stderr.raw")).unwrap(),
            stderr
        );
        assert_eq!(
            fs::read(workspace.record().join("stdout.filtered")).unwrap(),
            expected
        );
        assert_eq!(
            fs::read(workspace.record().join("stderr.filtered")).unwrap(),
            stderr
        );
        assert_eq!(
            fs::read_to_string(argv_log).unwrap(),
            format!("<test>\n<arg with spaces>\n<{literal}>\n<>\n")
        );
        assert!(!marker.exists());
        let capture = load_replay(&workspace.record(), 4096).unwrap();
        assert_eq!(
            capture.command,
            [
                cargo.as_os_str().to_os_string(),
                OsString::from("test"),
                OsString::from("arg with spaces"),
                OsString::from(&literal),
                OsString::from("")
            ]
        );
        fs::remove_file(cargo).unwrap();
        let replay = mini()
            .arg("--replay")
            .arg(workspace.record())
            .output()
            .unwrap();
        assert_status(&replay, 101);
        assert_eq!(replay.stdout, expected);
        assert_eq!(replay.stderr, stderr);
        let replay_with_stats = mini()
            .arg("--replay")
            .arg(workspace.record())
            .arg("--stats")
            .output()
            .unwrap();
        assert_status(&replay_with_stats, 101);
        assert_eq!(replay_with_stats.stdout, expected);
        assert!(replay_with_stats.stderr.starts_with(stderr));
        assert!(String::from_utf8_lossy(&replay_with_stats.stderr)
            .contains("[mini] replay matcher=cargo recorded_matcher=cargo"));
    }

    #[test]
    fn cli_records_unknown_binary_output_byte_for_byte() {
        let workspace = Workspace::new();
        let program = script(
            &workspace,
            "unknown-tool",
            "cat \"$MINI_TEST_OUT\"\ncat \"$MINI_TEST_ERR\" >&2\nexit 37",
        );
        let stdout = b"binary stdout\0\xff\xfe\n";
        let stderr = b"binary stderr\0\xfe";
        let out_path = workspace.0.join("source.stdout");
        let err_path = workspace.0.join("source.stderr");
        fs::write(&out_path, stdout).unwrap();
        fs::write(&err_path, stderr).unwrap();
        let output = mini()
            .arg("--record")
            .arg(workspace.record())
            .arg(&program)
            .env("MINI_TEST_OUT", out_path)
            .env("MINI_TEST_ERR", err_path)
            .output()
            .unwrap();
        assert_status(&output, 37);
        assert_eq!(output.stdout, stdout);
        assert_eq!(output.stderr, stderr);
        let captured = load_replay(&workspace.record(), 4096).unwrap();
        assert_eq!(captured.matcher, Matcher::Passthrough);
        assert_eq!(captured.stdout, stdout);
        assert_eq!(captured.stderr, stderr);
        fs::remove_file(program).unwrap();
        let replay = mini()
            .arg("--replay")
            .arg(workspace.record())
            .output()
            .unwrap();
        assert_status(&replay, 37);
        assert_eq!(replay.stdout, stdout);
        assert_eq!(replay.stderr, stderr);
    }

    #[test]
    fn cli_rejects_conflicts_and_existing_directories_before_executing() {
        let workspace = Workspace::new();
        let marker = workspace.0.join("executed");
        let program = script(
            &workspace,
            "unknown-tool",
            "printf executed > \"$MINI_TEST_MARKER\"",
        );
        fs::create_dir(workspace.record()).unwrap();
        let sentinel = workspace.record().join("keep.txt");
        fs::write(&sentinel, b"unchanged").unwrap();
        let existing = mini()
            .arg("--record")
            .arg(workspace.record())
            .arg(&program)
            .env("MINI_TEST_MARKER", &marker)
            .output()
            .unwrap();
        assert_status(&existing, 1);
        assert!(!marker.exists());
        assert_eq!(fs::read(sentinel).unwrap(), b"unchanged");
        let new_path = workspace.0.join("must-not-be-created");
        let raw = mini()
            .arg("--raw")
            .arg("--record")
            .arg(&new_path)
            .arg(&program)
            .env("MINI_TEST_MARKER", &marker)
            .output()
            .unwrap();
        assert_status(&raw, 2);
        assert!(!new_path.exists());
        for extra in [
            vec!["--raw"],
            vec!["--max-line-chars", "10"],
            vec!["echo", "must-not-run"],
        ] {
            let output = mini()
                .arg("--replay")
                .arg(workspace.record())
                .args(extra)
                .output()
                .unwrap();
            assert_status(&output, 2);
        }
        assert!(!marker.exists());
    }

    #[test]
    fn cli_spilled_record_keeps_original_bytes_and_cannot_be_replayed() {
        let workspace = Workspace::new();
        let cargo = script(&workspace, "cargo", "cat \"$MINI_TEST_OUT\"");
        let stdout = format!(
            "running 1 test\ntest good ... ok\n{}\ntest result: ok. 1 passed; 0 failed\n",
            "long application log ".repeat(100)
        );
        let source = workspace.0.join("source.stdout");
        fs::write(&source, stdout.as_bytes()).unwrap();
        let output = mini()
            .arg("--record")
            .arg(workspace.record())
            .args(["--stats", "--max-buffer", "32"])
            .arg(cargo)
            .arg("test")
            .env("MINI_TEST_OUT", source)
            .output()
            .unwrap();
        assert_status(&output, 0);
        assert_eq!(output.stdout, stdout.as_bytes());
        assert_eq!(
            fs::read(workspace.record().join("stdout.raw")).unwrap(),
            stdout.as_bytes()
        );
        assert_eq!(
            fs::read(workspace.record().join("stdout.filtered")).unwrap(),
            stdout.as_bytes()
        );
        assert!(fs::read(workspace.record().join("stderr.filtered"))
            .unwrap()
            .is_empty());
        let metadata = fs::read_to_string(workspace.record().join("metadata.json")).unwrap();
        assert!(metadata.contains("\"complete\": false"));
        assert!(metadata.contains("\"stdout_spilled\": true"));
        let replay = mini()
            .arg("--replay")
            .arg(workspace.record())
            .output()
            .unwrap();
        assert_status(&replay, 1);
        assert!(replay.stdout.is_empty());
        assert!(
            String::from_utf8_lossy(&replay.stderr).contains("spilled record cannot be replayed")
        );
    }

    #[cfg(any(target_os = "macos", target_os = "linux"))]
    #[test]
    fn cli_cancelled_record_is_incomplete_and_replay_is_refused() {
        use std::process::{Child, Stdio};
        use std::thread;
        use std::time::{Duration, Instant};
        extern "C" {
            fn kill(pid: i32, number: i32) -> i32;
        }
        struct Guard {
            child: Option<Child>,
            pid_path: PathBuf,
        }
        impl Drop for Guard {
            fn drop(&mut self) {
                if let Ok(value) = fs::read_to_string(&self.pid_path) {
                    if let Ok(pid) = value.parse::<i32>() {
                        if pid > 1 {
                            unsafe {
                                kill(-pid, 9);
                            }
                        }
                    }
                }
                if let Some(child) = self.child.as_mut() {
                    let _ = child.kill();
                    let _ = child.wait();
                }
            }
        }
        let workspace = Workspace::new();
        let cargo = script(&workspace, "cargo", "trap 'exit 0' TERM\nprintf '%s' \"$$\" > \"$MINI_TEST_PID\"\nprintf 'running 1 test\\ntest retained_on_cancel ... ok\\ntest result: ok. 1 passed; 0 failed\\n'\nprintf ready > \"$MINI_TEST_READY\"\nwhile :; do sleep 1; done");
        let pid_path = workspace.0.join("child.pid");
        let ready = workspace.0.join("child.ready");
        let child = mini()
            .arg("--record")
            .arg(workspace.record())
            .arg(cargo)
            .arg("test")
            .env("MINI_TEST_PID", &pid_path)
            .env("MINI_TEST_READY", &ready)
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap();
        let mut guard = Guard {
            child: Some(child),
            pid_path,
        };
        let startup = Instant::now() + Duration::from_secs(30);
        while !ready.exists() {
            assert!(guard.child.as_mut().unwrap().try_wait().unwrap().is_none());
            assert!(
                Instant::now() < startup,
                "recording fixture startup timed out"
            );
            thread::sleep(Duration::from_millis(10));
        }
        let child = guard.child.as_mut().unwrap();
        assert_eq!(unsafe { kill(i32::try_from(child.id()).unwrap(), 15) }, 0);
        let deadline = Instant::now() + Duration::from_secs(4);
        while child.try_wait().unwrap().is_none() {
            assert!(
                Instant::now() < deadline,
                "recording cancellation exceeded deadline"
            );
            thread::sleep(Duration::from_millis(10));
        }
        let output = guard.child.take().unwrap().wait_with_output().unwrap();
        assert_status(&output, 143);
        assert!(String::from_utf8_lossy(&output.stdout).contains("test retained_on_cancel ... ok"));
        let metadata = fs::read_to_string(workspace.record().join("metadata.json")).unwrap();
        assert!(metadata.contains("\"complete\": false"));
        assert!(metadata.contains("\"cancelled\": true"));
        assert_eq!(
            fs::read(workspace.record().join("stdout.raw")).unwrap(),
            output.stdout
        );
        assert_eq!(
            fs::read(workspace.record().join("stdout.filtered")).unwrap(),
            output.stdout
        );
        let replay = mini()
            .arg("--replay")
            .arg(workspace.record())
            .output()
            .unwrap();
        assert_status(&replay, 1);
        assert!(replay.stdout.is_empty());
        assert!(String::from_utf8_lossy(&replay.stderr).contains("cancelled"));
    }
}
