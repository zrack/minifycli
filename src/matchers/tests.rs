//! Small, conservative matchers for human-readable test output.
//!
//! These are format recognizers, not parsers for arbitrary test-runner output.
//! A framework summary must be present before any test line is removed. Once
//! failure output starts, the remainder of that stream is kept intact.

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum TestKind {
    Cargo,
    Npm,
}

pub fn minify(input: &str, kind: TestKind, failed: bool) -> Option<String> {
    let output = match kind {
        TestKind::Cargo => cargo(input, failed),
        TestKind::Npm => npm(input, failed),
    }?;
    (output.len() < input.len()).then_some(output)
}

fn content(line: &str) -> &str {
    let line = line.strip_suffix('\n').unwrap_or(line);
    line.strip_suffix('\r').unwrap_or(line)
}

fn cargo(input: &str, failed: bool) -> Option<String> {
    let lines: Vec<&str> = input.split_inclusive('\n').collect();
    if failed
        && !lines
            .iter()
            .any(|line| cargo_failure_boundary(content(line)))
    {
        // A successful-looking test run followed by an unexplained command
        // failure may be a script/infrastructure problem. Keep all evidence.
        return None;
    }
    let has_test_summary = lines.iter().any(|line| {
        let line = content(line);
        line.starts_with("test result: ok.") || line.starts_with("test result: FAILED.")
    });
    let has_build_summary = lines.iter().any(|line| {
        let line = content(line);
        line.starts_with("    Finished ")
            && (line.contains(" profile ") || line.contains(" target(s) in "))
    });
    if !has_test_summary && !has_build_summary {
        return None;
    }

    let mut output = String::with_capacity(input.len());
    let mut running_tests = false;
    let mut preserve_tail = false;
    for original in lines {
        let line = content(original);
        if cargo_failure_boundary(line) {
            preserve_tail = true;
        }
        if preserve_tail {
            output.push_str(original);
            continue;
        }
        if has_test_summary && cargo_test_count(line) {
            running_tests = true;
            // Keep the count: a useful boundary between test binaries.
            output.push_str(original);
            continue;
        }
        if line.starts_with("test result: ") {
            running_tests = false;
        }
        if running_tests && cargo_pass(line) {
            continue;
        }
        if cargo_progress(line) {
            continue;
        }
        output.push_str(original);
    }
    Some(output)
}

fn cargo_test_count(line: &str) -> bool {
    let Some(rest) = line.strip_prefix("running ") else {
        return false;
    };
    let Some((count, suffix)) = rest.split_once(' ') else {
        return false;
    };
    !count.is_empty()
        && count.bytes().all(|byte| byte.is_ascii_digit())
        && (suffix == "tests" || suffix == "test")
}

fn cargo_pass(line: &str) -> bool {
    let Some(name) = line
        .strip_prefix("test ")
        .and_then(|line| line.strip_suffix(" ... ok"))
    else {
        return false;
    };
    // libtest names are identifiers/paths, with optional doctest locations or
    // the `- should panic` suffix. Do not consume arbitrary indented logs.
    !name.is_empty() && !name.contains('\t') && !name.starts_with(' ')
}

fn cargo_failure_boundary(line: &str) -> bool {
    let trimmed = line.trim_start();
    trimmed == "failures:"
        || trimmed.starts_with("---- ")
        || trimmed.starts_with("thread '")
        || trimmed.starts_with("error:")
        || trimmed.starts_with("error[")
        || (line.starts_with("test ") && line.ends_with(" ... FAILED"))
}

fn cargo_progress(line: &str) -> bool {
    ["   Compiling ", "    Checking "]
        .iter()
        .filter_map(|prefix| line.strip_prefix(prefix))
        .any(|rest| {
            // Cargo always includes the crate version in these progress lines.
            rest.split_whitespace()
                .nth(1)
                .and_then(|version| version.strip_prefix('v'))
                .and_then(|version| version.bytes().next())
                .is_some_and(|byte| byte.is_ascii_digit())
        })
}

