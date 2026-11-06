#![cfg(any(target_os = "linux", target_os = "macos"))]

use std::fs::{self, File};
use std::io::Write;
use std::os::unix::fs::PermissionsExt;
use std::os::unix::io::AsRawFd;
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdout, Command, ExitStatus, Stdio};
use std::sync::atomic::{AtomicI32, AtomicUsize, Ordering};
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

const SIGINT: i32 = 2;
const SIGKILL: i32 = 9;
const SIGTERM: i32 = 15;
const SIG_IGN: usize = 1;
const FIXTURE_ROLE: &str = "MINIFYCLI_CANCELLATION_ROLE";
const FIXTURE_DIR: &str = "MINIFYCLI_CANCELLATION_DIR";
const FIXTURE_IGNORE: &str = "MINIFYCLI_CANCELLATION_IGNORE";
const FIXTURE_EARLY_EXIT: &str = "MINIFYCLI_CANCELLATION_EARLY_EXIT";
const FIXTURE_EMIT: &str = "MINIFYCLI_CANCELLATION_EMIT";
const TEST_TIMEOUT: Duration = Duration::from_secs(6);
static NEXT_DIRECTORY: AtomicUsize = AtomicUsize::new(0);
static RECEIVED_SIGNAL: AtomicI32 = AtomicI32::new(0);

#[repr(C)]
struct PollFd {
    fd: i32,
    events: i16,
    revents: i16,
}

#[cfg(target_os = "macos")]
type PollCount = u32;
#[cfg(target_os = "linux")]
type PollCount = usize;

extern "C" {
    fn kill(pid: i32, signal: i32) -> i32;
    fn signal(number: i32, handler: usize) -> usize;
    fn poll(descriptors: *mut PollFd, count: PollCount, timeout_ms: i32) -> i32;
}

extern "C" fn record_signal(number: i32) {
    RECEIVED_SIGNAL.store(number, Ordering::Relaxed);
}

fn send_signal(pid: u32, number: i32) -> bool {
    // The test creates and owns every positive PID supplied here.
    unsafe { kill(i32::try_from(pid).unwrap(), number) == 0 }
}

fn kill_group(pid: u32) {
    // These group IDs belong to mini or its fixture child, never the runner.
    unsafe {
        kill(-i32::try_from(pid).unwrap(), SIGKILL);
    }
}

fn fixture_pid(directory: &Path, role: &str) -> Option<u32> {
    fs::read_to_string(directory.join(format!("{role}.pid")))
        .ok()?
        .trim()
        .parse()
        .ok()
}

struct Harness {
    directory: PathBuf,
    child: Child,
    stdout_reader: Option<ChildStdout>,
    deadline: Instant,
}

impl Harness {
    fn spawn(ignore_signals: bool, early_leader_exit: bool) -> Self {
        Self::spawn_inner(ignore_signals, early_leader_exit, false)
    }

    fn spawn_piped_emitter() -> Self {
        Self::spawn_inner(false, false, true)
    }

    fn spawn_inner(ignore_signals: bool, early_leader_exit: bool, piped_emitter: bool) -> Self {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let id = NEXT_DIRECTORY.fetch_add(1, Ordering::Relaxed);
        let directory = std::env::temp_dir().join(format!(
            "minifycli-cancellation-{}-{nonce}-{id}",
            std::process::id()
        ));
        fs::create_dir(&directory).unwrap();

        // A libtest executable can act as a std-only subprocess fixture. Its
        // basename selects the real Cargo capture path; `test --exact` runs
        // only the worker function below, rather than these cancellation tests.
        let fixture = directory.join("cargo");
        fs::copy(std::env::current_exe().unwrap(), &fixture).unwrap();
        fs::set_permissions(&fixture, fs::Permissions::from_mode(0o755)).unwrap();

        let stdout = File::create(directory.join("stdout.log")).unwrap();
        let stderr = File::create(directory.join("stderr.log")).unwrap();
        let mut command = Command::new(env!("CARGO_BIN_EXE_mini"));
        if piped_emitter {
            command.args(["--max-buffer", "32"]);
        }
        command
            .arg(fixture)
            .args(["test", "--exact"])
            .env(FIXTURE_ROLE, "parent")
            .env(FIXTURE_DIR, &directory)
            .env(FIXTURE_IGNORE, if ignore_signals { "1" } else { "0" })
            .env(FIXTURE_EMIT, if piped_emitter { "1" } else { "0" })
            .env(
                FIXTURE_EARLY_EXIT,
                if early_leader_exit { "1" } else { "0" },
            )
            .stdin(Stdio::null())
            .stdout(if piped_emitter {
                Stdio::piped()
            } else {
                Stdio::from(stdout)
            })
            .stderr(Stdio::from(stderr))
            .process_group(0);
        let mut child = command.spawn().unwrap();
        let stdout_reader = child.stdout.take();
        Self {
            directory,
            child,
            stdout_reader,
            deadline: Instant::now() + TEST_TIMEOUT,
        }
    }

