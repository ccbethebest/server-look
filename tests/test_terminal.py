from pathlib import Path
import unittest
from tempfile import TemporaryDirectory
from server_look.config.ui_preferences import validate
from server_look.transport.ssh_keys import detect_keys, ensure_key, install_script
from server_look.transport.terminal import python_command

class CommandTests(unittest.TestCase):
    def test_scale_validation_and_legacy(self):
        self.assertEqual(validate({})['global_scale'], 100)
        for bad in (0, 49, 201, True, '100'):
            with self.assertRaises(ValueError): validate({'global_scale': bad})
    def test_existing_pair_never_overwritten(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'id_rsa').write_text('private-placeholder')
            (root / 'id_rsa.pub').write_text('ssh-rsa AAAA comment')
            self.assertEqual(len(detect_keys(root)), 1)
            self.assertEqual(ensure_key(root), root / 'id_rsa.pub')
            self.assertEqual((root / 'id_rsa').read_text(), 'private-placeholder')
    def test_install_only_accepts_public_key(self):
        with self.assertRaises(ValueError): install_script('-----BEGIN PRIVATE KEY-----')
        with self.assertRaises(ValueError): install_script('ssh-ed25519 AAAA\necho bad')
        script = install_script('ssh-ed25519 AAAA test')
        self.assertIn('authorized_keys', script)
        self.assertIn('flock', script)
    def test_python_multiline_compiles_as_one_cell(self):
        command = python_command('for i in range(2):\n    print(i)')
        self.assertIn('exec(compile(', command)
        self.assertTrue(command.endswith('\n'))


class WorkspaceTests(unittest.TestCase):
    def test_scale_is_reversible_and_repeatable(self):
        import tkinter as tk
        from tkinter import ttk
        from server_look.ui.theme import apply_theme
        root = tk.Tk()
        root.withdraw()
        try:
            frame = ttk.Frame(root, padding=10)
            frame.pack(padx=(4, 8))
            tree = ttk.Treeview(frame, columns=('name',))
            tree.column('name', width=160)
            tree.pack()
            root._serverlook_options = {'global_scale': 150}
            apply_theme(root)
            self.assertEqual(tree.column('name', 'width'), 240)
            self.assertEqual(int(str(ttk.Style(root).configure('Treeview', 'rowheight'))), 45)
            apply_theme(root)
            self.assertEqual(tree.column('name', 'width'), 240)
            root._serverlook_options['global_scale'] = 100
            apply_theme(root)
            self.assertEqual(tree.column('name', 'width'), 160)
            self.assertEqual(tuple(map(int, frame.pack_info()['padx'])), (4, 8))
        finally:
            root.destroy()

    def test_independent_sessions_multiline_and_disconnect(self):
        import tkinter as tk
        from tkinter import ttk
        from types import SimpleNamespace
        from unittest.mock import patch, MagicMock
        import queue
        from server_look.ui.command_panel import CommandPanel
        root = tk.Tk()
        root.withdraw()
        page = SimpleNamespace(root=root, tabs=ttk.Notebook(root), connection=object(),
                               readonly=tk.BooleanVar(root, False), generation=1)
        made = []
        def session(*args, **kwargs):
            value = MagicMock(events=queue.Queue())
            value.events.put(('ready', None))
            made.append(value)
            return value
        with patch('server_look.ui.command_panel.TerminalSession', side_effect=session):
            panel = CommandPanel(page)
            try:
                panel.new_shell()
                panel.new_shell()
                panel.new_python()
                panel.poll()
                self.assertEqual(len(panel.sessions), 3)
                item = list(panel.sessions.values())[-1]
                item['editor'].insert('1.0', 'for i in range(2):\n    print(i)')
                panel.execute_cell(item)
                namespace = {}
                exec(made[-1].send.call_args.args[0], namespace)
                exec(python_command('answer = i + 41'), namespace)
                self.assertEqual(namespace['answer'], 42)
                self.assertFalse(made[0].send.called)
                made[0].events.put(('data', 'hello\r\n'))
                panel.poll()
                self.assertIn('hello', list(panel.sessions.values())[0]['output'].get('1.0', 'end'))
                panel.disconnect()
                self.assertTrue(all(value.close.called for value in made))
                page.readonly.set(True)
                made[-1].send.reset_mock()
                panel.execute_cell(item)
                made[-1].send.assert_not_called()
                panel.tabs.select(item['frame'])
                made[-1].close.reset_mock()
                panel.close_current()
                self.assertEqual(len(panel.sessions), 2)
                made[-1].close.assert_called_once()
                self.assertFalse(item['frame'].winfo_exists())
            finally:
                panel.close()
                root.destroy()

if __name__ == '__main__': unittest.main()
