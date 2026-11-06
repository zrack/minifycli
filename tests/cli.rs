#![cfg(unix)]

use std::ffi::OsStr;
use std::fs;
use std::io::Write;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::process::{Command, Output, Stdio};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

static NEXT_DIRECTORY: AtomicUsize = AtomicUsize::new(0);

struct Workspace(PathBuf);

impl Workspace {
    fn new() -> Self {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let id = NEXT_DIRECTORY.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "minifycli-integration-{}-{nonce}-{id}",
            std::process::id()
        ));
        fs::create_dir(&path).unwrap();
        Self(path)
    }

    fn file(&self, name: &str, bytes: &[u8]) -> PathBuf {
        let path = self.0.join(name);
        fs::write(&path, bytes).unwrap();
        path
    }

    fn script(&self, name: &str, body: &str) -> PathBuf {
        let path = self.file(name, format!("#!/bin/sh\nset -eu\n{body}\n").as_bytes());
        fs::set_permissions(&path, fs::Permissions::from_mode(0o755)).unwrap();
        path
    }

    fn emitter(&self, name: &str, stdout: &[u8], stderr: &[u8], exit: i32) -> Command {
        let program = self.script(
            name,
            "cat \"$MINIFYCLI_TEST_OUT\"\ncat \"$MINIFYCLI_TEST_ERR\" >&2\nexit \"$MINIFYCLI_TEST_EXIT\"",
        );
        let stdout_path = self.file("stdout.fixture", stdout);
        let stderr_path = self.file("stderr.fixture", stderr);
        let mut command = mini();
        command
            .env("MINIFYCLI_TEST_OUT", stdout_path)
            .env("MINIFYCLI_TEST_ERR", stderr_path)
            .env("MINIFYCLI_TEST_EXIT", exit.to_string())
            .arg(program);
        command
    }
}