    fn logs(&self) -> String {
        format!(
            "stdout:\n{}\nstderr:\n{}",
            fs::read_to_string(self.directory.join("stdout.log")).unwrap_or_default(),
            fs::read_to_string(self.directory.join("stderr.log")).unwrap_or_default()
        )
    }

    fn wait_ready(&mut self) {
        loop {
            if self.directory.join("parent.ready").exists()
                && self.directory.join("descendant.ready").exists()
            {
                return;
            }
            assert!(
                self.child.try_wait().unwrap().is_none(),
                "mini exited before fixture readiness; {}",
                self.logs()
            );
            assert!(
                Instant::now() < self.deadline,
                "fixture readiness timed out; {}",
                self.logs()
            );
            thread::sleep(Duration::from_millis(10));
        }
    }

    fn wait_exit(&mut self) -> ExitStatus {
        loop {
            if let Some(status) = self.child.try_wait().unwrap() {
                return status;
            }
            assert!(
                Instant::now() < self.deadline,
                "mini did not exit within the watchdog deadline; {}",
                self.logs()
            );
            thread::sleep(Duration::from_millis(10));
        }
    }

    fn wait_emitting(&mut self) {
        self.wait_ready();
        loop {
            let mut descriptor = PollFd {
                fd: self.stdout_reader.as_ref().unwrap().as_raw_fd(),
                events: 1, // POLLIN: observe queued bytes without consuming any.
                revents: 0,
            };
            let readable =
                unsafe { poll(&mut descriptor, 1, 0) } > 0 && descriptor.revents & 1 != 0;
            if self.directory.join("emitter.started").exists() && readable {
                assert!(
                    !self.directory.join("emitter.completed").exists(),
                    "the 16MiB write should not fit in the unread pipe chain"
                );
                return;
            }
            assert!(
                self.child.try_wait().unwrap().is_none(),
                "mini exited before output reached its downstream pipe; {}",
                self.logs()
            );
            assert!(
                Instant::now() < self.deadline,
                "emitter readiness timed out"
            );
            thread::sleep(Duration::from_millis(10));
        }
    }
}

impl Drop for Harness {
    fn drop(&mut self) {
        // Cleanup also runs on failed assertions, including against a mini
        // implementation that never forwards the signal. Output uses files so
        // surviving descendants cannot hold a pipe open and deadlock the test.
        if let Some(pid) = fixture_pid(&self.directory, "parent") {
            kill_group(pid);
            send_signal(pid, SIGKILL);
        }
        if let Some(pid) = fixture_pid(&self.directory, "descendant") {
            send_signal(pid, SIGKILL);
        }
        kill_group(self.child.id());
        let _ = self.child.kill();
        let _ = self.child.wait();
        let _ = fs::remove_dir_all(&self.directory);
    }
}

fn is_live_non_zombie(pid: u32) -> bool {
    let output = Command::new("ps")
        .args(["-o", "stat=", "-p", &pid.to_string()])
        .output()
        .expect("ps is required for Unix cancellation integration tests");
    let states = String::from_utf8_lossy(&output.stdout);
    // A killed orphan may briefly remain a zombie until the OS reaps it. It
    // cannot execute or retain descriptors, so this counts as stopped.
    states
        .split_whitespace()
        .any(|state| !state.starts_with('Z'))
}

fn assert_stopped(pid: u32) {
    let deadline = Instant::now() + Duration::from_secs(1);
    while is_live_non_zombie(pid) {
        assert!(
            Instant::now() < deadline,
            "fixture process {pid} remained live after mini exited"
        );
        thread::sleep(Duration::from_millis(10));
    }
}

