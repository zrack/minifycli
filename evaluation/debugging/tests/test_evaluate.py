import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / 'evaluate.py'
spec = importlib.util.spec_from_file_location('debugging_evaluate', MODULE)
evaluate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluate)


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.base = self.root / 'base'
        self.candidate = self.root / 'frozen'
        self.base.mkdir()
        (self.base / 'lib').mkdir()
        (self.base / 'lib/subject.js').write_text('bug\n')
        (self.base / 'test').mkdir()
        (self.base / 'test/original.txt').write_text('pristine\n')
        (self.base / 'package.json').write_text('{"scripts":{"test":"original"}}\n')
        (self.base / 'node_modules').mkdir()
        (self.base / 'node_modules/dep').write_text('dependency\n')
        shutil.copytree(self.base, self.candidate)
        self.task = {'id':'JX', 'upstream_test_paths':['test/original.txt'],
                     'baseline_command':[sys.executable,'-c',
                         "from pathlib import Path; assert Path('test/original.txt').read_text() == 'pristine\\n'; Path('local-check-artifact').write_text('written only in copy')"],
                     'hidden_command':[sys.executable,'-c',
                         "from pathlib import Path; import sys; assert (Path(sys.argv[1])/'lib/subject.js').read_text() == 'fixed\\n'",'WORKSPACE']}

    def tearDown(self):
        self.temp.cleanup()

    def run_evaluation(self):
        return evaluate.evaluate_task(self.task, self.base, self.candidate, self.root/'evaluation')

    def test_valid_fix_checked_in_copies_and_frozen_tree_unchanged(self):
        (self.candidate/'lib/subject.js').write_text('fixed\n')
        (self.candidate/'test/new.txt').write_text('regression\n')
        result = self.run_evaluation()
        self.assertTrue(result['correct_repair'])
        self.assertTrue(result['added_test_coverage'])
        self.assertTrue(result['frozen_workspace_unchanged'])
        self.assertFalse((self.candidate/'local-check-artifact').exists())
        self.assertEqual((self.root/'evaluation/pristine/test/original.txt').read_text(),'pristine\n')
        self.assertEqual((self.root/'evaluation/candidate/node_modules/dep').read_text(),'dependency\n')
        self.assertFalse((self.root/'evaluation/candidate/node_modules').is_symlink())
        # Logs/patches are inspectable but the returned metadata contains no code.
        self.assertNotIn('fixed\\n', json.dumps(result))
        self.assertEqual(result['patch']['sha256'],evaluate.sha256((self.root/'evaluation/candidate.patch').read_bytes()))

    def test_unchanged_source_cannot_pass(self):
        result = self.run_evaluation()
        self.assertFalse(result['production_changed'])
        self.assertFalse(result['correct_repair'])
        self.assertEqual(result['checks']['hidden']['exit_code'],1)

    def test_original_test_weakening_is_detected_in_candidate_suite(self):
        (self.candidate/'lib/subject.js').write_text('fixed\n')
        (self.candidate/'test/original.txt').write_text('weakened\n')
        result = self.run_evaluation()
        self.assertFalse(result['checks']['candidate_baseline']['passed'])
        self.assertTrue(result['checks']['pristine_baseline']['passed'])
        self.assertFalse(result['correct_repair'])

    def test_candidate_manifest_changes_do_not_replace_pristine_manifest(self):
        (self.candidate/'lib/subject.js').write_text('fixed\n')
        (self.candidate/'package.json').write_text('{"scripts":{"test":"skip"}}\n')
        result = self.run_evaluation()
        self.assertEqual((self.root/'evaluation/pristine/package.json').read_text(),(self.base/'package.json').read_text())
        self.assertTrue(result['correct_repair'])

    def test_dependency_internal_links_stay_local_after_copy(self):
        modules=self.base/'node_modules'
        (modules/'pkg').mkdir()
        (modules/'pkg/cli').write_text('local dependency')
        (modules/'.bin').mkdir()
        (modules/'.bin/cli').symlink_to('../pkg/cli')
        (self.candidate/'lib/subject.js').write_text('fixed\n')
        result=self.run_evaluation()
        copied=self.root/'evaluation/candidate/node_modules/.bin/cli'
        self.assertTrue(result['correct_repair'])
        self.assertTrue(copied.is_symlink())
        self.assertEqual(copied.resolve(),(self.root/'evaluation/candidate/node_modules/pkg/cli').resolve())
        copied.write_text('changed privately')
        self.assertEqual((modules/'pkg/cli').read_text(),'local dependency')

    def test_distinct_empty_npm_config_files(self):
        directory=self.root/'env';directory.mkdir()
        env=evaluate._environment(directory,directory/'target')
        self.assertNotEqual(env['npm_config_userconfig'],env['npm_config_globalconfig'])
        self.assertEqual(Path(env['npm_config_userconfig']).read_bytes(),b'')
        self.assertEqual(Path(env['npm_config_globalconfig']).read_bytes(),b'')

    def test_output_directory_inside_frozen_input_is_rejected(self):
        with self.assertRaises(ValueError):
            evaluate.evaluate_task(self.task,self.base,self.candidate,self.candidate/'evaluation')
        self.assertFalse((self.candidate/'evaluation').exists())

    def test_output_directory_is_exclusive(self):
        (self.root/'evaluation').mkdir()
        with self.assertRaises(FileExistsError):
            self.run_evaluation()

    def test_timeout_is_not_correctness_success(self):
        (self.candidate/'lib/subject.js').write_text('fixed\n')
        self.task['baseline_command']=[sys.executable,'-c','import time; time.sleep(2)']
        with patch.object(evaluate,'COMMAND_TIMEOUT_SECONDS',0.05):
            result=self.run_evaluation()
        self.assertTrue(result['checks']['candidate_baseline']['timed_out'])
        self.assertFalse(result['correct_repair'])

    def test_missing_program_is_explicit_infrastructure_evidence(self):
        self.task['baseline_command']=['/nonexistent-evaluation-command']
        result=self.run_evaluation()
        self.assertIsNotNone(result['checks']['candidate_baseline']['spawn_error'])
        self.assertIsNone(result['checks']['candidate_baseline']['exit_code'])
        self.assertFalse(result['correct_repair'])

    def prepare_rust(self):
        for folder in [self.base,self.candidate]:
            (folder/'src').mkdir()
            (folder/'src/lib.rs').write_bytes(b'fn production() { buggy(); }\n#[cfg(test)]\nmod tests { fn original() {} }\n')
        self.task['id']='RX'
        self.task['upstream_test_paths']=['src/lib.rs']
        self.task['baseline_command']=[sys.executable,'-c',"from pathlib import Path; assert b'fn original()' in Path('src/lib.rs').read_bytes()"]
        self.task['hidden_command']=[sys.executable,'-c',"from pathlib import Path; import sys; assert b'fixed();' in (Path(sys.argv[1])/'src/lib.rs').read_bytes()",'WORKSPACE']

    def test_rust_restores_original_test_suffix_without_erasing_fix(self):
        self.prepare_rust()
        (self.candidate/'src/lib.rs').write_bytes(b'fn production() { fixed(); }\n#[cfg(test)]\nmod tests { fn original() {} fn added() {} }\n')
        result=self.run_evaluation()
        self.assertTrue(result['correct_repair'])
        self.assertTrue(result['added_test_coverage'])
        restored=(self.root/'evaluation/pristine/src/lib.rs').read_bytes()
        self.assertIn(b'fixed();',restored)
        self.assertIn(b'fn original()',restored)
        self.assertNotIn(b'fn added()',restored)

    def test_rust_missing_original_marker_fails_closed(self):
        self.prepare_rust()
        (self.candidate/'src/lib.rs').write_bytes(b'fn production() { fixed(); }\n')
        result=self.run_evaluation()
        self.assertFalse(result['correct_repair'])
        self.assertTrue(result['restore_errors'])
        self.assertNotIn('hidden',result['checks'])

    def test_rust_multiple_markers_fails_closed(self):
        self.prepare_rust()
        with (self.candidate/'src/lib.rs').open('ab') as file:
            file.write(b'#[cfg(test)]\nmod test { }\n')
        result=self.run_evaluation()
        self.assertFalse(result['correct_repair'])
        self.assertTrue(result['infrastructure_errors'] or result['restore_errors'])

    def test_test_only_rust_change_is_not_production_repair(self):
        self.prepare_rust()
        (self.candidate/'src/lib.rs').write_bytes(b'fn production() { buggy(); }\n#[cfg(test)]\nmod tests { fn original() {} fn added() {} }\n')
        result=self.run_evaluation()
        self.assertFalse(result['production_changed'])
        self.assertFalse(result['correct_repair'])


if __name__=='__main__':
    unittest.main()
