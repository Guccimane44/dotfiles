import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('expertise', Path(__file__).resolve().parents[1] / 'scripts/agent-expertise.py')
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)


class ExpertiseTests(unittest.TestCase):
    def test_pin_and_bounded_read(self):
        _, data = e.verify()
        self.assertEqual(data['revision'], '226c8d35fb6ea3ed55467753dba6dea2b5fd5778')
        text = e.read_document('AGENTS.md', 2, 3)
        self.assertIn('4: ', text)
        self.assertNotIn('\n5: ', text)
        self.assertIn(data['revision'], text)

    def test_invalid_paths_and_ranges(self):
        for name in ('../AGENTS.md', '/etc/passwd', 'missing.md', 'LICENSE'):
            with self.assertRaises(RuntimeError): e.read_document(name)
        for start, lines in ((0, 1), (1, 0), (1, 201)):
            with self.assertRaises(RuntimeError): e.read_document('AGENTS.md', start, lines)

    def test_tampering_and_symlinks_block_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / 'expertise'
            shutil.copytree(e.BASE, dest)
            file = dest / 'harness-engineering/README.md'
            original = file.read_bytes()
            with patch.object(e, 'BASE', dest):
                file.write_text('Changed')
                with self.assertRaises(RuntimeError): e.read_document('AGENTS.md')
                file.write_bytes(original)
                file.unlink()
                file.symlink_to('/etc/passwd')
                with self.assertRaises(RuntimeError): e.read_document('AGENTS.md')
