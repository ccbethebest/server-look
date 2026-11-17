import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from server_look.files.file_transfer import Transfer
from server_look.files.transfer_progress import update_progress


class TransferProgressTests(unittest.TestCase):
    def test_nested_upload_accumulates_bytes_across_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'a').write_bytes(b'a' * 30)
            (root / 'folder').mkdir()
            (root / 'folder/b').write_bytes(b'b' * 70)
            sftp = MagicMock()
            sftp.lstat.side_effect = FileNotFoundError
            def put(src, dst, callback):
                size = Path(src).stat().st_size
                callback(size // 2, size)
                callback(size, size)
            sftp.put.side_effect = put
            connection = MagicMock()
            connection.session.client().open_sftp.return_value = sftp
            events = []
            transfer = Transfer(events.append)
            transfer.run_many_connection(connection, 'upload', [str(root / 'a'), str(root / 'folder')], '/dest')
            measured = [e for e in events if e['bytes_total'] is not None]
            self.assertEqual({e['bytes_total'] for e in measured}, {100})
            self.assertEqual([e['bytes_done'] for e in measured], sorted(e['bytes_done'] for e in measured))
            self.assertIn(30, [e['bytes_done'] for e in measured])
            self.assertEqual(events[-1], dict(completed=2, total=2, bytes_done=100, bytes_total=100, phase='transferring'))

    def test_remote_download_measures_nested_total_and_closes_scan_connection(self):
        sftp = MagicMock()
        infos = {'/folder': (stat.S_IFDIR, 0), '/folder/a': (stat.S_IFREG, 40),
                 '/b': (stat.S_IFREG, 60)}
        sftp.lstat.side_effect = lambda path: SimpleNamespace(st_mode=infos[path][0], st_size=infos[path][1])
        sftp.listdir.return_value = ['a']
        sftp.get.side_effect = lambda src, dst, callback: callback(infos[src][1], infos[src][1])
        connection = MagicMock()
        connection.session.client().open_sftp.return_value = sftp
        with tempfile.TemporaryDirectory() as folder:
            events = []
            Transfer(events.append).run_many_connection(connection, 'download', ['/folder', '/b'], folder)
        self.assertEqual(events[-1]['bytes_done'], 100)
        self.assertEqual(events[-1]['bytes_total'], 100)
        self.assertEqual(sftp.close.call_count, 3)

    def test_local_copy_reports_total_and_completed_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'src').write_bytes(b'content')
            (root / 'dst').mkdir()
            events = []
            Transfer(events.append).copy_local([root / 'src'], root / 'dst')
            self.assertEqual(events[-1]['bytes_total'], 7)
            self.assertEqual(events[-1]['bytes_done'], 7)
            self.assertEqual(events[-1]['completed'], 1)

    def test_ten_gigabyte_transfer_shows_sizes_and_percentage(self):
        bar = MagicMock()
        bar.cget.return_value = 'indeterminate'
        text = update_progress(bar, dict(completed=0, total=1, bytes_done=2_500_000_000, bytes_total=10_000_000_000))
        self.assertIn('2.50 GB', text)
        self.assertIn('10.00 GB', text)
        self.assertIn('25.0%', text)
        bar.stop.assert_called_once()
        bar.configure.assert_any_call(value=25.0)

    def test_empty_batch_only_reaches_100_when_completed(self):
        bar = MagicMock()
        self.assertIn('0.0%', update_progress(bar, dict(completed=0, total=1, bytes_done=0, bytes_total=0)))
        self.assertIn('100.0%', update_progress(bar, dict(completed=1, total=1, bytes_done=0, bytes_total=0)))


if __name__ == '__main__':
    unittest.main()
