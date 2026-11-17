from types import SimpleNamespace
from unittest.mock import patch

from tests.test_command_usability import CommandUsabilityTests
from server_look.ui.text_actions import bind_text_menu


class TerminalTextActionsTests(CommandUsabilityTests):
    def type_echo(self, text):
        self.panel.transmit(self.item, text)
        self.item['stream'].feed(text)
        self.panel.render(self.item)
        self.item['session'].send.reset_mock()

    def select(self, text):
        output = self.item['output']
        start = output.search(text, '1.0')
        self.assertTrue(start)
        output.tag_add('sel', start, f'{start}+{len(text)}c')

    def test_single_right_click_without_selection_pastes_to_remote(self):
        output = self.item['output']
        output.clipboard_clear()
        output.clipboard_append('pwd')
        output.event_generate('<Button-3>', x=10, y=10)
        self.root.update()
        self.item['session'].send.assert_called_once_with('pwd')

    def test_right_click_with_selection_offers_copy_without_sending(self):
        self.type_echo('echo sample')
        self.select('sample')
        menu = self.item['text_menu']
        with patch.object(menu, 'tk_popup') as popup:
            self.panel.right_click(SimpleNamespace(x_root=10, y_root=20), self.item)
            popup.assert_called_once_with(10, 20)
        self.assertEqual(str(menu.entrycget(2, 'state')), 'normal')
        menu.invoke(0)
        self.assertEqual(self.root.clipboard_get(), 'sample')
        self.item['session'].send.assert_not_called()

    def test_delete_middle_selection_moves_remote_cursor_and_deletes(self):
        self.type_echo('echo abcXYZdef')
        self.select('XYZ')
        self.item['output'].event_generate('<KeyPress-Delete>')
        self.root.update()
        self.item['session'].send.assert_called_once_with('\x1b[D' * 3 + '\x7f' * 3)
        self.assertEqual(self.item['shell_line'].text, 'echo abcdef')
        self.assertEqual(self.item['shell_line'].cursor, 8)

    def test_prompt_and_executed_output_cannot_be_deleted(self):
        self.type_echo('pwd')
        self.select('root@host')
        self.panel.delete_selection(self.item)
        self.item['session'].send.assert_not_called()
        self.panel.transmit(self.item, '\r')
        self.item['session'].send.reset_mock()
        self.item['output'].tag_remove('sel', '1.0', 'end')
        self.select('pwd')
        self.panel.delete_selection(self.item)
        self.item['session'].send.assert_not_called()

    def test_stale_or_wrapped_output_is_not_editable(self):
        self.type_echo('echo typed')
        self.select('typed')
        self.item['stream'].feed('\r\nbackground output')
        self.panel.delete_selection(self.item)
        self.item['session'].send.assert_not_called()

    def test_readonly_blocks_selected_deletion(self):
        self.type_echo('echo test')
        self.select('test')
        self.page.readonly.set(True)
        self.panel.delete_selection(self.item)
        self.item['session'].send.assert_not_called()
        self.assertEqual(self.item['shell_line'].text, 'echo test')

    def test_command_entry_ctrl_c_copies_and_right_click_pastes(self):
        entry = self.item['command_entry']
        entry.insert(0, 'abcdef')
        entry.selection_range(1, 4)
        entry.focus_force()
        self.root.update()
        entry.event_generate('<Control-c>')
        self.root.update()
        self.assertEqual(entry.clipboard_get(), 'bcd')
        self.item['session'].send.assert_not_called()
        menu = bind_text_menu(entry)
        menu.invoke(2)
        self.assertEqual(entry.get(), 'aef')
        entry.icursor('end')
        entry.event_generate('<Button-3>', x=10, y=10)
        self.root.update()
        self.assertEqual(entry.get(), 'aefbcd')

    def test_python_multiline_menu_delete_can_be_undone(self):
        self.panel.new_python()
        self.root.update()
        item = list(self.panel.sessions.values())[-1]
        editor = item['editor']
        editor.insert('1.0', 'print(1)\nprint(2)')
        editor.edit_separator()
        editor.tag_add('sel', '1.0', '2.0')
        menu = bind_text_menu(editor)
        menu.invoke(2)
        self.assertEqual(editor.get('1.0', 'end-1c'), 'print(2)')
        editor.edit_undo()
        self.assertEqual(editor.get('1.0', 'end-1c'), 'print(1)\nprint(2)')
