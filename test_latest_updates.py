"""Regression checks for native SFTP, accelerator detection and search metadata."""
import io
import json
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from client_core import REMOTE
from directory_mapping import ProcessSocket
from file_search import directory_size, run_search


class UpdateTests(unittest.TestCase):
    def test_native_socket_initializes_real_paramiko_client(self):
        import paramiko
        process = SimpleNamespace(stdin=io.BytesIO(),
                                  stdout=io.BytesIO(struct.pack('>IBI', 5, 2, 3)),
                                  poll=lambda: 0, wait=lambda timeout: None)
        with patch('directory_mapping.subprocess.Popen', return_value=process):
            client = paramiko.SFTPClient(ProcessSocket(['ssh', 'host']))
            client.close()
        self.assertTrue(process.stdin.closed)

    def test_ascend_idle_does_not_require_nvidia_hardware(self):
        request = {'action': 'idle', 'source': "def collect_accelerators():\n return '| 0 910B | OK |', {}, {}, []",
                   'resource_source': Path('server_resources.py').read_text(encoding='utf-8')}
        output = io.StringIO()
        with patch('sys.stdin', io.StringIO(json.dumps(request))), patch('sys.stdout', output):
            exec(REMOTE, {})
        self.assertEqual(json.loads(output.getvalue()), {'state': 'idle', 'used': 0, 'total': 1, 'idle': True, 'errors': []})

    def test_snapshot_preserves_launchers_and_children_without_siblings(self):
        rows = {pid: dict(pid=pid, ppid=ppid, container='', npu={'0': 1} if pid == 3 else {})
                for pid, ppid in [(1, 0), (2, 1), (3, 2), (4, 3), (5, 2), (6, 1)]}
        request = {'action': 'snapshot', 'source': 'def collect():\n return ' + repr({'processes': rows}),
                   'resource_source': 'def collect_resources(raw):\n return {"hardware": {}}'}
        output = io.StringIO()
        with patch('sys.stdin', io.StringIO(json.dumps(request))), patch('sys.stdout', output):
            exec(REMOTE, {})
        self.assertEqual(set(json.loads(output.getvalue())['processes']), {'1', '2', '3', '4'})

    def test_search_metadata_and_optional_directory_totals(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root, 'folder')
            folder.mkdir()
            (folder / 'data.bin').write_bytes(b'12345')
            result = run_search(root, 'folder', directory_sizes=True)
            self.assertEqual(result['results'][0]['size'], 5)
            self.assertGreater(result['results'][0]['modified'], 0)
            self.assertTrue(result['results'][0]['size_complete'])
            self.assertIsNone(run_search(root, 'folder')['results'][0]['size'])
            self.assertEqual(directory_size(root, limit=1), (0, False))

    def test_task_relations_keep_ancestors_and_descendants_only(self):
        from task_relations import relation_rows
        rows = {str(pid): dict(pid=pid, ppid=ppid) for pid, ppid in [(1, 0), (2, 1), (3, 2), (4, 3), (5, 2)]}
        self.assertEqual([row['pid'] for row, _ in relation_rows(rows, rows['3'])], [1, 2, 3, 4])
        rows['1']['ppid'] = 4
        self.assertEqual(len(relation_rows(rows, rows['3'])), 4)

    def test_remote_picker_reuses_connection_and_cache(self):
        import tkinter as tk
        from remote_directory_dialog import RemoteDirectoryDialog
        import time
        root = tk.Tk()
        root.withdraw()
        calls, chosen = [], []
        def request(action, **values):
            calls.append((action, values['path']))
            return {'path': values['path'], 'entries': [{'name': 'child', 'path': '/child', 'is_dir': True}]}
        picker = RemoteDirectoryDialog(root, SimpleNamespace(request=request), '/', chosen.append)
        try:
            deadline = time.monotonic() + 2
            while picker.loading and time.monotonic() < deadline:
                root.update()
                time.sleep(.01)
            self.assertFalse(picker.loading)
            picker.browse('/')
            self.assertEqual(len(calls), 1)
            picker.choose()
            self.assertEqual(chosen, ['/'])
        finally:
            picker.close()
            root.destroy()


if __name__ == '__main__':
    unittest.main()
