"""Both Python entry points provide a native script editor, not a terminal input."""
from unittest.mock import patch
import tempfile
from pathlib import Path

from tests.test_terminal_recovery import TerminalRecoveryTests
from server_look.transport.terminal import python_command
import unittest


class ScriptTransportTests(unittest.TestCase):
    def test_large_unicode_script_uses_short_pty_lines_and_retains_state(self):
        source = '# 中文脚本\n' * 1200 + 'answer = 42\n'
        command = python_command(source)
        self.assertLess(max(map(len, command.splitlines())), 1000)
        namespace = {}
        exec(command, namespace)
        self.assertEqual(namespace['answer'], 42)
        self.assertFalse(any(key.startswith('_serverlook_source_') for key in namespace))


class PythonWorkspaceTests(TerminalRecoveryTests):
    def test_pycharm_run_keys_and_block_indent(self):
        window = self.open_context()
        editor = window.editor
        source = 'first = 1\nsecond = 2'
        editor.insert('1.0', source)
        editor.focus_force()
        self.root.update()
        with patch.object(window, 'send') as send:
            editor.event_generate('<Shift-F10>')
            send.assert_called_once_with(python_command(source))
            send.reset_mock()
            editor.tag_add('sel', '2.0', 'end-1c')
            editor.event_generate('<Alt-Shift-KeyPress-E>')
            send.assert_called_once_with(python_command('second = 2'))
        editor.tag_add('sel', '1.0', 'end-1c')
        editor.event_generate('<Tab>')
        self.assertEqual(editor.get('1.0', 'end-1c'), '    first = 1\n    second = 2')
        editor.event_generate('<Shift-Tab>')
        self.assertEqual(editor.get('1.0', 'end-1c'), source)
        editor.event_generate('<Control-slash>')
        self.assertEqual(editor.get('1.0', 'end-1c'), '# first = 1\n# second = 2')

    def open_context(self):
        self.item['ready'] = True
        self.panel.bridge_event(self.item, 'python', True)
        return self.item['python_window']

    def test_both_entry_points_share_script_editor_and_readonly_output(self):
        context = self.open_context()
        self.panel.new_python()
        dedicated = list(self.panel.sessions.values())[-1]
        window = dedicated['python_window']
        self.assertIs(type(window), type(context))
        self.assertIs(dedicated['editor'], window.editor)
        for workspace in (context, window):
            self.assertEqual(str(workspace.output.cget('state')), 'disabled')
            self.assertTrue(workspace.editor.cget('undo'))
            self.assertFalse(workspace.editor.bind('<KeyPress>'))
            workspace.editor.insert('1.0', 'a = 1\nprint(a)')
            workspace.editor.mark_set('insert', '1.5')
            workspace.editor.insert('insert', '0')
            workspace.feed('remote result\r\n')
            self.assertEqual(workspace.editor.index('insert'), '1.6')
            self.assertEqual(workspace.editor.get('1.0', 'end-1c'), 'a = 10\nprint(a)')

    def test_script_runs_on_original_interpreter_and_selection_runs_separately(self):
        window = self.open_context()
        window.editor.insert('1.0', 'answer = 40\nanswer += 2')
        window.execute()
        namespace = {}
        exec(self.item['session'].send.call_args.args[0], namespace)
        self.assertEqual(namespace['answer'], 42)
        window.editor.tag_add('sel', '2.0', '2.end')
        window.execute_selection()
        exec(self.item['session'].send.call_args.args[0], namespace)
        self.assertEqual(namespace['answer'], 44)

    def test_native_cursor_mouse_clipboard_delete_and_undo(self):
        window = self.open_context()
        editor = window.editor
        window.window.update()
        editor.focus_force()
        editor.insert('1.0', 'hello world\nsecond line')
        editor.mark_set('insert', '1.5')
        editor.event_generate('<Left>')
        self.assertEqual(editor.index('insert'), '1.4')
        editor.event_generate('<Right>')
        self.assertEqual(editor.index('insert'), '1.5')
        box = editor.bbox('2.0')
        editor.event_generate('<Button-1>', x=box[0], y=box[1] + 2)
        editor.event_generate('<ButtonRelease-1>', x=box[0], y=box[1] + 2)
        self.assertEqual(editor.index('insert'), '2.0')
        try:
            previous_clipboard = editor.clipboard_get()
        except Exception:
            previous_clipboard = ''
        try:
            editor.tag_add('sel', '1.0', '1.5')
            editor.event_generate('<<Copy>>')
            self.assertEqual(editor.clipboard_get(), 'hello')
            editor.tag_remove('sel', '1.0', 'end')
            editor.mark_set('insert', 'end-1c')
            editor.event_generate('<<Paste>>')
            self.assertTrue(editor.get('1.0', 'end-1c').endswith('hello'))
            editor.edit_separator()
            editor.tag_remove('sel', '1.0', 'end')
            editor.tag_add('sel', '1.0', '1.5')
            editor.mark_set('insert', '1.5')
            editor.event_generate('<Delete>')
            self.assertTrue(editor.get('1.0', 'end-1c').startswith(' world'), editor.get('1.0', 'end-1c'))
            editor.event_generate('<Control-z>')
            self.assertTrue(editor.get('1.0', 'end-1c').startswith('hello world'))
        finally:
            editor.clipboard_clear()
            editor.clipboard_append(previous_clipboard)

    def test_local_script_save_search_and_cancel_close_keep_content(self):
        window = self.open_context()
        window.editor.insert('1.0', 'print("hello")\n')
        window.search_query.set('hello')
        window.find_text()
        self.assertTrue(window.editor.tag_ranges('search_match'))
        with patch('server_look.ui.context_python.messagebox.askyesnocancel', return_value=None):
            self.assertFalse(window.close())
        self.assertTrue(window.active)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'script.py'
            with patch('server_look.ui.context_python.filedialog.asksaveasfilename', return_value=str(path)):
                self.assertTrue(window.save())
            self.assertEqual(path.read_text(encoding='utf-8'), 'print("hello")\n')
            self.assertFalse(window.dirty())

    def test_readonly_and_replaced_connections_cannot_execute(self):
        window = self.open_context()
        window.editor.insert('1.0', 'print(1)')
        self.panel.page.readonly.set(True)
        window.execute()
        self.item['session'].send.assert_not_called()
        self.panel.page.readonly.set(False)
        self.panel.page.generation += 1
        window.execute()
        self.item['session'].send.assert_not_called()
