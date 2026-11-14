import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from file_transfer import Transfer


class BatchTransferTests(unittest.TestCase):
    def test_batch_passes_all_items_and_stops_on_cancel(self):
        transfer = Transfer()
        transfer.run_connection = Mock(side_effect=lambda *args: transfer.cancel())
        with self.assertRaisesRegex(RuntimeError, '取消'):
            transfer.run_many_connection(object(), 'download', ['/a', '/b'], '.')
        self.assertEqual(transfer.run_connection.call_count, 1)

    def test_download_rejects_windows_alias_and_path_escape(self):
        for name in ('../escape', 'CON', 'file:stream', 'trailing.', 'a\\b'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                from file_transfer import local_name
                local_name(name)

    def test_local_copy_handles_multiple_items_and_cancellation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target = root / 'source', root / 'target'
            source.mkdir()
            target.mkdir()
            (source / 'a.txt').write_text('a')
            (source / 'folder').mkdir()
            (source / 'folder' / 'b.txt').write_text('b')
            transfer = Transfer()
            transfer.copy_local([source / 'a.txt', source / 'folder'], target)
            self.assertEqual((target / 'folder' / 'b.txt').read_text(), 'b')
            self.assertEqual((target / 'a.txt').read_text(), 'a')
            transfer.cancel()
            with self.assertRaisesRegex(RuntimeError, '取消'):
                transfer.copy_local([source / 'a.txt'], target)
