"""Exercise missing-only transfers against a filesystem-backed SFTP substitute."""
from contextlib import contextmanager
import io
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

from directory_mapping import DirectoryMapping, endpoint
from remote_search import stream_search
from table_sort import enable_sort, sort_key


class LocalSFTP:
    def __init__(self, root):
        self.root = root

    def path(self, value):
        return self.root / value.lstrip('/')

    def lstat(self, path):
        return self.path(path).lstat()

    def listdir_attr(self, path):
        return [SimpleNamespace(filename=p.name) for p in self.path(path).iterdir()]

    def mkdir(self, path):
        self.path(path).mkdir()

    def open(self, path, mode):
        return self.path(path).open('xb' if mode == 'wx' else mode)

    def remove(self, path):
        self.path(path).unlink()

    def rename(self, source, target):
        if self.path(target).exists():
            raise FileExistsError(target)
        self.path(source).rename(self.path(target))

    def posix_rename(self, source, target):
        self.path(source).replace(self.path(target))


class MappingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.local, self.remote = root / 'local', root / 'remote'
        self.local.mkdir()
        self.remote.mkdir()
        self.connection = SimpleNamespace(args=['ssh', '-p', '22', '-l', 'root', 'example.test'])
        self.record = dict(local=str(self.local), remote='/', direction='本地 → 服务器',
                           server=endpoint(self.connection))
        self.mapping = DirectoryMapping()

        @contextmanager
        def channel(connection):
            yield LocalSFTP(self.remote)
        self.mapping.channel = channel

    def test_upload_merges_directories_without_overwriting(self):
        for root in (self.local, self.remote):
            (root / 'nested').mkdir()
        (self.local / 'nested' / 'new.txt').write_text('new')
        (self.local / 'existing.txt').write_text('changed')
        (self.remote / 'existing.txt').write_text('keep')
        result = self.mapping.run(self.connection, self.record)
        self.assertIn('复制 1 个文件', result)
        self.assertEqual((self.remote / 'existing.txt').read_text(), 'keep')
        self.assertEqual((self.remote / 'nested' / 'new.txt').read_text(), 'new')

    def test_overwrite_recurses_in_both_directions_and_preserves_extra_files(self):
        for upload in (True, False):
            with self.subTest(upload=upload):
                source, target = (self.local, self.remote) if upload else (self.remote, self.local)
                for root in (source, target):
                    (root / 'nested').mkdir(exist_ok=True)
                (source / 'nested' / 'existing.txt').write_text('replacement')
                (target / 'nested' / 'existing.txt').write_text('old contents longer')
                (source / 'nested' / 'new.txt').write_text('new')
                (target / 'extra.txt').write_text('keep')
                self.record.update(overwrite=True, direction='本地 → 服务器' if upload else '服务器 → 本地')
                self.mapping.run(self.connection, self.record)
                self.assertEqual((target / 'nested' / 'existing.txt').read_text(), 'replacement')
                self.assertEqual((target / 'nested' / 'new.txt').read_text(), 'new')
                self.assertEqual((target / 'extra.txt').read_text(), 'keep')

    def test_failed_overwrite_preserves_original_and_cleans_staging_file(self):
        (self.local / 'existing.txt').write_text('replacement')
        (self.remote / 'existing.txt').write_text('original')
        self.record['overwrite'] = True
        with patch.object(LocalSFTP, 'posix_rename', side_effect=OSError('unsupported')):
            with self.assertRaisesRegex(OSError, 'unsupported'):
                self.mapping.run(self.connection, self.record)
        self.assertEqual((self.remote / 'existing.txt').read_text(), 'original')
        self.assertEqual([p.name for p in self.remote.iterdir()], ['existing.txt'])

    def test_selected_download_overwrites_only_selected_files(self):
        for root in (self.local, self.remote):
            (root / 'a.txt').write_text('local' if root == self.local else 'remote')
            (root / 'b.txt').write_text('local' if root == self.local else 'remote')
        self.record.update(overwrite=True, direction='服务器 → 本地')
        self.mapping.run(self.connection, self.record, ['/a.txt'])
        self.assertEqual((self.local / 'a.txt').read_text(), 'remote')
        self.assertEqual((self.local / 'b.txt').read_text(), 'local')

    def test_download_selected_descendant_and_existing_file(self):
        (self.remote / 'nested').mkdir()
        (self.remote / 'nested' / 'new.txt').write_text('new')
        (self.remote / 'other.txt').write_text('other')
        self.record['direction'] = '服务器 → 本地'
        self.mapping.run(self.connection, self.record, ['/nested/new.txt'])
        self.assertEqual((self.local / 'nested' / 'new.txt').read_text(), 'new')
        self.assertFalse((self.local / 'other.txt').exists())
        (self.remote / 'nested' / 'new.txt').write_text('changed')
        self.mapping.run(self.connection, self.record, ['/nested/new.txt'])
        self.assertEqual((self.local / 'nested' / 'new.txt').read_text(), 'new')

    def test_rejects_outside_selection_wrong_server_and_cancel(self):
        with self.assertRaises(ValueError):
            self.mapping.run(self.connection, self.record, [str(self.local.parent / 'outside')])
        with self.assertRaises(ValueError):
            self.mapping.run(self.connection, dict(self.record, server='other'))
        self.mapping.cancel()
        with self.assertRaisesRegex(RuntimeError, '取消'):
            self.mapping.run(self.connection, self.record)

    def test_download_rejects_windows_name_collisions(self):
        self.record['direction'] = '服务器 → 本地'
        with patch.object(LocalSFTP, 'listdir_attr', return_value=[
                SimpleNamespace(filename='Model.bin'), SimpleNamespace(filename='model.bin')]):
            with self.assertRaisesRegex(ValueError, '同名'):
                self.mapping.run(self.connection, self.record)

    def test_selected_source_junction_cannot_escape_root(self):
        import os
        import subprocess
        if os.name != 'nt':
            self.skipTest('Windows directory junction')
        outside = self.local.parent / 'outside'
        outside.mkdir()
        (outside / 'secret.txt').write_text('secret')
        link = self.local / 'linked'
        subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(outside)],
                       check=True, capture_output=True)
        try:
            with self.assertRaisesRegex(ValueError, '链接'):
                self.mapping.run(self.connection, self.record, [str(link / 'secret.txt')])
            self.assertFalse((self.remote / 'linked').exists())
        finally:
            link.rmdir()


