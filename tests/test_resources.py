import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from server_look.remote import server_resources as resources


class ResourceTests(unittest.TestCase):
    def test_directory_listing_includes_hidden_files_and_directories(self):
        with tempfile.TemporaryDirectory() as temp:
            Path(temp, 'folder').mkdir()
            Path(temp, '.hidden').write_text('abc')
            result = resources.list_directory(temp)
            self.assertEqual(result['path'], os.path.realpath(temp))
            entries = {entry['name']: entry for entry in result['entries']}
            self.assertTrue(entries['folder']['is_dir'])
            self.assertEqual(entries['.hidden']['size'], 3)

    def test_invalid_directory_is_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp, 'file')
            file.touch()
            with self.assertRaises(NotADirectoryError):
                resources.list_directory(str(file))

    def test_mount_paths_decode_linux_escapes(self):
        self.assertEqual(resources.decode_mount('/mnt/my\\040disk'), '/mnt/my disk')

    def test_disk_collection_keeps_network_mounts_and_excludes_virtual_filesystems(self):
        output = ('Filesystem Type 1B-blocks Used Available Use% Mounted on\n'
                  '/dev/sda ext4 1000 400 600 40% /\n'
                  'server:/share nfs4 2000 1000 1000 50% /mnt/share\n'
                  'tmpfs tmpfs 100 0 100 0% /run\n')
        with patch('server_look.remote.server_resources.subprocess.run') as run:
            run.return_value.stdout = output
            run.return_value.returncode = 0
            rows = resources.disks()
        self.assertEqual([row['mount'] for row in rows], ['/', '/mnt/share'])

    def test_directory_limits_large_listing(self):
        result = resources.list_directory(str(Path(__file__).parent), limit=1)
        self.assertEqual(len(result['entries']), 1)
        self.assertTrue(result['truncated'])

    def test_relative_path_is_rejected(self):
        with self.assertRaises(ValueError):
            resources.list_directory('../')

    def test_numeric_npu_models(self):
        raw = '| 0 910 | OK | 90 |\n| 1 | Ascend950 | OK | 90 |'
        self.assertEqual(resources.npu_configuration(raw)['NPU 数量'], '2')

    def test_npu_models_in_both_driver_layouts(self):
        compact = '| 0     910B4-1             | OK            | 93.2 |'
        modern = '| 1      | Ascend950DT      | Alarm         | 765 |'
        self.assertEqual(resources.npu_configuration(compact)['NPU 型号'], '910B4-1')
        self.assertEqual(resources.npu_configuration(modern)['NPU 1'], 'Ascend950DT · 健康状态 Alarm')


if __name__ == '__main__':
    unittest.main()
