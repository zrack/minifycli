import json
import os
from pathlib import Path
import signal
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from evaluation.confirmation import evaluate as grader


def task(rust=False):
    return {"id": "C-R1" if rust else "C-J1", "baseline_command": [sys.executable, "test/check.py"],
            "hidden_command": ["node", "evaluation/confirmation/tasks/js/C-J1-hidden.mjs", "WORKSPACE"],
            "evaluation": {"production_globs": ["src/**/*.rs"] if rust else ["lib/**/*.js"],
                           "protected_test_globs": ["test/**", "src/**/tests.rs"]}}


class RustRestorationTests(unittest.TestCase):
    def test_nonterminal_inline_tests_restored_without_erasing_following_production(self):
        before = b'fn first()->i32{0}\n#[cfg(test)]\nmod tests { #[test] fn original(){assert!(false);} }\nfn last()->i32{0}\n'
        candidate = before.replace(b'{0}', b'{1}').replace(b'assert!(false)', b'assert!(true)')
        restored, changed, tests = grader._restore_rust(before, candidate)
        self.assertIn(b'fn first()->i32{1}', restored)
        self.assertIn(b'fn last()->i32{1}', restored)
        self.assertIn(b'assert!(false)', restored)
        self.assertTrue(changed and tests)

    def test_out_of_line_declarations_are_original_and_new_test_module_is_removed(self):
        before = b'#[cfg(test)]\nmod tests;\npub fn parse()->i32{0}\n'
        candidate = before.replace(b'{0}', b'{1}') + b'#[cfg(test)] mod extra { #[test] fn regression(){} }\n'
        restored, changed, tests = grader._restore_rust(before, candidate)
        self.assertIn(b'mod tests;', restored)
        self.assertNotIn(b'mod extra', restored)
        self.assertIn(b'{1}', restored)
        self.assertTrue(changed and tests)

    def test_braces_and_test_markers_in_literals_and_nested_comments_are_ignored(self):
        before = b'''fn parse<'a>(s:&'a str)->&'a str{s}
// #[cfg(test)] mod fake { }
/* outer { /* inner } */ */
const RAW: &str = r###"} #[test] {"###;
#[cfg(test)] mod tests {
 #[test] fn real(){ let s = "}"; let c = '}'; assert_eq!(s, "}"); }
}
fn after()->i32{0}
'''
        after = before.replace(b'fn after()->i32{0}', b'fn after()->i32{1}').replace(b'fn real()', b'fn modified()')
        restored, changed, _ = grader._restore_rust(before, after)
        self.assertTrue(changed)
        self.assertIn(b'fn real()', restored)
        self.assertIn(b'fn after()->i32{1}', restored)
        self.assertIn(b'r###"} #[test] {"###', restored)

    def test_test_only_changes_do_not_count_as_production_repair(self):
        before = b'fn prod(){}\n#[cfg(test)] mod test { #[test] fn old(){} }\n'
        after = before.replace(b'fn old()', b'fn renamed()')
        restored, changed, tests = grader._restore_rust(before, after)
        self.assertEqual(restored, before)
        self.assertFalse(changed)
        self.assertTrue(tests)
        restored, changed, tests = grader._restore_rust(b'fn prod(){}\n', b'fn prod(){}\n#[cfg(test)] mod new { #[test] fn x(){} }\n')
        self.assertFalse(changed)
        self.assertTrue(tests)

    def test_ambiguous_removed_or_unsupported_structures_fail_closed(self):
        before = b'#[cfg(test)] mod tests { #[test] fn old(){} }\nfn prod(){}'
        cases = [b'fn prod(){}', b'#[cfg(any(test, feature="std"))] mod tests {}',
                 b'#[cfg(test)] mod tests {}\n#[cfg(test)] mod tests {}',
                 b'#[cfg(test)] mod tests {', b'#[cfg_attr(test, inline)] fn prod(){}']
        for candidate in cases:
            with self.subTest(candidate=candidate):
                with self.assertRaises(grader.RestoreError):
                    grader._restore_rust(before, candidate)

    def test_test_functions_and_test_only_macros_can_precede_production(self):
        before = b'#[test]\n#[cfg(feature="std")]\nfn direct(){assert!(false);}\n#[cfg(test)] macro_rules! helper {()=>{{"}"}}}\nfn prod(){old()}\n'
        after = before.replace(b'false', b'true').replace(b'old()', b'new()')
        restored, changed, _ = grader._restore_rust(before, after)
        self.assertTrue(changed)
        self.assertIn(b'assert!(false)', restored)
        self.assertIn(b'new()', restored)

    def test_unchanged_crate_level_test_configuration_is_retained_verbatim(self):
        before = b'#![cfg_attr(all(test, windows), feature(std_misc))]\nfn prod(){old()}\n#[cfg(test)] mod test { #[test] fn x(){} }'
        after = before.replace(b'old()', b'new()')
        restored, changed, _ = grader._restore_rust(before, after)
        self.assertTrue(changed)
        self.assertTrue(restored.startswith(before.split(b'\n')[0]))
        with self.assertRaises(grader.RestoreError):
            grader._restore_rust(before, after.replace(b'windows', b'unix'))


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.base, self.workspace = self.root / "base", self.root / "workspace"
        for directory in (self.base, self.workspace):
            (directory / "lib").mkdir(parents=True)
            (directory / "test").mkdir()
            (directory / "lib/value.js").write_text("broken")
            (directory / "test/check.py").write_text("from pathlib import Path\nassert Path('lib/value.js').read_text() == 'fixed'\n")
            (directory / "package.json").write_text('{"untouched":true}')

    def tearDown(self):
        self.temp.cleanup()

    def evaluate(self, **options):
        hidden = lambda task, pristine, directory: [sys.executable, str(pristine / "test/check.py")]
        with patch.object(grader, "_hidden_command", side_effect=hidden):
            return grader.evaluate_task(task(), self.base, self.workspace, self.root / options.get("output", "evaluation"))

    def test_globs_match_direct_and_nested_source_but_protect_tests(self):
        policy = grader._policy(task(True))
        self.assertTrue(grader._production_path("src/lib.rs", policy))
        self.assertTrue(grader._production_path("src/ascii/mod.rs", policy))
        self.assertFalse(grader._production_path("src/ascii/tests.rs", policy))
        self.assertFalse(grader._production_path("tests/hidden.rs", policy))
        self.assertFalse(grader._production_path("src/a.rs/../../oracle", policy))
        with self.assertRaises(ValueError):
            grader._glob("../oracle/**")

    def test_real_checks_restore_original_tests_and_manifests_and_preserve_inputs(self):
        (self.workspace / "lib/value.js").write_text("fixed")
        (self.workspace / "test/check.py").write_text("# weakened candidate tests\n")
        (self.workspace / "package.json").write_text('{"tampered":true}')
        before = grader._tree_hash(grader._files(self.workspace))
        result = self.evaluate()
        self.assertTrue(result["correct_repair"], result)
        self.assertTrue(result["production_changed"])
        self.assertTrue(result["added_test_coverage"])
        self.assertTrue(result["frozen_workspace_unchanged"] and result["base_unchanged"])
        self.assertEqual(grader._tree_hash(grader._files(self.workspace)), before)
        pristine = self.root / "evaluation/pristine"
        self.assertEqual((pristine / "test/check.py").read_bytes(), (self.base / "test/check.py").read_bytes())
        self.assertEqual((pristine / "package.json").read_bytes(), (self.base / "package.json").read_bytes())
        self.assertEqual(set(result["checks"]), {"candidate_baseline", "pristine_baseline", "hidden"})

    def test_test_only_patch_and_baseline_weakening_cannot_pass(self):
        (self.workspace / "test/check.py").write_text("# every test deleted\n")
        result = self.evaluate()
        self.assertFalse(result["correct_repair"])
        self.assertFalse(result["production_changed"])
        self.assertTrue(result["checks"]["candidate_baseline"]["passed"])
        self.assertFalse(result["checks"]["pristine_baseline"]["passed"])
        self.assertFalse(result["checks"]["hidden"]["passed"])

    def test_disposable_target_cleanup_keeps_sources_and_capture_logs(self):
        directory = self.root / "check"
        target = self.root / ".targethidden"
        code = "from pathlib import Path; import os; p=Path(os.environ['CARGO_TARGET_DIR']); p.mkdir(); (p/'object').write_bytes(b'compiler'); print('preserved output')"
        result = grader._run([sys.executable, "-c", code], self.workspace, directory, target)
        self.assertTrue(result["passed"])
        self.assertTrue(result["target_cleanup"]["created"] and result["target_cleanup"]["removed"])
        self.assertFalse(target.exists())
        self.assertTrue((self.workspace / "lib/value.js").is_file())
        self.assertEqual((directory / "stdout").read_text(), "preserved output\n")
        self.assertEqual(result["streams"]["stdout"]["sha256"], grader.sha256((directory / "stdout").read_bytes()))
        shared = self.root / "shared/.targethidden"
        shared.mkdir(parents=True)
        with self.assertRaises(ValueError):
            grader._run([sys.executable, "-c", "pass"], self.workspace, self.root / "second", shared)
        self.assertTrue(shared.is_dir())

    def test_timeout_keeps_partial_logs_and_deletes_only_its_target(self):
        target = self.root / ".targethidden"
        code = "from pathlib import Path; import os,time; Path(os.environ['CARGO_TARGET_DIR']).mkdir(); print('before timeout',flush=True); time.sleep(5)"
        result = grader._run([sys.executable, "-c", code], self.workspace, self.root / "check", target, timeout=0.3)
        self.assertTrue(result["timed_out"])
        self.assertFalse(result["passed"])
        self.assertTrue(result["target_cleanup"]["removed"])
        self.assertFalse(target.exists())
        self.assertGreater(result["streams"]["stdout"]["bytes"], 0)

    def test_task_color_unset_applies_without_enabling_network_or_credentials(self):
        code = "import os; assert 'NO_COLOR' not in os.environ; assert os.environ['npm_config_offline']=='true'; assert 'OPENAI_API_KEY' not in os.environ"
        with patch.dict(os.environ, {"OPENAI_API_KEY": "not-passed"}):
            result = grader._run([sys.executable, "-c", code], self.workspace, self.root / "check", self.root / ".targethidden", environment_unset=["NO_COLOR"])
        self.assertTrue(result["passed"])
        value = task()
        value["setup"] = {"environment_unset": ["CARGO_NET_OFFLINE"]}
        with self.assertRaises(ValueError):
            grader._policy(value)

    def test_symlinks_path_overlap_and_unregistered_assets_are_rejected(self):
        (self.workspace / "lib/escape.js").symlink_to(self.root / "oracle")
        result = self.evaluate()
        self.assertFalse(result["correct_repair"])
        self.assertTrue(result["infrastructure_errors"])
        self.assertTrue((self.root / "evaluation/evaluation.json").is_file())
        with self.assertRaises(ValueError):
            grader.evaluate_task(task(), self.base, self.workspace, self.workspace / "output")
        value = task()
        value["hidden_command"] = ["node", "evaluation/debugging/evaluate.py", "WORKSPACE"]
        with self.assertRaises(ValueError):
            grader._hidden_command(value, self.workspace, self.root)

    def test_deleted_rust_test_wiring_is_a_restore_failure(self):
        base = {"src/lib.rs": b'#[cfg(test)] mod tests;\nfn prod(){}'}
        candidate = {"src/lib.rs": b'fn prod(){changed()}'}
        destination = self.root / "pristine"
        (destination / "src").mkdir(parents=True)
        (destination / "src/lib.rs").write_bytes(base["src/lib.rs"])
        errors, changed, _ = grader._overlay(base, candidate, destination, grader._policy(task(True)))
        self.assertTrue(errors)
        self.assertFalse(changed)
        self.assertEqual((destination / "src/lib.rs").read_bytes(), base["src/lib.rs"])

    def test_low_disk_before_copy_records_failure_without_commands_or_deletion(self):
        original_base = grader._tree_hash(grader._files(self.base))
        original_candidate = grader._tree_hash(grader._files(self.workspace))
        preserved = self.root / "existing-evidence.log"
        preserved.write_text("retain evidence")
        with patch.object(grader.shutil, "disk_usage", return_value=SimpleNamespace(free=grader.MINIMUM_FREE_BYTES - 1)), patch.object(grader, "_run", side_effect=AssertionError("must not run")), patch.object(grader, "_copy_source", side_effect=AssertionError("must not copy")):
            result = self.evaluate()
        self.assertFalse(result["correct_repair"])
        self.assertEqual(result["infrastructure_errors"][0]["type"], "DiskSpaceError")
        self.assertEqual(result["checks"], {})
        self.assertFalse((self.root / "evaluation/pristine").exists())
        self.assertFalse((self.root / "evaluation/candidate").exists())
        self.assertEqual(preserved.read_text(), "retain evidence")
        self.assertEqual(grader._tree_hash(grader._files(self.base)), original_base)
        self.assertEqual(grader._tree_hash(grader._files(self.workspace)), original_candidate)
        receipt = json.loads((self.root / "evaluation/disk-space.jsonl").read_text())
        self.assertEqual(receipt["observed_free_bytes"], grader.MINIMUM_FREE_BYTES - 1)
        self.assertFalse(receipt["sufficient"])
        self.assertNotIn("observed_free_bytes", json.dumps(result))

    def test_low_disk_before_next_check_preserves_prior_logs_and_disposable_data(self):
        (self.workspace / "lib/value.js").write_text("fixed")
        measurements = [grader.MINIMUM_FREE_BYTES + 1, grader.MINIMUM_FREE_BYTES + 1,
                        grader.MINIMUM_FREE_BYTES - 1]
        with patch.object(grader.shutil, "disk_usage", side_effect=[SimpleNamespace(free=value) for value in measurements]):
            result = self.evaluate()
        self.assertTrue(result["checks"]["candidate_baseline"]["passed"])
        self.assertNotIn("pristine_baseline", result["checks"])
        self.assertEqual(result["infrastructure_errors"][0]["type"], "DiskSpaceError")
        self.assertTrue((self.root / "evaluation/candidate-baseline/stdout").is_file())
        self.assertTrue((self.root / "evaluation/candidate/lib/value.js").is_file())
        self.assertTrue((self.root / "evaluation/pristine/lib/value.js").is_file())
        self.assertFalse((self.root / "evaluation/pristine-baseline/stdout").exists())
        # Direct check guard also cannot delete preexisting targets on refusal.
        existing = self.root / ".targethidden"
        existing.mkdir()
        (existing / "preserved").write_text("retain")
        with patch.object(grader.shutil, "disk_usage", return_value=SimpleNamespace(free=0)), patch.object(grader.subprocess, "Popen", side_effect=AssertionError("must not launch")):
            with self.assertRaises(grader.DiskSpaceError):
                grader._run([sys.executable, "-c", "pass"], self.workspace, self.root / "refused-check", existing)
        self.assertEqual((existing / "preserved").read_text(), "retain")


if __name__ == "__main__":
    unittest.main()
