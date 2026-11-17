import unittest
from unittest.mock import patch
from tests.test_gpu import monitor


class NpuKillTests(unittest.TestCase):
    def test_rechecks_occupancy_identity_protection_and_permissions(self):
        identities = [{'pid': p, 'ticks': 100} for p in (1, 10, 20, 30, 40, 50)]
        def current(pid):
            return {'pid': pid, 'ticks': 101 if pid == 20 else 100}
        def send(fd, sig):
            if fd == 140:
                raise PermissionError('denied')
        with patch.object(monitor, 'run', return_value='probe'), \
             patch.object(monitor, 'parse_npu_processes', return_value={p: {} for p in (1, 10, 20, 30, 40)}), \
             patch.object(monitor, 'processes', return_value={}), \
             patch.object(monitor, 'protected_pids', return_value={1, 30}), \
             patch.object(monitor, 'read_process', side_effect=current), \
             patch.object(monitor.os, 'pidfd_open', side_effect=lambda pid: pid + 100, create=True) as opened, \
             patch.object(monitor.signal, 'pidfd_send_signal', side_effect=send, create=True) as sent, \
             patch.object(monitor.signal, 'SIGKILL', 9, create=True), \
             patch.object(monitor.os, 'close') as closed:
            result = monitor.kill_npu_tasks(identities)
        self.assertEqual(result['killed'], [10])
        self.assertEqual(result['skipped'], [1, 20, 30, 50])
        self.assertEqual(len(result['errors']), 1)
        self.assertEqual(opened.call_count, 3)
        self.assertEqual(sent.call_count, 2)
        self.assertEqual(closed.call_count, 3)

    def test_changed_task_details_are_rejected(self):
        with patch.object(monitor, 'read_process', return_value={'ticks': 2}):
            with self.assertRaises(RuntimeError):
                monitor.task_details(123, 1)

    def test_cancel_does_not_send_kill_and_confirm_sends_snapshot(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from server_look.app.server_page import ServerPage
        task = {'pid': 10, 'ticks': 22, 'user': 'alice', 'command': 'python train.py', 'npu': {'0:0': 100}}
        page = SimpleNamespace(connection=object(), busy=False, fresh=True, readonly=Mock(get=lambda: False),
                               connected_address='test', root=None, data={'processes': {'10': task}}, submit=Mock())
        page.npu_targets = lambda: ServerPage.npu_targets(page)
        with patch('server_look.app.server_page.messagebox.askyesno', return_value=False):
            ServerPage.kill_npu(page)
        page.submit.assert_not_called()
        with patch('server_look.app.server_page.messagebox.askyesno', return_value=True):
            ServerPage.kill_npu(page)
        page.submit.assert_called_once_with('kill_npu', targets=[{'pid': 10, 'ticks': 22}])
        task['npu'] = {'GPU 0': 100}
        self.assertEqual(page.npu_targets(), [])


if __name__ == '__main__':
    unittest.main()
