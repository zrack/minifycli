import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("run_pilot", Path(__file__).resolve().parents[1] / "run_pilot.py")
pilot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pilot)


def stream(tokens):
    return {"tokens": {name: tokens for name in pilot.ENCODINGS}, "bytes": tokens or 0, "utf8": tokens is not None}


def trial(tokens, status=True, contract=True):
    return {"stdout": stream(tokens), "stderr": stream(0), "exit_matches_expected": status,
            "contracts": [{"id": "diagnostic", "passed": contract}], "wall_seconds": 0.1,
            "timed_out": False, "capture_complete": True}


def case(identifier, raw, mini, rtk):
    return {"id": identifier, "group": "ordinary", "same_capture": {
        "raw": {"stdout": stream(raw), "stderr": stream(0)},
        "mini": {"stdout": stream(mini), "contracts_stdout": []},
        "rtk_pipe": None if rtk is None else {"stdout": stream(rtk), "contracts_stdout": []}},
        "native": {"raw": [trial(raw)], "mini": [trial(mini)], **({"rtk": [trial(rtk)]} if rtk is not None else {})}}


class ArithmeticTests(unittest.TestCase):
    def test_zero_denominator_is_unavailable_and_expansion_is_negative(self):
        self.assertIsNone(pilot.reduction(0, 10))
        self.assertIsNone(pilot.reduction(None, 10))
        self.assertEqual(pilot.reduction(10, 15), -50.0)

    def test_common_corpus_preserves_empty_expansion_and_excludes_unsupported(self):
        result = pilot.summarize({"cases": [case("empty", 0, 0, 2), case("normal", 10, 8, 12), case("unsupported", 100, 50, None)]})
        common = result["same_capture_common"]["ordinary"]
        self.assertEqual(common["case_ids"], ["empty", "normal"])
        rtk = common["variants"]["rtk_pipe"]["encodings"]["o200k_base"]
        self.assertEqual((rtk["raw_tokens"], rtk["output_tokens"], rtk["reduction_percent"]), (10, 14, -40.0))
        mini = common["variants"]["mini"]["encodings"]["o200k_base"]
        self.assertEqual(mini["reduction_percent"], 20.0)
        native = result["native_common"]["ordinary"]
        self.assertEqual(native["case_ids"], ["empty", "normal"])
        self.assertEqual(native["variants"]["rtk"]["encodings"]["o200k_base"]["reduction_percent"], -40.0)

    def test_invalid_utf8_token_counts_stay_null(self):
        tokenizer = pilot.Tokenizer.__new__(pilot.Tokenizer)
        tokenizer.encoders = {}
        description = tokenizer.describe(b"\xff")
        self.assertFalse(description["utf8"])
        self.assertTrue(all(value is None for value in description["tokens"].values()))

    def test_invalid_pairs_are_counted_not_silently_zeroed(self):
        result = pilot.summarize({"cases": [case("invalid", None, None, None)]})
        row = result["same_capture"]["ordinary"]["mini"]["encodings"]["o200k_base"]
        self.assertEqual(row["valid_cases"], 0)
        self.assertIsNone(row["reduction_percent"])

    def test_status_and_retention_failures_remain_visible(self):
        value = case("failure", 10, 2, 1)
        value["native"]["rtk"][0] = trial(1, status=False, contract=False)
        result = pilot.summarize({"cases": [value]})
        self.assertEqual(result["native"]["ordinary"]["rtk"]["status_mismatches"], 1)
        self.assertEqual(result["native"]["ordinary"]["rtk"]["contract_failures"], 1)

    def test_failed_pipe_cannot_earn_empty_output_savings(self):
        value = case("failed-filter", 10, 8, 0)
        value["same_capture"]["rtk_pipe"]["filter_returncode"] = 1
        result = pilot.summarize({"cases": [value]})
        for name in ("mini", "rtk_pipe"):
            metric = result["same_capture_common"]["ordinary"]["variants"][name]["encodings"]["o200k_base"]
            self.assertEqual(metric["valid_cases"], 0)
            self.assertEqual(metric["excluded_cases"], 1)
            self.assertIsNone(metric["reduction_percent"])

    def test_incomplete_native_trial_is_excluded_from_every_common_variant(self):
        value = case("timeout", 10, 8, 0)
        value["native"]["rtk"][0].update(capture_complete=False, timed_out=True, exit_matches_expected=False)
        result = pilot.summarize({"cases": [value]})
        for name in ("raw", "mini", "rtk"):
            metric = result["native_common"]["ordinary"]["variants"][name]["encodings"]["o200k_base"]
            self.assertEqual(metric["paired_trials"], 0)
            self.assertEqual(metric["excluded_pairs"], 1)
            self.assertIsNone(metric["reduction_percent"])
            self.assertIsNone(result["native_common"]["ordinary"]["variants"][name]["median_wall_seconds"])
        self.assertEqual(result["native"]["ordinary"]["rtk"]["timeouts"], 1)


