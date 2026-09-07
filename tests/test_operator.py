import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('profiles',Path(__file__).resolve().parents[1]/'scripts/skills-profile.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)

class ProfileTests(unittest.TestCase):
    def test_pins_and_installed_bytes_match(self):
        manifest=p.manifest()
        with tempfile.TemporaryDirectory() as tmp:
            p.install('web-review',tmp)
            installed=Path(tmp)/'.agents/skills/web-design-guidelines/references/guidelines.md'
            self.assertEqual(installed.read_bytes(),(p.REPO/'vendor/skills/web-design-guidelines/references/guidelines.md').read_bytes())
            self.assertEqual(json.loads((Path(tmp)/'.agents/dotfiles-skills.json').read_text())['revision'],manifest['revision'])
            with self.assertRaises(RuntimeError):p.install('web-review',tmp)

    def test_does_not_escape_project_through_symlink(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            (Path(tmp)/'.agents').symlink_to(outside,target_is_directory=True)
            with self.assertRaises(RuntimeError):p.install('react',tmp)
            self.assertFalse(list(Path(outside).iterdir()))

    def test_tampering_is_detected_before_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake=Path(tmp)
            (fake/'vendor/skills').mkdir(parents=True)
            (fake/'skills-lock.json').write_text(json.dumps({'files':{'SKILL.md':'bad'},'profiles':{}}))
            (fake/'vendor/skills/SKILL.md').write_text('changed')
            with patch.object(p,'REPO',fake),self.assertRaises(RuntimeError):p.manifest()