fn cancellation_case(number: i32, ignore_signals: bool) {
    let mut harness = Harness::spawn(ignore_signals, false);
    harness.wait_ready();
    let parent = fixture_pid(&harness.directory, "parent").unwrap();
    let descendant = fixture_pid(&harness.directory, "descendant").unwrap();
    assert_ne!(harness.child.id(), parent);
    assert_ne!(parent, descendant);
    assert!(is_live_non_zombie(parent));
    assert!(is_live_non_zombie(descendant));

    let cancelled_at = Instant::now();
    assert!(send_signal(harness.child.id(), number));
    let status = harness.wait_exit();
    assert_eq!(
        status.code(),
        Some(128 + number),
        "mini should convert received cancellation to shell-compatible status; {}",
        harness.logs()
    );
    assert!(
        cancelled_at.elapsed() < Duration::from_secs(4),
        "cancellation should have a bounded grace period"
    );
    assert_stopped(parent);
    assert_stopped(descendant);

    if !ignore_signals {
        for role in ["parent", "descendant"] {
            let observed = fs::read_to_string(harness.directory.join(format!("{role}.signal")))
                .unwrap_or_else(|error| panic!("{role} did not observe forwarded signal: {error}"));
            assert_eq!(observed, number.to_string());
        }
    }

    let stdout = fs::read_to_string(harness.directory.join("stdout.log")).unwrap();
    let stderr = fs::read_to_string(harness.directory.join("stderr.log")).unwrap();
    assert!(
        stdout.contains("test cancellation_fixture_must_remain ... ok\n"),
        "cancelled output must bypass normal passing-test filtering; {stdout}"
    );
    assert!(
        stderr.contains("   Compiling cancellation-fixture v0.0.0\n"),
        "cancelled stderr must bypass normal progress filtering; {stderr}"
    );
}

#[test]
fn sigterm_to_mini_reaches_child_and_descendant() {
    cancellation_case(SIGTERM, false);
}

#[test]
fn sigint_to_mini_reaches_child_and_descendant() {
    cancellation_case(SIGINT, false);
}

#[test]
fn sigterm_forces_cleanup_when_child_and_descendant_ignore_it() {
    cancellation_case(SIGTERM, true);
}

#[test]
fn sigint_forces_cleanup_when_child_and_descendant_ignore_it() {
    cancellation_case(SIGINT, true);
}

#[test]
fn cancellation_stops_descendant_holding_pipes_after_leader_exits() {
    let mut harness = Harness::spawn(false, true);
    harness.wait_ready();
    let parent = fixture_pid(&harness.directory, "parent").unwrap();
    let descendant = fixture_pid(&harness.directory, "descendant").unwrap();
    assert_stopped(parent);
    assert!(is_live_non_zombie(descendant));
    assert!(
        harness.child.try_wait().unwrap().is_none(),
        "mini should still be draining the pipe retained by the descendant"
    );

    assert!(send_signal(harness.child.id(), SIGTERM));
    let status = harness.wait_exit();
    assert_eq!(status.code(), Some(143), "{}", harness.logs());
    assert_stopped(descendant);
    assert_eq!(
        fs::read_to_string(harness.directory.join("descendant.signal")).unwrap(),
        "15"
    );
}

#[test]
fn sigterm_exits_when_spilled_stdout_is_blocked_by_an_unread_pipe() {
    let mut harness = Harness::spawn_piped_emitter();
    harness.wait_emitting();
    let parent = fixture_pid(&harness.directory, "parent").unwrap();
    let descendant = fixture_pid(&harness.directory, "descendant").unwrap();
    let cancelled_at = Instant::now();
    assert!(send_signal(harness.child.id(), SIGTERM));
    let status = harness.wait_exit();
    assert_eq!(status.code(), Some(143), "{}", harness.logs());
    assert!(cancelled_at.elapsed() < Duration::from_secs(2));
    assert_stopped(parent);
    assert_stopped(descendant);
    // Keep the unread consumer alive throughout the exit/cleanup assertions.
    assert!(harness.stdout_reader.is_some());
}

