import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('release', Path(__file__).resolve().parents[1] / 'scripts/agent-release.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        for obj, key, value in ((r, 'HOME', self.root/'runtime'), (r.a, 'ROOT', self.root/'state')):
            p = patch.object(obj, key, value)
            p.start(); self.addCleanup(p.stop)

    def release(self, name):
        path = r.HOME/'releases'/name
        path.mkdir(parents=True)
        (path/'script.py').write_text('print("fixture")')
        r.a.save(path/'release.json', {'schema': 1, 'revision': name, 'files': r.inventory(path)})
        return path

    def test_integrity_rejects_edit_extra_file_and_symlink(self):
        for change in ('edit', 'extra', 'symlink'):
            path = self.release(change)
            if change == 'edit': (path/'script.py').write_text('changed')
            if change == 'extra':
                (path/'nested').mkdir()
                (path/'nested/release.json').write_text('hidden')
            if change == 'symlink': (path/'alias').symlink_to(path/'script.py')
            with self.assertRaises(RuntimeError): r.verify(path)

    def test_activation_and_rollback_keep_task_state(self):
        first, second = self.release('first'), self.release('second')
        r.s.persist({'jobs': {'4': {'status': 'accepted'}}})
        with patch.object(r.s, 'install') as install, contextlib.redirect_stdout(io.StringIO()):
            r.activate(first); r.activate(second); r.rollback()
        self.assertEqual((r.HOME/'current').resolve(), first)
        self.assertEqual((r.HOME/'previous').resolve(), second)
        self.assertEqual(r.s.load()['jobs']['4']['status'], 'accepted')
        self.assertEqual(install.call_count, 3)

    def test_install_failure_restores_previous_selection(self):
        first, second = self.release('first'), self.release('second')
        r.select(first)
        with patch.object(r.s, 'install', side_effect=[RuntimeError('failed'), None]):
            with self.assertRaises(RuntimeError): r.activate(second)
        self.assertEqual((r.HOME/'current').resolve(), first)
        self.assertFalse((r.HOME/'previous').exists())

    def test_active_worker_blocks_upgrade_before_selection(self):
        first, second = self.release('first'), self.release('second')
        r.select(first)
        with r.a.lock(), patch.object(r.s, 'install') as install:
            with self.assertRaises(RuntimeError): r.activate(second)
            install.assert_not_called()
        self.assertEqual((r.HOME/'current').resolve(), first)

    def test_dirty_source_refuses_build(self):
        with patch.object(r.a, 'git', return_value=' M file'):
            with self.assertRaises(RuntimeError): r.build(self.root)

    def test_log_rotation_keeps_two_backups(self):
        path = r.s.paths()[0]/'service.log'
        for value in ('first', 'second', 'third'):
            path.write_text(value); r.s.rotate_logs(limit=1)
        self.assertEqual(path.read_text(), '')
        self.assertEqual(path.with_name('service.log.1').read_text(), 'third')
        self.assertEqual(path.with_name('service.log.2').read_text(), 'second')

    def test_failed_state_flush_preserves_prior_record(self):
        path = self.root/'state.json'
        r.a.save(path, {'attempt': 1})
        with patch.object(r.a.os, 'fsync', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError): r.a.save(path, {'attempt': 2})
        self.assertEqual(json.loads(path.read_text()), {'attempt': 1})
        self.assertEqual(list(self.root.glob('state.json.*')), [])


if __name__ == '__main__': unittest.main()
