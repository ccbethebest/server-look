import subprocess
import sys
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from server_look.transport.ssh_keys import check_key, configure_key, install_script, _KEY_LOOKUP
from server_look.ui.command_panel import CommandPanel


class KeyTransportTests(unittest.TestCase):
    def test_openssh_receives_lf_script_despite_windows_text_translation(self):
        receiver = (
            "import sys; payload = sys.stdin.buffer.read(); "
            "sys.stderr.write('Authorized users only. All activities may be monitored and reported.\\n'); "
            "sys.exit('CRLF reached remote shell') if b'\\r' in payload else print('PAIRED')"
        )
        connection = SimpleNamespace(session=None, args=[sys.executable, '-c', receiver])
        self.assertTrue(check_key(connection, 'ssh-ed25519 AAAA local'))

    def test_detection_is_read_only_and_uses_existing_connection(self):
        connection = SimpleNamespace(session=Mock())
        connection.session.execute.return_value = 'PAIRED\n'
        self.assertTrue(check_key(connection, 'ssh-ed25519 AAAA local'))
        command, script = connection.session.execute.call_args.args
        self.assertEqual(command, 'sh -s')
        for mutation in ('mkdir', 'chmod', '>>', 'flock'):
            self.assertNotIn(mutation, script)
        connection.session.execute.return_value = 'MISSING\n'
        self.assertFalse(check_key(connection, 'ssh-ed25519 AAAA local'))
        connection.session.execute.return_value = 'unexpected'
        with self.assertRaises(RuntimeError):
            check_key(connection, 'ssh-ed25519 AAAA local')

    def test_install_preserves_append_lock_and_duplicate_check(self):
        connection = SimpleNamespace(session=Mock())
        configure_key(connection, 'ssh-ed25519 AAAA local')
        script = connection.session.execute.call_args.args[1]
        self.assertIn('exec 9>>authorized_keys', script)
        self.assertIn('flock -x 9', script)
        self.assertIn('shlex.split', script)
        self.assertIn('Public key already configured', script)
        with self.assertRaises(ValueError):
            install_script('ssh-ed25519 AAAA\necho malicious', check_only=True)

    def test_remote_key_matching_options_comments_and_false_matches(self):
        with TemporaryDirectory() as directory:
            target = Path(directory) / 'authorized_keys'
            for content, expected in [
                ('ssh-ed25519 AAAA old-computer\n', 0),
                ('command="echo hello world",no-pty ssh-ed25519 AAAA other-comment\n', 0),
                ('# ssh-ed25519 AAAA comment\n', 1),
                ('command="echo ssh-ed25519 AAAA test" ssh-ed25519 BBBB\n', 1),
                ('ssh-ed25519 BBBB ssh-ed25519 AAAA\n', 1),
                ('ssh-rsa AAAA\n', 1),
                ('\n', 1),
            ]:
                target.write_text(content, encoding='utf-8')
                result = subprocess.run([sys.executable, '-c', _KEY_LOOKUP, 'ssh-ed25519', 'AAAA'],
                                        cwd=directory, capture_output=True)
                self.assertEqual(result.returncode, expected, result.stderr)


class KeyPanelTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.connection = object()
        self.page = SimpleNamespace(root=self.root, tabs=ttk.Notebook(self.root),
                                    connection=self.connection, generation=1,
                                    readonly=tk.BooleanVar(self.root, False))
        self.panel = CommandPanel(self.page)
        self.root.after_cancel(self.panel.poll_job)

    def tearDown(self):
        self.panel.close()
        self.root.destroy()

    def result(self, paired, **kwargs):
        self.panel.key_result('configure', 1, self.connection, 'ssh-ed25519 AAAA local', paired, **kwargs)

    def test_detect_and_generate_report_both_paths_without_generation(self):
        path = Path('C:/test/.ssh/id_ed25519.pub')
        with patch('server_look.ui.command_panel.detect_keys', return_value=[path]), \
             patch('server_look.ui.command_panel.ensure_key') as generate, \
             patch('server_look.ui.command_panel.messagebox.showinfo') as info:
            for action in ('detect', 'generate'):
                self.panel.key_action(action)
                report = info.call_args.args[1]
                self.assertIn(str(path), report)
                self.assertIn(str(path.with_suffix('')), report)
            self.assertIn('无需生成', report)
            generate.assert_not_called()

    def test_already_paired_and_decline_never_install(self):
        with patch('server_look.ui.command_panel.messagebox.showinfo') as info, \
             patch('server_look.ui.command_panel.messagebox.askyesno', return_value=False) as ask, \
             patch.object(self.panel, 'start_key_job') as start:
            self.result(True, error=False)
            self.assertIn('已配对', info.call_args.args[1])
            ask.assert_not_called()
            self.result(False, error=False)
            ask.assert_called_once()
            start.assert_not_called()

    def test_approve_installs_only_captured_key_and_connection(self):
        with patch('server_look.ui.command_panel.messagebox.askyesno', return_value=True), \
             patch.object(self.panel, 'start_key_job') as start:
            self.result(False, error=False)
            start.assert_called_once_with('install', 1, self.connection, 'ssh-ed25519 AAAA local')

    def test_stale_connection_or_readonly_cannot_install(self):
        with patch('server_look.ui.command_panel.messagebox.askyesno', return_value=True) as ask, \
             patch('server_look.ui.command_panel.messagebox.showwarning'), \
             patch.object(self.panel, 'start_key_job') as start:
            self.page.connection = object()
            self.result(False, error=False)
            ask.assert_not_called()
            self.page.connection = self.connection
            self.page.readonly.set(True)
            self.result(False, error=False)
            ask.assert_not_called()
            start.assert_not_called()

    def test_worker_checks_before_any_write(self):
        with patch('server_look.ui.command_panel.check_key', return_value=False) as check, \
             patch('server_look.ui.command_panel.configure_key') as install:
            self.panel.start_key_job('configure', 1, self.connection, 'ssh-ed25519 AAAA local')
            result = self.panel.jobs.get(timeout=2)
            check.assert_called_once_with(self.connection, 'ssh-ed25519 AAAA local')
            install.assert_not_called()
            self.assertEqual(result[-2:], (False, False))


if __name__ == '__main__':
    unittest.main()
