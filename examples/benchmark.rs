//! Reproduce byte reductions on the checked-in handcrafted format fixtures.
use minifycli::{minify, Matcher};

struct Fixture {
    label: &'static str,
    input: &'static [u8],
    matcher: Matcher,
    failed: bool,
    preserve_tail: Option<&'static str>,
    preserve: &'static [&'static str],
}

fn main() {
    let fixtures = [
        Fixture {
            label: "cargo test: 40 pass / 1 fail",
            input: include_bytes!("../benchmarks/fixtures/cargo-test.log"),
            matcher: Matcher::Cargo,
            failed: true,
            preserve_tail: Some("test auth::test_login_timeout ... FAILED\n"),
            preserve: &["running 41 tests\n", "at ./src/auth.rs:45:5\n"],
        },
        Fixture {
            label: "npm/Jest: 40 pass / 1 fail",
            input: include_bytes!("../benchmarks/fixtures/npm-jest.log"),
            matcher: Matcher::NpmTest,
            failed: true,
            preserve_tail: Some("FAIL tests/auth.test.js\n"),
            preserve: &["at Object.toBe (tests/auth.test.js:42:25)\n"],
        },
        Fixture {
            label: "git diff: 3 files",
            input: include_bytes!("../benchmarks/fixtures/git-diff.patch"),
            matcher: Matcher::GitDiff,
            failed: false,
            preserve_tail: None,
            preserve: &[
                "--- a/src/auth.rs\n+++ b/src/auth.rs\n",
                "--- a/src/billing.rs\n+++ b/src/billing.rs\n",
                "--- a/tests/account_service.rs\n+++ b/tests/account_service.rs\n",
                "+    // An oversized discount must not underflow.\n",
                "+    subtotal.saturating_sub(discount)\n",
            ],
        },
        Fixture {
            label: "rg -n: 24 matches / 3 files",
            input: include_bytes!("../benchmarks/fixtures/rg-numbered.log"),
            matcher: Matcher::Search,
            failed: false,
            preserve_tail: None,
            preserve: &[
                "src/services/authentication/session_management.rs:\n",
                "src/services/billing/invoice_calculation.rs:\n",
                "tests/integration/account_service_endpoints.rs:\n",
                "  10:    // TODO: verify request timeout before retrying.\n",
                "  71:    // TODO: preserve the caller's request identifier.\n",
            ],
        },
        Fixture {
            label: "unknown command: passthrough",
            input: include_bytes!("../benchmarks/fixtures/unknown-cli.log"),
            matcher: Matcher::Passthrough,
            failed: false,
            preserve_tail: None,
            preserve: &[],
        },
    ];

    println!("Handcrafted fixtures; bytes only, no truncation.\n");
    println!("| Fixture | Raw bytes | Output bytes | Saved bytes | Reduction |");
    println!("| --- | ---: | ---: | ---: | ---: |");
    for fixture in fixtures {
        let output = minify(fixture.input, fixture.matcher, fixture.failed, None);
        let raw_text = std::str::from_utf8(fixture.input).expect("fixture must be UTF-8");
        let output_text = std::str::from_utf8(&output).expect("fixture output must be UTF-8");
        assert!(
            output.len() <= fixture.input.len(),
            "{} expanded",
            fixture.label
        );
        for text in fixture.preserve {
            assert!(
                output_text.contains(text),
                "{} lost {text:?}",
                fixture.label
            );
        }
        if let Some(boundary) = fixture.preserve_tail {
            let start = raw_text
                .find(boundary)
                .expect("fixture lacks failure boundary");
            assert!(
                output_text.ends_with(&raw_text[start..]),
                "{} changed failure output",
                fixture.label
            );
        }
        if fixture.matcher == Matcher::Passthrough {
            assert_eq!(output, fixture.input, "unknown output must be byte-exact");
        }
        let saved = fixture.input.len() - output.len();
        let reduction = saved as f64 * 100.0 / fixture.input.len() as f64;
        println!(
            "| {} | {} | {} | {} | {:.1}% |",
            fixture.label,
            fixture.input.len(),
            output.len(),
            saved,
            reduction
        );
    }
    println!("\nFailure suffixes, selected source/location lines, and passthrough bytes verified.");
}
