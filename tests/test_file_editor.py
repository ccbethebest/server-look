"""Text editing preserves encoding and refuses unsafe or stale writes."""
import os
from pathlib import Path
import tempfile
import unittest
from server_look.remote.file_editor import edit_file


class FileEditingTests(unittest.TestCase):
    def test_roundtrip_encoding_newlines_and_conflict(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'notes.txt'
            for codec, bom in [('utf-8', b''), ('utf-8-sig', b''), ('gb18030', b''), ('utf-16-le', b'\xff\xfe'), ('utf-16-be', b'\xfe\xff')]:
                path.write_bytes(bom + '你好\r\nabc\r\n'.encode(codec))
                document = edit_file(str(path))
                self.assertEqual(document.pop('text'), '你好\nabc\n')
                edit_file(str(path), text='修改\n', **document)
                self.assertEqual(path.read_bytes(), bom + '修改\r\n'.encode(codec))
                with self.assertRaisesRegex(ValueError, '外部修改'):
                    edit_file(str(path), text='覆盖', **document)
                self.assertEqual(path.read_bytes(), bom + '修改\r\n'.encode(codec))

    def test_remote_dispatch_read_and_save(self):
        import json
        import subprocess
        import sys
        from server_look.transport.client_core import REMOTE
        source = Path('server_look/remote/file_editor.py').read_text(encoding='utf-8')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'remote.txt'
            path.write_text('before', encoding='utf-8')
            def request(options):
                payload = dict(action='edit_file', source='', resource_source=source, options=options)
                result = subprocess.run([sys.executable, '-c', REMOTE], input=json.dumps(payload),
                                        text=True, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                return json.loads(result.stdout)
            document = request(dict(path=str(path)))
            document.pop('text')
            request(dict(path=str(path), text='after', **document))
            self.assertEqual(path.read_text(encoding='utf-8'), 'after')

    def test_refuse_binary_and_large_files_but_accept_text_scripts(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'notes.txt'
            path.write_bytes(b'abc\0def')
            with self.assertRaises(ValueError):
                edit_file(str(path))
            exe = Path(folder) / 'test.exe'
            exe.write_text('text')
            self.assertEqual(edit_file(str(exe))['text'], 'text')
            path.write_bytes(b'x' * (4 * 1024 * 1024 + 1))
            with self.assertRaisesRegex(ValueError, '4 MiB'):
                edit_file(str(path))
            if os.name != 'nt':
                path.write_text('hello')
                path.chmod(0o755)
                self.assertEqual(edit_file(str(path))['text'], 'hello')


class EditorWindowTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from types import SimpleNamespace
        from server_look.ui.text_editor import EditorManager
        self.root = tk.Tk()
        self.root.withdraw()
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / 'notes.txt'
        self.path.write_text('original', encoding='utf-8')
        self.page = SimpleNamespace(root=self.root, connection=None, generation=1,
                                    readonly=tk.BooleanVar(self.root, False))
        self.manager = EditorManager(self.page)

    def tearDown(self):
        import gc
        for editor in list(self.manager.windows):
            editor.destroy()
        self.root.destroy()
        self.folder.cleanup()
        # Release old Tcl interpreters on their owning thread before the next worker starts.
        del self.manager, self.page, self.root
        gc.collect()

    def wait(self, editor):
        import time
        deadline = time.monotonic() + 5
        while editor.busy and time.monotonic() < deadline:
            self.root.update()
            time.sleep(.01)
        self.root.update()
        self.assertFalse(editor.busy)

    def test_comment_shortcut_toggles_block_preserves_indent_and_undo(self):
        self.manager.open(self.path)
        editor = self.manager.windows[0]
        self.wait(editor)
        text = editor.text
        source = '    alpha\n  # existing\n\nnext'
        text.delete('1.0', 'end')
        text.insert('1.0', source)
        text.edit_reset()
        text.focus_force()
        self.root.update()
        text.tag_add('sel', '1.2', '4.0')
        text.event_generate('<Control-slash>')
        self.assertEqual(editor.content(), '    # alpha\n  # # existing\n\nnext')
        text.event_generate('<Control-slash>')
        self.assertEqual(editor.content(), source)
        text.edit_undo()
        self.assertEqual(editor.content(), '    # alpha\n  # # existing\n\nnext')
        text.edit_undo()
        self.assertEqual(editor.content(), source)
        text.tag_remove('sel', '1.0', 'end')
        text.mark_set('insert', '4.2')
        text.event_generate('<Control-slash>')
        self.assertEqual(editor.content(), source[:-4] + '# next')
        text.configure(state='disabled')
        text.event_generate('<Control-slash>')
        self.assertEqual(editor.content(), source[:-4] + '# next')

    def test_selected_lines_tab_shift_tab_and_single_step_undo(self):
        self.manager.open(self.path)
        editor = self.manager.windows[0]
        self.wait(editor)
        text = editor.text
        text.delete('1.0', 'end')
        text.insert('1.0', 'alpha\nbeta\ngamma')
        text.edit_reset()
        text.focus_force()
        self.root.update()
        text.tag_add('sel', '1.2', '3.0')
        text.event_generate('<Tab>')
        self.assertEqual(editor.content(), '    alpha\n    beta\ngamma')
        self.assertTrue(text.tag_ranges('sel'))
        text.event_generate('<Tab>')
        self.assertEqual(editor.content(), '        alpha\n        beta\ngamma')
        text.event_generate('<Shift-Tab>')
        self.assertEqual(editor.content(), '    alpha\n    beta\ngamma')
        text.edit_undo()
        self.assertEqual(editor.content(), '        alpha\n        beta\ngamma')
        text.edit_undo()
        self.assertEqual(editor.content(), '    alpha\n    beta\ngamma')
        text.edit_redo()
        self.assertEqual(editor.content(), '        alpha\n        beta\ngamma')

    def test_outdent_short_indent_blank_lines_and_cursor_tab(self):
        self.manager.open(self.path)
        editor = self.manager.windows[0]
        self.wait(editor)
        text = editor.text
        text.delete('1.0', 'end')
        text.insert('1.0', '  alpha\n\tbeta\n\nplain\n')
        text.focus_force()
        self.root.update()
        text.tag_add('sel', '1.0', 'end-1c')
        text.event_generate('<Shift-Tab>')
        self.assertEqual(editor.content(), 'alpha\nbeta\n\nplain\n')
        text.tag_remove('sel', '1.0', 'end')
        text.mark_set('insert', '1.2')
        text.event_generate('<Tab>')
        self.assertEqual(editor.content(), 'al    pha\nbeta\n\nplain\n')
        text.configure(state='disabled')
        text.event_generate('<Tab>')
        self.assertEqual(editor.content(), 'al    pha\nbeta\n\nplain\n')

    def test_line_numbers_follow_scroll_and_font(self):
        self.path.write_text('\n'.join('text ' + str(i) for i in range(1, 301)), encoding='utf-8')
        self.manager.open(self.path)
        editor = self.manager.windows[0]
        self.wait(editor)
        gutter = editor.line_numbers
        self.assertEqual(gutter.itemcget(gutter.find_all()[0], 'text'), '1')
        self.assertLess(len(gutter.find_all()), 100)
        editor.text.yview('120.0')
        self.root.update()
        first = gutter.find_all()[0]
        line = gutter.itemcget(first, 'text')
        self.assertEqual(line, editor.text.index('@0,0').split('.')[0])
        self.assertEqual(gutter.coords(first)[1], editor.text.dlineinfo(line + '.0')[1])
        old_width = gutter.winfo_width()
        editor.text.configure(font=('Consolas', 24))
        self.root.update()
        self.assertGreater(gutter.winfo_width(), old_width)

    def test_line_numbers_update_on_edit_undo_and_do_not_enter_saved_text(self):
        self.manager.open(self.path)
        editor = self.manager.windows[0]
        self.wait(editor)
        editor.text.insert('end-1c', '\nsecond\nthird')
        editor.text.edit_separator()
        self.root.update()
        labels = lambda: [editor.line_numbers.itemcget(item, 'text')
                          for item in editor.line_numbers.find_all()]
        self.assertEqual(labels(), ['1', '2', '3'])
        editor.edit('<<Undo>>')
        self.root.update()
        self.assertEqual(labels(), ['1'])
        editor.edit('<<Redo>>')
        self.root.update()
        self.assertEqual(labels(), ['1', '2', '3'])
        editor.save()
        self.wait(editor)
        self.assertEqual(self.path.read_text(encoding='utf-8'), 'original\nsecond\nthird')

    def test_find_unicode_literal_wrap_backwards_and_edited_content(self):
        self.manager.open(self.path)
        editor = self.manager.windows[0]
        self.wait(editor)
        editor.text.delete('1.0', 'end')
        editor.text.insert('1.0', '你好.*\nother\n你好.*')
        editor.show_search()
        editor.search_query.set('你好.*')
        editor.find_text()
        self.assertEqual(str(editor.text.index('search_match.first')), '1.0')
        editor.find_text()
        self.assertEqual(str(editor.text.index('search_match.first')), '3.0')
        editor.find_text()
        self.assertEqual(str(editor.text.index('search_match.first')), '1.0')
        editor.find_text(backwards=True)
        self.assertEqual(str(editor.text.index('search_match.first')), '3.0')
        editor.text.delete('3.0', 'end-1c')
        editor.find_text()
        self.assertEqual(str(editor.text.index('search_match.first')), '1.0')
        editor.search_query.set('missing')
        editor.find_text()
        self.assertEqual(editor.text.tag_ranges('search_match'), ())
        self.assertIn('未找到', editor.search_status.get())
        editor.search_query.set('')
        editor.find_text()
        editor.hide_search()
        self.assertFalse(editor.search_bar.winfo_ismapped())

    def test_undo_redo_save_and_close_confirmations(self):
        from unittest.mock import patch
        self.manager.open(self.path)
        editor = self.manager.windows[0]
        self.wait(editor)
        self.manager.open(self.path)
        self.assertEqual(len(self.manager.windows), 1)
        editor.text.insert('end', ' changed')
        editor.text.edit_separator()
        self.assertTrue(editor.dirty())
        editor.edit('<<Undo>>')
        self.assertEqual(editor.content(), 'original')
        editor.edit('<<Redo>>')
        self.assertEqual(editor.content(), 'original changed')
        with patch('server_look.ui.text_editor.messagebox.askyesnocancel', return_value=None):
            self.assertFalse(self.manager.close_all())
        self.assertTrue(editor.window.winfo_exists())
        editor.save()
        self.wait(editor)
        self.assertEqual(self.path.read_text(encoding='utf-8'), 'original changed')
        self.assertFalse(editor.dirty())
        editor.text.insert('end', ' discarded')
        with patch('server_look.ui.text_editor.messagebox.askyesnocancel', return_value=False):
            self.assertTrue(self.manager.close_all())
        self.assertEqual(self.path.read_text(encoding='utf-8'), 'original changed')
        self.manager.open(self.path)
        editor = self.manager.windows[0]
        self.wait(editor)
        editor.text.insert('end', ' saved on close')
        with patch('server_look.ui.text_editor.messagebox.askyesnocancel', return_value=True):
            self.assertFalse(editor.close())
        self.wait(editor)
        self.assertTrue(editor.closed)
        self.assertEqual(self.path.read_text(encoding='utf-8'), 'original changed saved on close')

    def test_terminal_request_uses_remote_editor_save_and_close(self):
        import json
        import queue
        from tkinter import ttk
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        from server_look.ui.command_panel import CommandPanel
        connection = Mock()
        connection.request.side_effect = lambda action, options: edit_file(**options)
        self.page.connection = connection
        self.page.tabs = ttk.Notebook(self.root)
        self.page.resources = SimpleNamespace(editors=self.manager)
        with patch('server_look.ui.command_panel.TerminalSession',
                   side_effect=lambda *a, **kw: Mock(events=queue.Queue())):
            panel = CommandPanel(self.page)
            try:
                panel.new_shell()
                item = next(iter(panel.sessions.values()))
                bridge = item['editor_bridge']
                request = bridge.prefix + json.dumps(str(self.path)) + '\x07prompt> '
                item['session'].events.put(('ready', None))
                item['session'].events.put(('data', request))
                panel.poll_session(item)
                editor = self.manager.windows[0]
                self.wait(editor)
                self.assertEqual(editor.content(), 'original')
                editor.text.insert('end', ' saved from terminal')
                with patch('server_look.ui.text_editor.messagebox.askyesnocancel', return_value=True):
                    editor.close()
                self.wait(editor)
                self.assertTrue(editor.closed)
                self.assertEqual(self.path.read_text(), 'original saved from terminal')
                self.assertIn('prompt>', item['output'].get('1.0', 'end'))
                self.assertFalse(item['ended'])
            finally:
                panel.close()

    def test_container_context_is_kept_for_save_and_separates_same_paths(self):
        from unittest.mock import Mock
        context = dict(boot='boot', namespace='mnt:[42]', uid='0', gid='0')
        connection = Mock()
        def request(action, options, **kwargs):
            self.assertEqual(kwargs.get('context'), context)
            result = edit_file(**dict(options, path=str(self.path)))
            return dict(result, location='Docker training · abc123')
        connection.request.side_effect = request
        self.page.connection = connection
        self.manager.open('/tmp/notes.txt', remote=True, context=context)
        editor = self.manager.windows[0]
        self.wait(editor)
        self.assertIn('Docker training', editor.status.get())
        self.manager.open('/tmp/notes.txt', remote=True, context=context)
        self.assertEqual(len(self.manager.windows), 1)
        editor.text.insert('end', ' updated')
        editor.save()
        self.wait(editor)
        self.assertEqual(self.path.read_text(), 'original updated')
        self.assertEqual(connection.request.call_count, 2)
        # An identical path on the host belongs to a separate editor window.
        connection.request.side_effect = lambda action, options: edit_file(str(self.path))
        self.manager.open('/tmp/notes.txt', remote=True)
        self.wait(self.manager.windows[1])
        self.assertEqual(len(self.manager.windows), 2)

    def test_remote_save_guards_and_conflict_keep_editor_open(self):
        from unittest.mock import Mock, patch
        connection = Mock()
        connection.request.side_effect = lambda action, options: edit_file(**options)
        self.page.connection = connection
        self.manager.open(str(self.path), remote=True)
        editor = self.manager.windows[0]
        self.wait(editor)
        editor.text.insert('end', ' edited')
        for readonly, generation in [(True, 1), (False, 2)]:
            self.page.readonly.set(readonly)
            self.page.generation = generation
            with patch('server_look.ui.text_editor.messagebox.showwarning') as warning:
                editor.save()
                warning.assert_called_once()
            self.assertEqual(connection.request.call_count, 1)
        self.page.generation = 1
        self.path.write_text('external', encoding='utf-8')
        with patch('server_look.ui.text_editor.messagebox.showerror') as error:
            editor.save()
            self.wait(editor)
            error.assert_called_once()
        self.assertEqual(self.path.read_text(encoding='utf-8'), 'external')
        self.assertTrue(editor.dirty())
        self.assertFalse(editor.closed)

    def test_application_close_respects_editor_cancel(self):
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        from server_look.app.desktop_app import MultiServerApp
        self.manager.open(self.path)
        editor = self.manager.windows[0]
        self.wait(editor)
        editor.text.insert('end', ' dirty')
        page = SimpleNamespace(resources=SimpleNamespace(editors=self.manager), close=Mock())
        app = SimpleNamespace(pages={'page': page}, dialogs=[], root=Mock())
        with patch('server_look.ui.text_editor.messagebox.askyesnocancel', return_value=None):
            MultiServerApp.close(app)
        app.root.destroy.assert_not_called()
        page.close.assert_not_called()

    def test_tick_indicates_boolean_selection(self):
        from tkinter import ttk
        import tkinter as tk
        from server_look.ui.theme import apply_theme
        apply_theme(self.root)
        value = tk.BooleanVar(self.root, False)
        check = ttk.Checkbutton(self.root, variable=value)
        check.invoke()
        self.assertTrue(value.get())
        self.assertIn('selected', check.state())
        check.invoke()
        self.assertFalse(value.get())
        self.assertNotIn('selected', check.state())
        self.assertIn('ServerLook.Check.indicator', str(ttk.Style(self.root).layout('TCheckbutton')))
        blank, selected, _, _ = self.root._serverlook_check_images
        self.assertNotEqual(blank.get(8, 12), selected.get(8, 12))


if __name__ == '__main__':
    unittest.main()
