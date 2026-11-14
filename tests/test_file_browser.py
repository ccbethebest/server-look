import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock
from server_look.files.file_transfer import Transfer

class TransferProgressTests(unittest.TestCase):
    def test_reports_completed_items_without_claiming_byte_progress(self):
        updates = []
        transfer = Transfer(progress=updates.append)
        transfer.run_connection = Mock()
        transfer.run_many_connection(Mock(), 'upload', ['a', 'b'], '/target')
        self.assertEqual([u['completed'] for u in updates], [0, 1, 1, 2])
        self.assertTrue(all(u['total'] == 2 for u in updates))

class ExplorerTests(unittest.TestCase):
    def setUp(self):
        from tkinterdnd2 import TkinterDnD
        from server_look.app.server_page import ServerPage
        self.root = TkinterDnD.Tk()
        self.page = ServerPage(self.root)
    def tearDown(self):
        self.page.close()
    def test_local_metadata_and_root_navigation(self):
        local = self.page.resources.local
        self.assertEqual(tuple(local.files['columns']), ('kind', 'size', 'modified'))
        self.assertEqual(str(local.files['selectmode']), 'extended')
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / 'sample.txt').write_bytes(b'hello')
            local.path.set(tmp)
            local.browse()
            row = next(i for i, p in local.items.items() if p.name == 'sample.txt')
            values = local.files.item(row, 'values')
            self.assertIn('5.0 B', values)
            self.assertRegex(values[2], r'\d{4}-\d{2}-\d{2}')
            local.go_root()
            self.assertEqual(local.current, Path(Path(tmp).anchor))