fn npm(input: &str, failed: bool) -> Option<String> {
    let lines: Vec<&str> = input.split_inclusive('\n').collect();
    if failed && !lines.iter().any(|line| npm_failure_boundary(content(line))) {
        return None;
    }
    let jest = lines
        .iter()
        .any(|line| content(line).starts_with("Test Suites:"))
        && lines.iter().any(|line| content(line).starts_with("Tests:"));
    let vitest = lines.iter().any(|line| {
        let line = content(line).trim_start();
        line.starts_with("Test Files ") && (line.contains(" passed ") || line.contains(" failed "))
    }) && lines.iter().any(|line| {
        let line = content(line).trim_start();
        line.starts_with("Tests ") && (line.contains(" passed ") || line.contains(" failed "))
    });
    let tap = lines.iter().any(|line| content(line) == "TAP version 13")
        && lines
            .iter()
            .any(|line| tap_summary_count(content(line), "# tests "))
        && lines
            .iter()
            .any(|line| tap_summary_count(content(line), "# fail "));
    if !jest && !vitest && !tap {
        return None;
    }

    let mut output = String::with_capacity(input.len());
    let mut preserve_tail = false;
    let mut index = 0;
    while index < lines.len() {
        let original = lines[index];
        let line = content(original);
        if npm_failure_boundary(line) {
            preserve_tail = true;
        }
        if preserve_tail {
            output.push_str(original);
            index += 1;
            continue;
        }
        if tap {
            if let Some(end) = tap_passing_record(&lines, index) {
                index = end;
                continue;
            }
        }
        if jest && jest_pass_header(line) {
            index += 1;
            continue;
        }
        output.push_str(original);
        index += 1;
    }
    Some(output)
}

fn tap_summary_count(line: &str, prefix: &str) -> bool {
    line.strip_prefix(prefix)
        .is_some_and(|count| !count.is_empty() && count.bytes().all(|byte| byte.is_ascii_digit()))
}

fn npm_failure_boundary(line: &str) -> bool {
    let line = line.trim_start();
    [
        "FAIL ",
        "FAIL\t",
        "not ok ",
        "● ",
        "× ",
        "✕ ",
        "✗ ",
        "AssertionError",
        "Error:",
    ]
    .iter()
    .any(|prefix| line.starts_with(prefix))
        || line.starts_with("⎯⎯")
        || line
            .split_once(':')
            .is_some_and(|(kind, _)| kind.ends_with("Error") && !kind.contains(' '))
}

/// Individual success markers, including timing-looking ones, can be ordinary
/// application logs. Keep all of them. Only a column-zero Jest file header with
/// an ordinary test-file path is eligible for removal; unfamiliar headers stay.
fn jest_pass_header(line: &str) -> bool {
    let Some(path) = line.strip_prefix("PASS ") else {
        return false;
    };
    let path = path.trim_start_matches(' ');
    if path.is_empty() || path.chars().any(char::is_whitespace) || path.contains(['\u{1b}', '\0']) {
        return false;
    }
    let filename = path.rsplit('/').next().unwrap_or(path);
    let test_location = filename.contains(".test.")
        || filename.contains(".spec.")
        || path.starts_with("__tests__/")
        || path.contains("/__tests__/");
    test_location
        && [".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts"]
            .iter()
            .any(|extension| filename.ends_with(extension))
}

/// Consume only a top-level TAP pass with optional *timing-only* YAML.
/// Nested subtests, skipped/todo tests, diagnostic comments, and unfamiliar
/// YAML keys remain intact. This intentionally misses some valid TAP formats.
fn tap_passing_record(lines: &[&str], start: usize) -> Option<usize> {
    let mut index = start;
    let subtest_name = content(lines[index]).strip_prefix("# Subtest: ");
    if subtest_name.is_some() {
        index += 1;
    } else if start > 0 {
        let previous = content(lines[start - 1]);
        if previous.starts_with("    ") || previous.starts_with("# Subtest: ") {
            // Keep the parent status of a nested subtest, and do not retry
            // removing part of a record rejected at its preceding header.
            return None;
        }
    }
    let pass = content(lines.get(index)?).strip_prefix("ok ")?;
    let (number, name) = pass.split_once(" - ")?;
    if number.is_empty()
        || !number.bytes().all(|byte| byte.is_ascii_digit())
        || name.is_empty()
        || name.contains(" #")
        || subtest_name.is_some_and(|subtest_name| subtest_name != name)
    {
        return None;
    }
    index += 1;
    if lines.get(index).map(|line| content(line)) == Some("  ---") {
        index += 1;
        let mut timing_seen = false;
        loop {
            let line = content(lines.get(index)?);
            if line == "  ..." && timing_seen {
                return Some(index + 1);
            }
            if let Some(duration) = line.strip_prefix("  duration_ms: ") {
                if duration.parse::<f64>().is_err() {
                    return None;
                }
                timing_seen = true;
            } else if line != "  type: 'test'" && line != "  type: 'suite'" {
                return None;
            }
            index += 1;
        }
    }
    Some(index)
}

#[cfg(test)]
mod unit_tests {
    use super::{minify, TestKind};