#[test]
fn closing_downstream_pipe_stops_infinite_emitter_without_external_signal() {
    let mut harness = Harness::spawn_piped_emitter();
    harness.wait_emitting();
    let parent = fixture_pid(&harness.directory, "parent").unwrap();
    let descendant = fixture_pid(&harness.directory, "descendant").unwrap();
    let closed_at = Instant::now();
    drop(harness.stdout_reader.take());
    let status = harness.wait_exit();
    assert_eq!(status.code(), Some(141), "{}", harness.logs());
    assert!(closed_at.elapsed() < Duration::from_secs(2));
    assert_stopped(parent);
    assert_stopped(descendant);
}

/// Subprocess entry point: it is a no-op in the ordinary test run. The harness
/// copies this executable to `cargo` and invokes exactly this one test.
#[test]
fn test() {
    let Ok(role) = std::env::var(FIXTURE_ROLE) else {
        return;
    };
    let directory = PathBuf::from(std::env::var_os(FIXTURE_DIR).unwrap());
    let ignore_signals = std::env::var(FIXTURE_IGNORE).unwrap() == "1";
    let emit = role == "parent" && std::env::var(FIXTURE_EMIT).unwrap() == "1";
    let handler = if ignore_signals {
        SIG_IGN
    } else {
        record_signal as *const () as usize
    };
    unsafe {
        assert_ne!(signal(SIGINT, handler), usize::MAX);
        assert_ne!(signal(SIGTERM, handler), usize::MAX);
    }
    fs::write(
        directory.join(format!("{role}.pid")),
        std::process::id().to_string(),
    )
    .unwrap();

    let mut descendant = if role == "parent" {
        let child = Command::new(std::env::current_exe().unwrap())
            .args(["test", "--exact"])
            .env(FIXTURE_ROLE, "descendant")
            .spawn()
            .unwrap();
        let deadline = Instant::now() + Duration::from_secs(3);
        while !directory.join("descendant.ready").exists() {
            assert!(
                Instant::now() < deadline,
                "descendant failed to become ready"
            );
            thread::sleep(Duration::from_millis(5));
        }
        std::io::stdout()
            .write_all(b"running 1 test\ntest cancellation_fixture_must_remain ... ok\ntest result: ok. 1 passed; 0 failed\n")
            .unwrap();
        std::io::stdout().flush().unwrap();
        std::io::stderr()
            .write_all(b"   Compiling cancellation-fixture v0.0.0\n    Finished `test` profile target(s) in 0.0s\n")
            .unwrap();
        std::io::stderr().flush().unwrap();
        Some(child)
    } else {
        None
    };
    fs::write(directory.join(format!("{role}.ready")), b"ready").unwrap();
    if role == "parent" && std::env::var(FIXTURE_EARLY_EXIT).unwrap() == "1" {
        // std::process::exit intentionally leaves the descendant running with
        // its inherited pipes, reproducing a daemonizing command leader.
        std::process::exit(0);
    }

    let watchdog = Instant::now() + Duration::from_secs(15);
    let chunk = if emit {
        vec![b'x'; 16 * 1024 * 1024]
    } else {
        Vec::new()
    };
    loop {
        let received = RECEIVED_SIGNAL.load(Ordering::Relaxed);
        if received != 0 {
            fs::write(
                directory.join(format!("{role}.signal")),
                received.to_string(),
            )
            .unwrap();
            if let Some(child) = descendant.as_mut() {
                // Give the equally signalled descendant a short opportunity to
                // exit and be reaped. The outer harness remains authoritative.
                let deadline = Instant::now() + Duration::from_millis(200);
                while child.try_wait().unwrap().is_none() && Instant::now() < deadline {
                    thread::sleep(Duration::from_millis(5));
                }
            }
            // A command may handle cancellation and report success. Mini must
            // still expose the received signal and preserve its buffered bytes.
            std::process::exit(0);
        }
        if Instant::now() >= watchdog {
            if let Some(child) = descendant.as_mut() {
                let _ = child.kill();
                let _ = child.wait();
            }
            std::process::exit(77);
        }
        if emit {
            fs::write(directory.join("emitter.started"), b"writing").unwrap();
            if std::io::stdout().write_all(&chunk).is_err() {
                std::process::exit(0);
            }
            fs::write(directory.join("emitter.completed"), b"written").unwrap();
        }
        thread::sleep(Duration::from_millis(5));
    }
}
