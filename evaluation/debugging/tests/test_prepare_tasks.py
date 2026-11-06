import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / 'prepare_tasks.py'
spec = importlib.util.spec_from_file_location('debugging_prepare_tasks', MODULE)
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class PreparationHelperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def archive(self, name, *, symlink=False):
        path=self.root/'source.tar'
        with tarfile.open(path,'w') as archive:
            item=tarfile.TarInfo(name)
            if symlink:
                item.type=tarfile.SYMTYPE;item.linkname='/outside'
                archive.addfile(item)
            else:
                item.size=6;archive.addfile(item,io.BytesIO(b'source'))
        return path

    def test_history_free_source_archive_extracts(self):
        prepare.extract_archive(self.archive('lib/source.js'),self.root/'export')
        self.assertEqual((self.root/'export/lib/source.js').read_bytes(),b'source')
        self.assertFalse((self.root/'export/.git').exists())

    def test_archive_traversal_is_rejected(self):
        with self.assertRaises(ValueError):
            prepare.extract_archive(self.archive('../escape'),self.root/'export')

    def test_archive_links_are_rejected(self):
        with self.assertRaises(ValueError):
            prepare.extract_archive(self.archive('link',symlink=True),self.root/'export')

    def test_dependency_relative_link_stays_inside_new_physical_tree(self):
        deps=self.root/'deps';(deps/'pkg').mkdir(parents=True);(deps/'.bin').mkdir()
        (deps/'pkg/cli').write_text('dependency');(deps/'.bin/cli').symlink_to('../pkg/cli')
        destination=self.root/'workspace';destination.mkdir()
        prepare.copy_dependencies(deps,destination)
        link=destination/'node_modules/.bin/cli'
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.resolve(),(destination/'node_modules/pkg/cli').resolve())
        link.write_text('separate copy')
        self.assertEqual((deps/'pkg/cli').read_text(),'dependency')

    def test_dependency_external_link_is_rejected(self):
        deps=self.root/'deps';deps.mkdir();(deps/'external').symlink_to('/outside')
        destination=self.root/'workspace';destination.mkdir()
        with self.assertRaises(ValueError):
            prepare.copy_dependencies(deps,destination)

    def test_distinct_config_files_and_disabled_git_credentials(self):
        env=prepare.environment(self.root,self.root/'cargo',self.root/'rustup')
        self.assertNotEqual(env['npm_config_userconfig'],env['npm_config_globalconfig'])
        self.assertEqual(Path(env['npm_config_userconfig']).read_bytes(),b'')
        self.assertEqual(env['GIT_CONFIG_KEY_0'],'credential.helper')
        self.assertEqual(env['GIT_CONFIG_VALUE_0'],'')
        self.assertEqual(env['GIT_TERMINAL_PROMPT'],'0')

    def test_existing_destination_is_never_modified(self):
        with self.assertRaises(FileExistsError):
            prepare.prepare(self.root,self.root/'cargo',self.root/'rustup',qualify=False)
        self.assertEqual(list(self.root.iterdir()),[])

    def test_registered_qualification_statuses_cover_all_snapshots(self):
        self.assertEqual(len(prepare.load_tasks()),6)
        expected=prepare.qualification_statuses()
        self.assertEqual(len(expected),24)
        for identifier in ['R1','R2','R3','J1','J2','J3']:
            self.assertEqual(expected[identifier,'base','baseline'],0)
            self.assertNotEqual(expected[identifier,'base','hidden'],0)
            self.assertEqual(expected[identifier,'oracle','baseline'],0)
            self.assertEqual(expected[identifier,'oracle','hidden'],0)


if __name__=='__main__':
    unittest.main()
