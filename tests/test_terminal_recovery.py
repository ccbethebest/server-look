"""Regression checks for terminal queries, isolation, and public-key selection."""
from pathlib import Path
import queue
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from server_look.transport.client_core import connection_args


class KeyConnectionTests(unittest.TestCase):
    def test_key_login_reuses_app_trust_and_nonstandard_key(self):
        with tempfile.TemporaryDirectory(prefix='ssh home ') as folder:
            home = Path(folder)
            ssh = home / '.ssh'
            ssh.mkdir()
            (ssh / 'custom_key').write_text('fixture only')
            (ssh / 'custom_key.pub').write_text('ssh-ed25519 AAAA fixture')
            (ssh / 'server_look_known_hosts').write_text('fixture only')
            with patch('pathlib.Path.home', return_value=home):
                args = connection_args('example.test', 'tester', 22)
            self.assertIn('-i', args)
            self.assertEqual(args[args.index('-i') + 1], str(ssh / 'custom_key'))
            self.assertIn(f'UserKnownHostsFile="{(ssh / "known_hosts").as_posix()}" '
                          f'"{(ssh / "server_look_known_hosts").as_posix()}"', args)
            self.assertIn('StrictHostKeyChecking=yes', args)


class TerminalRecoveryTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from tkinter import ttk
        from server_look.ui.command_panel import CommandPanel
        self.root = tk.Tk()
        self.root.withdraw()
        page = SimpleNamespace(root=self.root, tabs=ttk.Notebook(self.root), connection=object(),
                               readonly=tk.BooleanVar(self.root, False), generation=1)
        self.patch = patch('server_look.ui.command_panel.TerminalSession',
                           side_effect=lambda *a, **kw: MagicMock(events=queue.Queue()))
        self.patch.start()
        self.panel = CommandPanel(page)
        self.panel.new_shell()
        self.item = next(iter(self.panel.sessions.values()))

    def tearDown(self):
        self.panel.close()
        self.root.destroy()
        self.patch.stop()

    def poll(self):
        self.root.after_cancel(self.panel.poll_job)
        self.panel.poll()

    def test_private_cursor_query_and_subsequent_output(self):
        self.item['session'].events.put(('data', '\x1b[2;3H\x1b[?6nAFTER'))
        self.poll()
        self.item['session'].send.assert_called_with('\x1b[?2;3R')
        self.assertIn('AFTER', self.item['output'].get('1.0', 'end'))
        self.item['session'].events.put(('data', 'NEXT'))
        self.poll()
        self.assertIn('NEXT', self.item['output'].get('1.0', 'end'))

    def test_parser_failure_does_not_stop_other_sessions_or_polling(self):
        self.item['stream'] = MagicMock()
        self.item['stream'].feed.side_effect = ValueError('invalid terminal output')
        self.item['session'].events.put(('data', 'bad'))
        self.panel.new_shell()
        healthy = list(self.panel.sessions.values())[-1]
        healthy['session'].events.put(('data', 'HEALTHY'))
        previous = self.panel.poll_job
        self.poll()
        self.assertTrue(self.item['ended'])
        self.item['session'].close.assert_called_once()
        self.assertIn('HEALTHY', healthy['output'].get('1.0', 'end'))
        self.assertNotEqual(previous, self.panel.poll_job)


if __name__ == '__main__':
    unittest.main()