class SafetyAndScopeTests(unittest.TestCase):
    def test_paths_cannot_escape_roots_or_follow_outside_symlinks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "root"
            root.mkdir()
            for path in ("../outside", "/absolute", ""):
                with self.assertRaises(ValueError):
                    pilot.safe_child(root, path)
            (root / "link").symlink_to(Path(temp) / "outside")
            with self.assertRaises(ValueError):
                pilot.safe_child(root, "link/file")

    def test_stderr_only_contract_is_outside_stdout_scope(self):
        definitions = [{"id": "error", "any": ["missing target"]}]
        result = pilot.stdout_contracts(b"", b"", definitions)
        self.assertEqual(result, [{"id": "error", "eligible": False, "passed": None}])
        result = pilot.stdout_contracts(b"missing target", b"removed", definitions)
        self.assertEqual(result, [{"id": "error", "eligible": True, "passed": False}])

    def test_duplicate_case_ids_are_rejected(self):
        plan = {"repositories": [{"id": "a"}, {"id": "b"}], "cases": [
            {"id": "one", "repo": "a", "argv": ["echo"], "expected_exit": 0},
            {"id": "one", "repo": "b", "argv": ["echo"], "expected_exit": 0}]}
        with self.assertRaises(ValueError):
            pilot.validate_plan(plan)

    def test_environment_does_not_repoint_home_or_external_dashboard(self):
        env = pilot.case_environment({"HOME": "/original", "LEDGER_DASHBOARD_DIR": "/external", "FORCE_COLOR": "1"}, Path("/workspace"), Path("/private-run"))
        self.assertEqual(env["HOME"], "/original")
        self.assertNotIn("LEDGER_DASHBOARD_DIR", env)
        self.assertNotIn("FORCE_COLOR", env)
        self.assertEqual(env["RTK_TELEMETRY_DISABLED"], "1")

    def test_export_does_not_overwrite_existing_destination(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(FileExistsError):
                pilot.export({"cases": []}, Path(temp))

    def test_provenance_export_is_whitelisted(self):
        value = pilot.public_rtk_provenance({"tag": "v1", "binary_sha256": "abc", "runtime_environment": {"secret": "private"}, "private_path": "/Users/private"})
        self.assertEqual(value, {"tag": "v1", "binary_sha256": "abc"})

    def test_snapshots_are_independent_pinned_depth_two_and_do_not_edit_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            sources, run = root / "sources", root / "run"
            sources.mkdir()
            run.mkdir()
            (run / "workspaces").mkdir()
            env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null")
            repositories = []
            for name in ("one", "two"):
                source = sources / name
                pilot.git(["init", "--quiet", str(source)], env)
                for revision in range(3):
                    (source / "file.txt").write_text(str(revision) + "\n")
                    pilot.git(["add", "file.txt"], env, source)
                    pilot.git(["-c", "user.name=Evaluation fixture", "-c", "user.email=fixture@example.invalid", "commit", "--quiet", "-m", f"revision {revision}"], env, source)
                repositories.append({"id": name, "name": name, "source_name": name,
                                     "commit": pilot.git(["rev-parse", "HEAD"], env, source)})
            workspaces, metadata = pilot.prepare_workspaces({"repositories": repositories}, sources, run, env, root)
            for repository in repositories:
                source = sources / repository["id"]
                self.assertEqual(pilot.git(["rev-parse", "HEAD"], env, source), repository["commit"])
                self.assertEqual(pilot.git(["status", "--porcelain"], env, source), "")
                self.assertEqual((source / "file.txt").read_text(), "2\n")
                for scenario in ("baseline", "controlled_failure"):
                    snapshot = workspaces[(repository["id"], scenario)]
                    self.assertEqual(pilot.git(["rev-list", "--count", "HEAD"], env, snapshot), "2")
                    self.assertEqual(pilot.git(["rev-parse", "HEAD"], env, snapshot), repository["commit"])
                    self.assertFalse((snapshot / ".git/objects/info/alternates").exists())
            self.assertTrue(all(item["baseline_clean"] for item in metadata))

    def test_raw_only_preflight_never_probes_comparators_or_tokenizer(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plan = {"repositories": [{"id": "a"}, {"id": "b"}], "cases": [{"id": "raw", "repo": "a", "argv": [sys.executable, "-c", "print('retained fact')"], "expected_exit": 0, "contracts": [{"id": "fact", "any": ["retained fact"]}]}]}
            path = root / "plan.json"
            path.write_text(json.dumps(plan))
            args = __import__('argparse').Namespace(plan=path, run_root=root / "run", repositories_root=root,
                mini=root / "missing-mini", rtk=root / "missing-rtk", preflight_only=True, timeout=5)
            with patch.object(pilot, "prepare_workspaces", return_value=({("a", "baseline"): root}, [])), \
                 patch.object(pilot, "binary_metadata", side_effect=AssertionError("comparator was invoked")), \
                 patch.object(pilot, "Tokenizer", side_effect=AssertionError("tokenizer was invoked")):
                result = pilot.run(args)
            self.assertTrue(result["passed"])
            self.assertEqual(result["plan_sha256"], pilot.sha256(path.read_bytes()))
            self.assertTrue((root / "run/preflight.json").is_file())


class ExecutionTests(unittest.TestCase):
    def test_nonzero_status_and_both_streams_are_captured(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / "capture"
            result = pilot.execute([sys.executable, "-c", "import sys;print('diagnostic');print('warning',file=sys.stderr);sys.exit(17)"], Path(temp), dict(__import__('os').environ), directory, timeout=5)
            self.assertEqual(result["returncode"], 17)
            self.assertTrue(result["capture_complete"])
            self.assertEqual((directory / "stdout").read_bytes(), b"diagnostic\n")
            self.assertEqual((directory / "stderr").read_bytes(), b"warning\n")

    def test_timeout_cannot_be_reported_as_success(self):
        with tempfile.TemporaryDirectory() as temp:
            started = time.monotonic()
            result = pilot.execute([sys.executable, "-c", "import time; print('ready',flush=True);time.sleep(10)"], Path(temp), dict(__import__('os').environ), Path(temp) / "capture", timeout=0.1)
            self.assertTrue(result["timed_out"])
            self.assertFalse(result["capture_complete"])
            self.assertNotEqual(result["returncode"], 0)
            self.assertLess(time.monotonic() - started, 4)

    def test_hash_is_content_based(self):
        self.assertEqual(pilot.sha256(b"abc"), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")


if __name__ == "__main__":
    unittest.main()
