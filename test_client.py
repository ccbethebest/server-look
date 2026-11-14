import json
import io
import tkinter as tk
import unittest
from unittest.mock import patch

from client_core import Connection, connection_args, find_task
from desktop_app import MultiServerApp
from server_page import ServerPage
from directory_channel import DirectoryChannel


class ClientTests(unittest.TestCase):
    def test_server_tab_dimensions_stay_fixed_when_selected(self):
        root = tk.Tk()
        app = MultiServerApp(root)
        try:
            self.assertEqual(len(app.pages), 1)
            self.assertEqual(next(iter(app.pages.values())).host.get(), '')
            app.add_server('example.test')
            widths = []
            for selected in (0, 1, 0):
                app.notebook.select(selected)
                root.update()
                widths.append({i: app.server_tabs.bbox(f'tab{i}') for i in range(2)})
            self.assertEqual(set(widths[0]), {0, 1})
            self.assertTrue(all(widths[0].values()))
            self.assertEqual(widths[0], widths[1])
            self.assertEqual(widths[1], widths[2])
        finally:
            app.close()

    def test_directory_requests_reuse_one_ssh_process(self):
        with patch('directory_channel.subprocess.Popen') as launch:
            process = launch.return_value
            process.poll.return_value = None
            process.stdin = io.StringIO()
            process.stdout = io.StringIO('\nWelcome to server\n{"result":{"path":"/"}}\n{"result":{"path":"/mnt"}}\n')
            channel = DirectoryChannel(['ssh', 'server'])
            try:
                self.assertEqual(channel.request('/')['path'], '/')
                self.assertEqual(channel.request('/mnt')['path'], '/mnt')
                self.assertEqual(launch.call_count, 1)
            finally:
                channel.close()

    def test_directory_cache_avoids_network_and_refresh_bypasses_cache(self):
        root = tk.Tk()
        root.withdraw()
        page = ServerPage(root)
        try:
            page.connection = object()
            page.resources.complete(dict(path='/mnt', entries=[], truncated=False), None)
            with patch.object(page, 'submit') as submit:
                page.resources.browse('/mnt')
                submit.assert_not_called()
                page.busy = True  # Monitoring does not block the directory channel.
                page.resources.browse('/mnt', force=True)
                submit.assert_called_once_with('list_directory', path='/mnt')
        finally:
            page.close()

    def test_file_navigation_and_disconnect_clear_previous_server_paths(self):
        root = tk.Tk()
        root.withdraw()
        page = ServerPage(root)
        try:
            page.connection = object()
            result = dict(path='/mnt', entries=[dict(name='weights', path='/mnt/weights', is_dir=True,
                          link=False, size=0, modified='today')], truncated=False)
            page.resources.apply(result)
            self.assertEqual(page.resources.path.get(), '/mnt')
            item = page.resources.files.get_children()[0]
            page.resources.files.selection_set(item)
            with patch.object(page, 'submit') as submit:
                page.resources.enter()
                submit.assert_called_once_with('list_directory', path='/mnt/weights')
            page.disconnect()
            self.assertEqual(page.resources.path.get(), '/')
            self.assertFalse(page.resources.files.get_children())
        finally:
            page.close()

    def test_resource_tabs_disable_task_actions_and_show_capacity(self):
        root = tk.Tk()
        root.withdraw()
        page = ServerPage(root)
        try:
            page.connection, page.fresh = object(), True
            page.data = dict(hardware={'CPU 架构': 'aarch64'}, disks=[dict(mount='/mnt', device='/dev/sda',
                             type='ext4', total=1024**4, used=1024**3, available=1024**3, percent='1%')])
            page.resources.render(page.data)
            page.tabs.select(page.resources.frame)
            page.buttons()
            self.assertEqual(str(page.term_button['state']), 'disabled')
            values = page.resources.disks.item('0', 'values')
            self.assertIn('1.0 TiB', values)
        finally:
            page.close()

    def test_reconnect_discards_results_from_previous_server(self):
        root = tk.Tk()
        root.withdraw()
        page = ServerPage(root)
        try:
            old_generation = page.generation
            page.disconnect()
            page.data = {'host': 'current-server'}
            page.results.put((old_generation, 'snapshot', {'host': 'old-server'}, None))
            root.after_cancel(page.poll_job)
            page.poll()
            self.assertEqual(page.data['host'], 'current-server')
            self.assertFalse(page.fresh)
        finally:
            page.close()

    def test_task_action_uses_selected_page_connection_and_identity(self):
        root = tk.Tk()
        root.withdraw()
        app = MultiServerApp(root)
        try:
            app.add_server('example.test')
            first, second = app.pages.values()
            first.connection, first.fresh = object(), True
            first.connected_address = 'root@first-server:22'
            task = dict(pid=12, ticks=100, ppid=1, started='today', user='root',
                        npu={'0:0': 123}, container=None, command='worker')
            first.data = dict(processes={'12': task}, containers={}, npu='OK')
            first.identity = (12, 100)
            first.render()
            root.update()
            with patch('server_page.messagebox.askyesno', return_value=True) as confirm, \
                    patch.object(first, 'submit') as submit, \
                    patch.object(second, 'submit') as other_submit:
                first.act('term')
                submit.assert_called_once_with('term', pid=12, ticks=100)
                other_submit.assert_not_called()
                self.assertIn('root@first-server:22', confirm.call_args.args[1])
        finally:
            app.close()

    def test_server_pages_keep_state_and_lifecycle_independent(self):
        root = tk.Tk()
        root.withdraw()
        app = MultiServerApp(root)
        try:
            app.add_server('example.test')
            first, second = app.pages.values()
            self.assertEqual(first.host.get(), '')
            self.assertEqual(second.host.get(), 'example.test')
            self.assertIsNot(first.results, second.results)
            first.readonly.set(True)
            self.assertFalse(second.readonly.get())
            second.connection, second.fresh = object(), True
            second.data = {'host': 'second'}
            first.disconnect()
            self.assertTrue(second.fresh)
            self.assertEqual(second.data['host'], 'second')
            added = app.add_server()
            self.assertEqual(added.host.get(), '')
            app.close_page()
            self.assertTrue(added.closed)
            self.assertEqual(len(app.pages), 2)
            root.update()
        finally:
            app.close()

    def test_reject_connection_injection(self):
        for host in ['-oProxyCommand=bad', 'host;cmd', 'host\nother', '$(cmd)']:
            with self.assertRaises(ValueError):
                connection_args(host, 'root', 22)
        with self.assertRaises(ValueError):
            connection_args('example.com', 'root;cmd', 22)

    def test_pid_reuse_does_not_match(self):
        data = {'processes': {'12': {'pid': 12, 'ticks': 200}}}
        self.assertIsNone(find_task(data, (12, 100)))
        self.assertIsNotNone(find_task(data, (12, 200)))

    def test_transport_no_shell_and_host_verification(self):
        with patch('client_core.subprocess.run') as run:
            run.return_value.returncode = 0
            run.return_value.stdout = '{}'
            Connection('server.example', 'test-user', 22).request('snapshot')
            args, kwargs = run.call_args
            self.assertIn('StrictHostKeyChecking=yes', args[0])
            self.assertFalse(kwargs.get('shell', False))
            payload = json.loads(kwargs['input'])
            self.assertEqual(payload['action'], 'snapshot')
            self.assertIn('def collect():', payload['source'])
            self.assertNotIn('/root/npu-top', args[0][-1])

    def test_idle_npu_still_shows_container_processes(self):
        root = tk.Tk()
        root.withdraw()
        app = ServerPage(root)
        try:
            task = dict(pid=12, ticks=100, ppid=1, started='today', user='root', container='abc', command='sleep 60')
            app.data = dict(processes={'12': task}, containers={}, npu='No running processes')
            app.render()
            self.assertEqual(len(app.tasks.get_children()), 1)
            self.assertIn('加速卡任务 0', app.summary.get())
            app.all_tasks.set(False)
            app.render()
            self.assertFalse(app.tasks.get_children())
            self.assertIn('没有正在占用 NPU', app.summary.get())
        finally:
            app.close()

    def test_gui_readonly_and_disappeared_selection(self):
        root = tk.Tk()
        root.withdraw()
        app = ServerPage(root)
        try:
            app.connection, app.fresh = object(), True
            task = dict(pid=12, ticks=100, ppid=1, started='2026-11-12', user='root', npu={'0:0': 123}, container=None, command='python worker.py')
            app.data = dict(processes={'12': task}, containers={}, npu='NPU OK')
            app.identity = (12, 100)
            app.render()
            root.update()
            self.assertEqual(str(app.term_button['state']), 'normal')
            app.readonly.set(True)
            app.buttons()
            self.assertEqual(str(app.term_button['state']), 'disabled')
            app.readonly.set(False)
            app.data['processes']['12'] = dict(task, ticks=200)
            app.render()
            root.update()
            self.assertEqual(str(app.term_button['state']), 'disabled')
            self.assertFalse(app.tasks.selection())
        finally:
            app.close()


if __name__ == '__main__':
    unittest.main()
