from pathlib import Path
import tempfile
import unittest
import json
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch
from server_look.remote.server_resources import delete_entries


class DeleteTests(unittest.TestCase):
    def test_deletes_selected_file_and_recursive_folder_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'keep').write_text('keep')
            (root / 'file').write_text('delete')
            (root / 'folder').mkdir()
            (root / 'folder' / 'nested').write_text('delete')
            delete_entries(str(root), ['file', 'folder'])
            self.assertEqual([p.name for p in root.iterdir()], ['keep'])

    def test_validates_entire_selection_before_deletion(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'keep'
            file.write_text('keep')
            for invalid in ('..', '.', '../outside', '/outside', 'a\\b', ''):
                with self.assertRaises(ValueError):
                    delete_entries(directory, ['keep', invalid])
                self.assertTrue(file.exists())

    def test_agent_delete_protocol(self):
        from server_look.transport.directory_channel import DIRECTORY_AGENT
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'delete me'
            target.write_text('data')
            source = Path('server_look/remote/server_resources.py').read_text(encoding='utf-8')
            requests = [dict(source=source), dict(path=directory, action='delete', names=[target.name])]
            result = subprocess.run([sys.executable, '-c', DIRECTORY_AGENT],
                input=''.join(json.dumps(r) + '\n' for r in requests), capture_output=True, text=True, check=True)
            self.assertIn('result', json.loads(result.stdout))
            self.assertFalse(target.exists())


class DeleteUITests(unittest.TestCase):
    def setUp(self):
        from tkinterdnd2 import TkinterDnD
        from server_look.app.server_page import ServerPage
        self.root = TkinterDnD.Tk()
        self.page = ServerPage(self.root)
        self.local = self.page.resources.local

    def tearDown(self):
        self.page.close()

    def test_local_cancel_preserves_selection_then_confirm_deletes(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'file'
            target.write_text('data')
            self.local.path.set(directory)
            self.local.browse()
            self.local.files.selection_set(self.local.files.get_children())
            with patch('server_look.files.local_files.messagebox.askyesno', return_value=False):
                self.local.delete_selected(False)
            self.assertTrue(target.exists())
            with patch('server_look.files.local_files.messagebox.askyesno', return_value=True), \
                    patch.object(self.local, 'launch', side_effect=lambda work, title: work()):
                self.local.delete_selected(False)
            self.assertFalse(target.exists())

    def test_remote_readonly_blocks_and_confirmation_routes_names(self):
        from unittest.mock import Mock
        request = Mock()
        self.page.connection = SimpleNamespace(close=lambda: None, directory=SimpleNamespace(request=request))
        self.page.connected_address = 'test-server'
        remote = self.page.resources
        remote.current = '/data'
        row = remote.files.insert('', 'end', text='folder')
        remote.entries[row] = {'path': '/data/folder'}
        remote.files.selection_set(row)
        self.page.readonly.set(True)
        with patch('server_look.files.local_files.messagebox.askyesno', return_value=True) as confirm, \
                patch.object(self.local, 'launch', side_effect=lambda work, title: work()):
            self.local.delete_selected(True)
            confirm.assert_not_called()
            request.assert_not_called()
            self.page.readonly.set(False)
            self.local.delete_selected(True)
            request.assert_called_once_with('/data', action='delete', names=['folder'])