class SortTests(unittest.TestCase):
    def test_units_and_natural_names(self):
        self.assertLess(sort_key('900 MiB'), sort_key('1 GiB'))
        self.assertLess(sort_key('task2'), sort_key('task10'))
        self.assertLess(sort_key('2026-01-01'), sort_key('2026-10-01'))

    def test_three_states_and_refresh(self):
        root = tk.Tk()
        root.withdraw()
        try:
            tree = ttk.Treeview(root, columns=('size',))
            tree.heading('#0', text='名称')
            tree.heading('size', text='大小')
            sorting = enable_sort(tree)
            rows = [tree.insert('', 'end', text=name) for name in ('task10', 'task2', 'task1')]
            sorting.refreshed()
            sorting.toggle('#0')
            self.assertEqual(tree.get_children(), tuple(reversed(rows)))
            sorting.toggle('#0')
            self.assertEqual(tree.get_children(), tuple(rows))
            sorting.toggle('#0')
            self.assertEqual(tree.get_children(), tuple(rows))
            sorting.toggle('#0')
            tree.delete(*rows)
            new = [tree.insert('', 'end', text=name) for name in ('b', 'a')]
            sorting.refreshed()
            self.assertEqual(tree.get_children(), tuple(reversed(new)))
        finally:
            root.destroy()


class RemoteSearchTests(unittest.TestCase):
    def process(self, text):
        return SimpleNamespace(stdin=io.StringIO(), stdout=io.StringIO(text),
                               poll=lambda: 0, wait=lambda timeout: None)

    def test_batches_arrive_before_completion(self):
        row = dict(name='model.bin', path='/model.bin', directory=False)
        lines = '\n'.join([json.dumps({'batch': [row]}), json.dumps({'done': dict(
            reason='完成', scanned=1, skipped=0, elapsed=0.1)})])
        batches = []
        with patch('remote_search.subprocess.Popen', return_value=self.process(lines)):
            result = stream_search(SimpleNamespace(session=None, args=['ssh']), 'command', {},
                                   threading.Event(), batches.append)
        self.assertEqual(batches, [[row]])
        self.assertEqual(result['results'], [row])

    def test_remote_errors_are_visible(self):
        with patch('remote_search.subprocess.Popen', return_value=self.process('Permission denied')):
            with self.assertRaisesRegex(RuntimeError, 'Permission denied'):
                stream_search(SimpleNamespace(session=None, args=['ssh']), 'command', {},
                              threading.Event(), lambda rows: None)
