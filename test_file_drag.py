"""Native TkDND registration and drag callbacks with real local files."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tkinterdnd2 import TkinterDnD
from server_page import ServerPage


class FileDragTests(unittest.TestCase):
    def setUp(self):
        self.root = TkinterDnD.Tk()
        self.page = ServerPage(self.root)
        self.local = self.page.resources.local
        self.remote = self.page.resources

    def tearDown(self):
        self.page.close()

    def test_multi_selection_and_native_bindings(self):
        tree = self.remote.files
        self.assertEqual(str(tree['selectmode']), 'extended')
        self.assertNotIn('TkDND_Drag1', tree.bindtags())
        self.assertTrue(tree.dnd_bind('<<DragInitCmd>>'))
        self.assertTrue(self.local.files.dnd_bind('<<Drop>>'))
        a, b = [tree.insert('', 'end', text=name) for name in ('a', 'b')]
        tree.selection_set(a, b)
        with patch.object(tree, 'identify_row', return_value=a):
            self.assertEqual(self.local.drag.press(SimpleNamespace(y=1, state=0, x_root=0, y_root=0)), 'break')
        self.assertEqual(tree.selection(), (a, b))

    def test_direct_drag_downloads_all_then_reuses_ready_files(self):
        tree = self.remote.files
        self.page.connection = SimpleNamespace(close=lambda: None)
        for index, name in enumerate(('中文 name.txt', 'folder')):
            iid = tree.insert('', 'end', text=name)
            self.remote.entries[iid] = {'path': '/' + name, 'size': index, 'modified': 'today'}
            tree.selection_add(iid)
        with tempfile.TemporaryDirectory() as directory:
            def download(connection, direction, sources, destination):
                for source in sources:
                    (Path(destination) / Path(source).name).write_text('content')
            with patch('file_drag.tempfile.mkdtemp', return_value=directory), \
                    patch('file_drag.Transfer.run_many_connection', side_effect=download) as copy:
                result = self.local.drag.begin(None)
                self.assertEqual(result[:2], ('copy', 'DND_Files'))
                self.assertEqual(len(result[2]), 2)
                self.assertTrue(all(Path(p).exists() for p in result[2]))
                self.assertEqual(self.local.drag.begin(None), result)
                self.assertEqual(copy.call_count, 1)

    def test_internal_drag_targets_local_folder_without_staging(self):
        self.page.connection = SimpleNamespace(close=lambda: None)
        row = self.remote.files.insert('', 'end', text='model.bin')
        self.remote.entries[row] = {'path': '/model.bin'}
        self.remote.files.selection_set(row)
        with tempfile.TemporaryDirectory() as directory:
            with patch('file_drag.messagebox.askyesno', return_value=True), \
                    patch('file_drag.tempfile.mkdtemp') as staging, \
                    patch('file_drag.Transfer.run_many_connection') as transfer, \
                    patch.object(self.local, 'launch', side_effect=lambda work, title: work()):
                self.local.drag.download_to(Path(directory))
                transfer.assert_called_once_with(self.page.connection, 'download',
                                                ['/model.bin'], Path(directory).as_posix())
                staging.assert_not_called()

    def test_drop_copies_multiple_paths_with_spaces_and_unicode(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = (root / 'a b.txt', root / '中文.txt')
            for path in paths:
                path.write_text('test')
            destination = root / 'target'
            destination.mkdir()
            self.local.current = destination
            data = self.root.tk.call('list', *(str(p) for p in paths))
            event = SimpleNamespace(data=data, y_root=-100)
            with patch('file_drag.messagebox.askyesno', return_value=True), \
                    patch.object(self.local, 'launch', side_effect=lambda work, title: work()):
                self.assertEqual(self.local.drag.drop(event), 'copy')
            self.assertEqual(sorted(p.name for p in destination.iterdir()), sorted(p.name for p in paths))

    def test_local_drag_exports_selected_files_without_download(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / name for name in ('中文 a.txt', 'b.txt')]
            self.local.files.delete(*self.local.files.get_children())
            for path in paths:
                path.write_text('data')
                row = self.local.files.insert('', 'end', text=path.name)
                self.local.items[row] = path
                self.local.files.selection_add(row)
            self.assertEqual(self.local.drag.begin_local(None), ('copy', 'DND_Files', tuple(map(str, paths))))

    def test_remote_drop_uploads_batch_to_hovered_folder_and_respects_readonly(self):
        self.page.connection = SimpleNamespace(close=lambda: None)
        self.page.connected_address = 'test-server'
        self.page.readonly.set(False)
        self.remote.current = '/current'
        row = self.remote.files.insert('', 'end', text='folder')
        self.remote.entries[row] = {'path': '/current/folder', 'is_dir': True}
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / name for name in ('a b.txt', '中文.txt')]
            for path in paths:
                path.write_text('data')
            event = SimpleNamespace(data=self.root.tk.call('list', *map(str, paths)), y_root=1)
            with patch.object(self.remote.files, 'identify_row', return_value=row), \
                    patch('file_drag.messagebox.askyesno', return_value=True), \
                    patch.object(self.local, 'launch', side_effect=lambda work, title: work()), \
                    patch('file_drag.Transfer.run_many_connection') as upload:
                self.assertEqual(self.local.drag.upload(event), 'copy')
                self.assertEqual(upload.call_args.args[1:], ('upload', [p.as_posix() for p in paths], '/current/folder'))
                self.page.readonly.set(True)
                self.assertEqual(self.local.drag.upload(event), 'refuse_drop')
                self.assertEqual(upload.call_count, 1)
