#![cfg(unix)]

//! Synthetic reporter-shaped output must not erase application diagnostics.

use std::fs;
use std::os::unix::fs::PermissionsExt;
use std::path::PathBuf;
use std::process::Command;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

static NEXT_DIRECTORY: AtomicUsize = AtomicUsize::new(0);

struct Emitter(PathBuf);

impl Emitter {
    fn new() -> Self {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let id = NEXT_DIRECTORY.fetch_add(1, Ordering::Relaxed);
        let directory = std::env::temp_dir().join(format!(
            "minifycli-log-retention-{}-{nonce}-{id}",
            std::process::id()
        ));
        fs::create_dir(&directory).unwrap();
        let program = directory.join("npm");
        fs::write(
            &program,
            b"#!/bin/sh\nset -eu\ncat \"$MINI_RETENTION_STDOUT\"\ncat \"$MINI_RETENTION_STDERR\" >&2\nexit \"$MINI_RETENTION_STATUS\"\n",
        )
        .unwrap();
        fs::set_permissions(program, fs::Permissions::from_mode(0o755)).unwrap();
        Self(directory)
    }

    fn assert_streams(
        &self,
        stdout: &[u8],
        stderr: &[u8],
        expected_stdout: &[u8],
        expected_stderr: &[u8],
        status: i32,
    ) {
        let stdout_path = self.0.join("stdout.log");
        let stderr_path = self.0.join("stderr.log");
        fs::write(&stdout_path, stdout).unwrap();
        fs::write(&stderr_path, stderr).unwrap();
        let output = Command::new(env!("CARGO_BIN_EXE_mini"))
            .arg(self.0.join("npm"))
            .arg("test")
            .env("MINI_RETENTION_STDOUT", stdout_path)
            .env("MINI_RETENTION_STDERR", stderr_path)
            .env("MINI_RETENTION_STATUS", status.to_string())
            .output()
            .unwrap();
        assert_eq!(output.status.code(), Some(status));
        assert_eq!(output.stdout, expected_stdout, "stdout diagnostic loss");
        assert_eq!(output.stderr, expected_stderr, "stderr diagnostic loss");
    }
}

impl Drop for Emitter {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn assert_fixture_on_each_stream(input: &[u8], expected: &[u8], status: i32) {
    let emitter = Emitter::new();
    emitter.assert_streams(input, b"", expected, b"", status);
    emitter.assert_streams(b"", input, b"", expected, status);
    emitter.assert_streams(input, input, expected, expected, status);
}

#[test]
fn jest_preserves_application_checkmarks_and_timing_lookalikes() {
    assert_fixture_on_each_stream(
        include_bytes!("fixtures/logs/jest-application-success.log"),
        include_bytes!("fixtures/logs/jest-application-success.expected.log"),
        0,
    );
}

#[test]
fn jest_preserves_success_looking_diagnostics_before_and_inside_failures() {
    assert_fixture_on_each_stream(
        include_bytes!("fixtures/logs/jest-application-failure.log"),
        include_bytes!("fixtures/logs/jest-application-failure.expected.log"),
        17,
    );
}

#[test]
fn vitest_preserves_ambiguous_success_records_byte_for_byte() {
    let input = include_bytes!("fixtures/logs/vitest-application-success.log");
    assert_fixture_on_each_stream(input, input, 0);
}

#[test]
fn jest_preserves_crlf_and_missing_final_newline_in_both_streams() {
    let input = include_bytes!("fixtures/logs/jest-application-crlf.log");
    let expected = include_bytes!("fixtures/logs/jest-application-crlf.expected.log");
    assert!(input.contains(&b'\r'));
    assert!(!input.ends_with(b"\n"));
    assert!(!expected.ends_with(b"\n"));
    assert_fixture_on_each_stream(input, expected, 0);
}
