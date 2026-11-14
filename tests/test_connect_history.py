"""Bulk history connections reuse pages and isolate credential failures."""
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from server_look.transport.connection_history import ConnectionHistory
from server_look.app.desktop_app import MultiServerApp


class ConnectHistoryTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.store = ConnectionHistory(Path(self.folder.name) / 'connections.json')
        self.root = tk.Tk()
        self.root.withdraw()
        self.history_patch = patch('server_look.app.server_page.ConnectionHistory', return_value=self.store)
        self.history_patch.start()
        self.app_history_patch = patch('server_look.app.desktop_app.ConnectionHistory', wraps=ConnectionHistory,
                                       return_value=self.store)
        self.app_history_patch.start()
        self.app = MultiServerApp(self.root)

    def tearDown(self):
        self.app.close()
        self.history_patch.stop()
        self.app_history_patch.stop()
        self.folder.cleanup()

    def save(self, host, mode='key', password=''):
        self.store.save(dict(host=host, user='root', port='22', auth_mode=mode),
                        password, bool(password))

    def test_reuses_pages_and_skips_active_connections_on_repeat(self):
        self.save('one.test')
        self.save('two.test', 'password', 'secret')
        page = self.app.current_page()
        page.host.set('one.test')
        with patch('server_look.app.server_page.Connection') as connection, patch('server_look.app.server_page.ServerPage.refresh'):
            self.app.connect_history()
            self.assertEqual(len(self.app.pages), 2)
            self.assertEqual(connection.call_count, 2)
            self.assertIn(page, self.app.pages.values())
            self.assertTrue(any(call.kwargs.get('password') == 'secret'
                                for call in connection.call_args_list))
            self.app.connect_history()
            self.assertEqual(connection.call_count, 2)
            self.assertEqual(len(self.app.pages), 2)

    def test_missing_or_unreadable_password_does_not_block_other_servers(self):
        self.save('key.test')
        self.save('missing.test', 'password')
        self.save('broken.test', 'password', 'saved')
        with patch.object(ConnectionHistory, 'password', side_effect=OSError('cannot decrypt')), \
                patch('server_look.app.server_page.Connection') as connection, patch('server_look.app.server_page.ServerPage.refresh'):
            self.app.connect_history()
            self.assertEqual(connection.call_count, 1)
            failed = [page for page in self.app.pages.values()
                      if page.connection_state.get() == '连接失败']
            self.assertEqual(len(failed), 2)
            self.assertTrue(all(page.connection_error for page in failed))

    def test_empty_history_does_not_create_pages(self):
        with patch('server_look.app.desktop_app.messagebox.showinfo') as notice:
            self.app.connect_history()
        self.assertEqual(len(self.app.pages), 1)
        notice.assert_called_once()
