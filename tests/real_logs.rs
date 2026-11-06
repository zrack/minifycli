//! Regression replay of real tool output from intentionally failing local probes.
//! Capture commands, versions, sanitization, and statuses are in fixtures/real/.

use minifycli::{minify, Matcher};

fn assert_original_failure_suffix(input: &[u8], output: &[u8], boundary: &str) {
    let input = std::str::from_utf8(input).unwrap();
    let output = std::str::from_utf8(output).unwrap();
    let start = input.find(boundary).expect("captured failure boundary");
    assert!(
        output.ends_with(&input[start..]),
        "captured failure details or summary changed"
    );
}

#[test]
fn captured_cargo_failure_retains_original_diagnostics_in_both_streams() {
    let stdout = include_bytes!("fixtures/real/cargo.raw.stdout");
    let stderr = include_bytes!("fixtures/real/cargo.raw.stderr");
    // The original command exited with 101. Library replay receives failure
    // context; it does not execute a command or produce an exit status.
    let output = minify(stdout, Matcher::Cargo, true, None);
    assert_original_failure_suffix(stdout, &output, "test z_failure ... FAILED\n");
    let text = std::str::from_utf8(&output).unwrap();
    for diagnostic in [
        "running 11 tests\n",
        "MINIFYCLI_CARGO_ASSERTION",
        "thread 'z_failure' (8785822) panicked at src/lib.rs:22:18:",
        "stack backtrace:",
        "at ./src/lib.rs:22:18",
        "test result: FAILED. 10 passed; 1 failed;",
    ] {
        assert!(text.contains(diagnostic), "lost {diagnostic:?}");
    }
    assert!(!text.contains("test a_pass_00 ... ok\n"));
    assert!(output.len() < stdout.len());
    assert_eq!(minify(stderr, Matcher::Cargo, true, None), stderr);
}

#[test]
fn captured_node_tap_failure_retains_original_diagnostics_in_both_streams() {
    let stdout = include_bytes!("fixtures/real/npm-node-tap.raw.stdout");
    let stderr = include_bytes!("fixtures/real/npm-node-tap.raw.stderr");
    // The original npm command exited with 1; that status is capture metadata.
    let output = minify(stdout, Matcher::NpmTest, true, None);
    assert_original_failure_suffix(stdout, &output, "# Subtest: z failure\n");
    let text = std::str::from_utf8(&output).unwrap();
    for diagnostic in [
        "TAP version 13\n",
        "not ok 11 - z failure\n",
        "MINIFYCLI_NODE_ASSERTION",
        "location: '<WORKSPACE>/node-probe/test.js:13:1'",
        "TestContext.<anonymous> (<WORKSPACE>/node-probe/test.js:13:32)",
        "code: 'ERR_ASSERTION'",
        "1..11\n# tests 11\n# suites 0\n# pass 10\n# fail 1\n",
    ] {
        assert!(text.contains(diagnostic), "lost {diagnostic:?}");
    }
    assert!(!text.contains("ok 1 - a pass 00\n"));
    assert!(output.len() < stdout.len());
    assert_eq!(minify(stderr, Matcher::NpmTest, true, None), stderr);
}