    #[test]
    fn cargo_preserves_failure_text_even_when_it_looks_like_a_pass() {
        let failure = "test bad ... FAILED\n\nfailures:\n\n---- bad stdout ----\nthread 'bad' panicked at src/lib.rs:4:5:\ntest misleading ... ok\n  assertion left == right failed\n  left: 1\n right: 2\n\nfailures:\n    bad\n\ntest result: FAILED. 1 passed; 1 failed; 0 ignored\n";
        let input = format!("running 2 tests\ntest good ... ok\n{failure}");
        let result = minify(&input, TestKind::Cargo, true).unwrap();
        assert!(!result.contains("test good ... ok"));
        assert!(result.ends_with(failure));
    }

    #[test]
    fn cargo_retains_counts_summaries_ignored_tests_and_user_logs() {
        let input = "running 3 tests\ntest one ... ok\napplication message\ntest two ... ignored\ntest three ... ok\ntest result: ok. 2 passed; 0 failed; 1 ignored\n";
        assert_eq!(
            minify(input, TestKind::Cargo, false).unwrap(),
            "running 3 tests\napplication message\ntest two ... ignored\ntest result: ok. 2 passed; 0 failed; 1 ignored\n"
        );
    }

    #[test]
    fn cargo_handles_multiple_test_binaries_and_doctests() {
        let input = "running 1 test\ntest one ... ok\ntest result: ok. 1 passed\n\n   Doc-tests demo\nrunning 1 test\ntest src/lib.rs - demo (line 2) ... ok\ntest result: ok. 1 passed\n";
        let result = minify(input, TestKind::Cargo, false).unwrap();
        assert!(!result.contains(" ... ok"));
        assert_eq!(result.matches("running 1 test").count(), 2);
        assert!(result.contains("   Doc-tests demo"));
    }

    #[test]
    fn cargo_keeps_compiler_warnings_and_source_excerpts() {
        let warning = "warning: unused variable: `value`\n --> src/main.rs:2:9\n  |\n2 |     let value = 1;\n  |         ^^^^^ help: prefix with an underscore\n";
        let input = format!("    Checking demo v0.1.0 (/tmp/demo)\n{warning}    Finished `dev` profile [unoptimized] target(s) in 0.10s\n");
        let result = minify(&input, TestKind::Cargo, false).unwrap();
        assert!(result.starts_with(warning));
        assert!(result.contains("    Finished `dev` profile"));
    }

    #[test]
    fn failed_compiler_without_summary_falls_back() {
        let input =
            "    Checking demo v0.1.0\nerror[E0308]: mismatched types\n  --> src/main.rs:2:1\n";
        assert!(minify(input, TestKind::Cargo, true).is_none());
    }

    #[test]
    fn pass_looking_user_output_outside_test_run_is_kept() {
        let input = "test log_message ... ok\nrunning 1 test\ntest real_test ... ok\ntest result: ok. 1 passed\n";
        let result = minify(input, TestKind::Cargo, false).unwrap();
        assert!(result.starts_with("test log_message ... ok\n"));
    }

    #[test]
    fn cargo_preserves_crlf_and_missing_final_newline() {
        let input = "running 1 test\r\ntest one ... ok\r\ntest result: ok. 1 passed";
        assert_eq!(
            minify(input, TestKind::Cargo, false).unwrap(),
            "running 1 test\r\ntest result: ok. 1 passed"
        );
    }

    #[test]
    fn cargo_unknown_and_summary_only_outputs_fall_back() {
        assert!(minify("all good\n", TestKind::Cargo, false).is_none());
        assert!(minify("test result: ok. 0 passed\n", TestKind::Cargo, false).is_none());
    }

    #[test]
    fn jest_removes_file_headers_and_keeps_individual_success_and_failure_output() {
        let tail = "FAIL src/bad.test.js\n  ● bad\n    Expected: 1\n    Received: 2\n    ✓ this line is part of the assertion\n    at src/bad.test.js:3:4\nTest Suites: 1 failed, 1 passed, 2 total\nTests: 1 failed, 3 passed, 4 total\n";
        let input = format!("PASS src/good.test.js\n  suite\n    ✓ works (2 ms)\n{tail}");
        let result = minify(&input, TestKind::Npm, true).unwrap();
        assert_eq!(result, format!("  suite\n    ✓ works (2 ms)\n{tail}"));
    }

    #[test]
    fn vitest_keeps_ambiguous_success_lines_and_user_logs() {
        let input = " RUN  v2.0.0 /tmp/project\n ✓ test/a.test.ts (4 tests) 3ms\nlog from the application\n Test Files  1 passed (1)\n      Tests  4 passed (4)\n   Duration  100ms\n";
        assert_eq!(minify(input, TestKind::Npm, false), None);
    }