impl Drop for Workspace {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn mini() -> Command {
    Command::new(env!("CARGO_BIN_EXE_mini"))
}

fn code(output: &Output, expected: i32) {
    assert_eq!(
        output.status.code(),
        Some(expected),
        "stderr: {}",
        String::from_utf8_lossy(&output.stderr)
    );
}

#[test]
fn unknown_command_preserves_both_binary_streams_and_exit_code() {
    let workspace = Workspace::new();
    let stdout = b"stdout\0with\xffbytes\n";
    let stderr = b"stderr\xfe\0without final newline";
    let output = workspace
        .emitter("unknown-command", stdout, stderr, 37)
        .output()
        .unwrap();
    code(&output, 37);
    assert_eq!(output.stdout, stdout);
    assert_eq!(output.stderr, stderr);
}

#[test]
fn argv_is_literal_and_options_after_the_command_are_forwarded() {
    let workspace = Workspace::new();
    let program = workspace.script("show-arguments", "printf '<%s>\\n' \"$@\"");
    let marker = workspace.0.join("must-not-exist");
    let substitution = format!("$(touch {})", marker.display());
    let separator = format!("; touch {}", marker.display());
    let arguments = [
        "with spaces",
        "",
        substitution.as_str(),
        separator.as_str(),
        "--help",
        "--version",
        "--stats",
        "--raw",
        "--max-buffer",
        "not-a-number",
    ];
    let output = mini().arg(program).args(arguments).output().unwrap();
    code(&output, 0);
    let expected: String = arguments.iter().map(|arg| format!("<{arg}>\n")).collect();
    assert_eq!(output.stdout, expected.as_bytes());
    assert!(output.stderr.is_empty());
    assert!(
        !marker.exists(),
        "arguments must not be evaluated by a shell"
    );
}

#[test]
fn stdin_working_directory_and_environment_are_inherited() {
    let workspace = Workspace::new();
    let program = workspace.script(
        "read-context",
        "pwd -P\nprintf 'env:%s\\n' \"$MINIFYCLI_CONTEXT_VALUE\"\ncat",
    );
    let mut child = mini()
        .arg(program)
        .current_dir(&workspace.0)
        .env("MINIFYCLI_CONTEXT_VALUE", "spaces and $literal syntax")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    child
        .stdin
        .take()
        .unwrap()
        .write_all(b"input\0payload\n")
        .unwrap();
    let output = child.wait_with_output().unwrap();
    code(&output, 0);
    let physical_directory = workspace.0.canonicalize().unwrap();
    let mut expected = format!(
        "{}\nenv:spaces and $literal syntax\n",
        physical_directory.display()
    )
    .into_bytes();
    expected.extend_from_slice(b"input\0payload\n");
    assert_eq!(output.stdout, expected);
    assert!(output.stderr.is_empty());
}

#[test]
fn raw_bypasses_a_recognized_test_runner() {
    let workspace = Workspace::new();
    let stdout = b"running 1 test\ntest good ... ok\ntest result: ok. 1 passed; 0 failed\n";
    let stderr = b"   Compiling demo v0.1.0\n    Finished `test` profile target(s) in 0.1s\n";
    let emitter = workspace.emitter("cargo", stdout, stderr, 0);
    let output = with_prefix(emitter, &["--raw"])
        .arg("test")
        .output()
        .unwrap();
    code(&output, 0);
    assert_eq!(output.stdout, stdout);
    assert_eq!(output.stderr, stderr);
}

/// Rebuild a Command to place Mini options before an already configured child.
/// Environment values stay scoped to this subprocess; tests never mutate PATH.
fn with_prefix(command: Command, prefix: &[&str]) -> Command {
    let mut rebuilt = Command::new(command.get_program());
    rebuilt.args(prefix).args(command.get_args());
    for (key, value) in command.get_envs() {
        match value {
            Some(value) => {
                rebuilt.env(key, value);
            }
            None => {
                rebuilt.env_remove(key);
            }
        }
    }
    if let Some(directory) = command.get_current_dir() {
        rebuilt.current_dir(directory);
    }
    rebuilt
}

#[test]
fn recognized_test_failure_keeps_traces_summaries_and_status_in_both_streams() {
    let workspace = Workspace::new();
    let failure = "test broken ... FAILED\n\nfailures:\n---- broken stdout ----\nthread 'broken' panicked at src/lib.rs:12:5:\ntest misleading ... ok\nassertion failed: expected == actual\n\ntest result: FAILED. 1 passed; 1 failed; 0 ignored\n";
    let stdout = format!("running 2 tests\ntest good ... ok\n{failure}");
    let stderr = format!("running 2 tests\ntest other_good ... ok\n{failure}");
    let output = workspace
        .emitter("cargo", stdout.as_bytes(), stderr.as_bytes(), 101)
        .arg("test")
        .output()
        .unwrap();
    code(&output, 101);
    assert_eq!(
        output.stdout,
        format!("running 2 tests\n{failure}").as_bytes()
    );
    assert_eq!(
        output.stderr,
        format!("running 2 tests\n{failure}").as_bytes()
    );
}

#[test]
fn buffer_overflow_emits_original_bytes_from_both_streams() {
    let workspace = Workspace::new();
    let mut stdout = b"running 1 test\ntest good ... ok\n".to_vec();
    stdout.extend(vec![b'x'; 200_000]);
    stdout.extend_from_slice(b"\ntest result: ok. 1 passed; 0 failed\n");
    let mut stderr = b"   Compiling demo v0.1.0\n".to_vec();
    stderr.extend(vec![b'y'; 200_000]);
    stderr.extend_from_slice(b"\n    Finished `test` profile target(s) in 0.1s\n");
    let emitter = workspace.emitter("cargo", &stdout, &stderr, 0);
    let output = with_prefix(emitter, &["--max-buffer", "32"])
        .arg("test")
        .output()
        .unwrap();
    code(&output, 0);
    assert_eq!(output.stdout, stdout);
    assert_eq!(output.stderr, stderr);
}

#[test]
fn known_command_binary_and_invalid_utf8_data_stay_exact() {
    for bytes in [
        b"running 1 test\ntest good ... ok\n\0test result: ok. 1 passed\n".as_slice(),
        b"running 1 test\ntest good ... ok\n\xfftest result: ok. 1 passed\n".as_slice(),
    ] {
        let workspace = Workspace::new();
        let output = workspace
            .emitter("cargo", bytes, bytes, 0)
            .arg("test")
            .output()
            .unwrap();
        code(&output, 0);
        assert_eq!(output.stdout, bytes);
        assert_eq!(output.stderr, bytes);
    }
}

#[test]
fn stats_report_real_byte_counts_on_stderr_only() {
    let workspace = Workspace::new();
    let stdout = b"running 1 test\ntest good ... ok\ntest result: ok. 1 passed\n";
    let emitter = workspace.emitter("cargo", stdout, b"", 0);
    let output = with_prefix(emitter, &["--stats"])
        .arg("test")
        .output()
        .unwrap();
    code(&output, 0);
    assert_eq!(
        output.stdout,
        b"running 1 test\ntest result: ok. 1 passed\n"
    );
    let stats = String::from_utf8(output.stderr).unwrap();
    assert!(stats.contains("[mini] matcher=cargo"));
    assert!(stats.contains(&format!("input={}B", stdout.len())));
    assert!(stats.contains(&format!("output={}B", output.stdout.len())));
    assert!(stats.contains("passthrough_streams=0"));
}

#[test]
fn missing_executable_returns_shell_compatible_not_found_code() {
    let workspace = Workspace::new();
    let output = mini()
        .arg(workspace.0.join("executable-does-not-exist"))
        .output()
        .unwrap();
    code(&output, 127);
    assert!(output.stdout.is_empty());
    assert!(String::from_utf8_lossy(&output.stderr).starts_with("mini: "));
}

#[test]
fn help_version_and_usage_errors_are_available_without_a_child() {
    let help = mini().arg("--help").output().unwrap();
    code(&help, 0);
    assert!(String::from_utf8_lossy(&help.stdout).contains("Usage: mini"));
    assert!(help.stderr.is_empty());

    let version = mini().arg("--version").output().unwrap();
    code(&version, 0);
    assert_eq!(version.stdout, b"mini 0.1.0\n");

    for arguments in [
        vec![],
        vec!["--unknown"],
        vec!["--max-buffer"],
        vec!["--max-buffer", "0"],
        vec!["--max-line-chars", "invalid"],
        vec!["--raw", "--stats", "cargo", "test"],
    ] {
        let output = mini().args(arguments).output().unwrap();
        code(&output, 2);
        assert!(output.stdout.is_empty());
        assert!(String::from_utf8_lossy(&output.stderr).starts_with("mini: "));
    }
}

#[test]
fn delimiter_can_precede_the_child_command() {
    let output = mini()
        .args(["--", "/bin/sh", "-c", "printf 'child\\n'"])
        .output()
        .unwrap();
    code(&output, 0);
    assert_eq!(output.stdout, b"child\n");
    assert!(output.stderr.is_empty());
}

#[test]
fn signal_termination_of_a_buffered_child_returns_128_plus_signal() {
    let workspace = Workspace::new();
    let program = workspace.script("cargo", "kill -TERM \"$$\"");
    let output = mini().arg(program).arg("test").output().unwrap();
    code(&output, 143);
}

fn git_in(directory: &Path, arguments: &[&OsStr]) -> Output {
    Command::new("git")
        .arg("-C")
        .arg(directory)
        .args(arguments)
        .env("GIT_CONFIG_NOSYSTEM", "1")
        .env("GIT_CONFIG_GLOBAL", "/dev/null")
        .output()
        .expect("Git must be installed for the Git integration test")
}

#[test]
fn real_git_diff_keeps_paths_hunks_and_source_whitespace() {
    let workspace = Workspace::new();
    let init = git_in(&workspace.0, &[OsStr::new("init"), OsStr::new("--quiet")]);
    code(&init, 0);
    workspace.file("source.txt", b"    old value\n\tkeep tabs\n");
    let add = git_in(&workspace.0, &[OsStr::new("add"), OsStr::new("source.txt")]);
    code(&add, 0);
    workspace.file("source.txt", b"    new value\n\tkeep tabs\n");
    let output = mini()
        .args([OsStr::new("git"), OsStr::new("-C"), workspace.0.as_os_str()])
        .args(["--no-pager", "diff", "--no-color", "--", "source.txt"])
        .env("GIT_CONFIG_NOSYSTEM", "1")
        .env("GIT_CONFIG_GLOBAL", "/dev/null")
        .output()
        .unwrap();
    code(&output, 0);
    assert!(output.stderr.is_empty());
    let text = String::from_utf8(output.stdout).unwrap();
    assert!(text.contains("--- a/source.txt\n"));
    assert!(text.contains("+++ b/source.txt\n"));
    assert!(text.contains("@@ -1,2 +1,2 @@\n"));
    assert!(text.contains("-    old value\n"));
    assert!(text.contains("+    new value\n"));
    assert!(text.contains(" \tkeep tabs\n"));
}