    #[test]
    fn vitest_failure_assertion_is_never_filtered() {
        let input = " ✓ test/a.test.ts (1 test) 3ms\n FAIL  test/b.test.ts > bad\nAssertionError: expected true\n ✓ assertion text\n Test Files  1 failed | 1 passed (2)\n      Tests  1 failed | 1 passed (2)\n";
        assert_eq!(minify(input, TestKind::Npm, true), None);
    }

    #[test]
    fn jest_keeps_application_success_messages_even_with_timings() {
        let input = "PASS src/good.test.js\n  console.log\n    ✓ migration completed\n    ✔ cache warmed (2 ms)\n    √ result verified\nPASS database migration completed\nTest Suites: 1 passed, 1 total\nTests: 1 passed, 1 total\n";
        assert_eq!(
            minify(input, TestKind::Npm, false).unwrap(),
            input.strip_prefix("PASS src/good.test.js\n").unwrap()
        );
    }

    #[test]
    fn jest_keeps_indented_or_unfamiliar_pass_headers() {
        for header in [
            "    PASS src/good.test.js",
            "PASS database migration completed",
            "PASS src/good.test.js (2 s)",
            "PASS src/path with spaces/good.test.js",
            "PASS src/custom-runner.file",
        ] {
            let input =
                format!("{header}\nTest Suites: 1 passed, 1 total\nTests: 1 passed, 1 total\n");
            assert_eq!(minify(&input, TestKind::Npm, false), None, "{header}");
        }
    }

    #[test]
    fn tap_removes_only_timing_only_pass_records() {
        let input = "TAP version 13\n# application log\n# Subtest: good\nok 1 - good\n  ---\n  duration_ms: 1.3\n  type: 'test'\n  ...\n1..1\n# tests 1\n# pass 1\n# fail 0\n";
        assert_eq!(
            minify(input, TestKind::Npm, false).unwrap(),
            "TAP version 13\n# application log\n1..1\n# tests 1\n# pass 1\n# fail 0\n"
        );
    }

    #[test]
    fn tap_failure_and_following_output_are_preserved() {
        let tail = "# Subtest: bad\nnot ok 2 - bad\n  ---\n  error: failure\n  stack: |-\n    ok 99 - assertion text\n  ...\nok 3 - later pass\n1..3\n# tests 3\n# pass 2\n# fail 1\n";
        let input = format!("TAP version 13\nok 1 - good\n{tail}");
        let result = minify(&input, TestKind::Npm, true).unwrap();
        assert_eq!(result, format!("TAP version 13\n{tail}"));
    }

    #[test]
    fn tap_preserves_unknown_yaml_and_skip_directives() {
        let input = "TAP version 13\nok 1 - diagnostics\n  ---\n  detail: useful\n  ...\nok 2 - later\nok 3 - unavailable # SKIP unavailable\n1..3\n# tests 3\n# fail 0\n";
        let result = minify(input, TestKind::Npm, false).unwrap();
        assert!(result.contains("ok 1 - diagnostics\n  ---\n  detail: useful\n  ...\n"));
        assert!(result.contains("ok 3 - unavailable # SKIP unavailable\n"));
        assert!(!result.contains("ok 2 - later\n"));
    }

    #[test]
    fn nested_tap_is_not_treated_as_a_top_level_pass() {
        let input = "TAP version 13\n# Subtest: parent\n    # Subtest: child\n    ok 1 - child\n    1..1\nok 1 - parent\nok 2 - another\n1..2\n# tests 2\n# fail 0\n";
        let result = minify(input, TestKind::Npm, false).unwrap();
        assert!(result.contains("    ok 1 - child\n"));
        assert!(result.contains("# Subtest: parent\n"));
        assert!(result.contains("ok 1 - parent\n"));
    }

    #[test]
    fn npm_unknown_format_falls_back() {
        assert!(minify("PASS this is a user log\n", TestKind::Npm, false).is_none());
        assert!(minify("npm ERR! missing script: test\n", TestKind::Npm, true).is_none());
    }

    #[test]
    fn unexplained_nonzero_exit_preserves_successful_test_logs() {
        assert!(minify(
            "running 1 test\ntest good ... ok\ntest result: ok. 1 passed\n",
            TestKind::Cargo,
            true,
        )
        .is_none());
        assert!(minify(
            "PASS good.test.js\nTest Suites: 1 passed, 1 total\nTests: 1 passed, 1 total\n",
            TestKind::Npm,
            true,
        )
        .is_none());
    }
}
