"""Mapped Tk keyboard delivery and command-page refresh policy."""
import queue
import sys
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from server_look.app.server_page import ServerPage
from server_look.ui.command_panel import CommandPanel


class CommandUsabilityTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry('900x650')
        self.book = ttk.Notebook(self.root)
        self.book.pack(fill='both', expand=True)
        self.page = SimpleNamespace(root=self.root, tabs=self.book, connection=object(),
                                    readonly=tk.BooleanVar(value=False), generation=1)
        self.patch = patch('server_look.ui.command_panel.TerminalSession',
                           side_effect=lambda *a, **k: MagicMock(events=queue.Queue()))
        self.patch.start()
        self.panel = CommandPanel(self.page)
        self.root.update()
        self.root.focus_force()
        self.panel.new_shell()
        self.item = next(iter(self.panel.sessions.values()))
        self.item['session'].events.put(('ready', None))
        self.item['session'].events.put(('data', '(base) [root@host ~]# '))
        self.panel.poll_session(self.item)
        self.root.update()
        self.item['session'].send.reset_mock()

    def tearDown(self):
        self.panel.close()
        self.root.destroy()
        self.patch.stop()

    def test_terminal_receives_mapped_key_events(self):
        self.item['output'].focus_set()
        self.root.update()
        for key in ('<KeyPress-a>', '<KeyPress-Return>', '<Control-KeyPress-c>'):
            self.root.event_generate(key)
            self.root.update()
        self.assertEqual([c.args[0] for c in self.item['session'].send.call_args_list],
                         ['a', '\r', '\x03'])

    @unittest.skipUnless(sys.platform == 'win32', 'Windows native keyboard state')
    def test_native_char_messages_with_num_lock_send_plain_command(self):
        import ctypes
        user = ctypes.windll.user32
        saved = (ctypes.c_ubyte * 256)()
        self.assertTrue(user.GetKeyboardState(saved))
        locked = (ctypes.c_ubyte * 256)()
        locked[0x90] = 1  # VK_NUMLOCK toggled on, with no modifiers held.
        self.panel.activate_terminal(self.item)
        self.root.update()
        try:
            self.assertTrue(user.SetKeyboardState(locked))
            for char in 'pwd\r':
                self.assertTrue(user.PostMessageW(self.item['output'].winfo_id(),
                                                 0x0102, ord(char), 1))
                self.root.update()
        finally:
            user.SetKeyboardState(saved)
        self.assertEqual([c.args[0] for c in self.item['session'].send.call_args_list],
                         ['p', 'w', 'd', '\r'])

    def test_explicit_activation_recovers_focus_and_sends_to_current_session(self):
        self.item['command_entry'].focus_set()
        self.root.update()
        self.panel.activate_terminal(self.item)
        self.root.update()
        self.assertIs(self.root.focus_get(), self.item['output'])
        self.assertIn('已启用', self.item['input_status'].get())
        self.root.event_generate('<KeyPress-p>')
        self.root.update()
        self.item['session'].send.assert_called_once_with('p')

    def test_new_session_focus_is_applied_after_widget_is_mapped(self):
        self.item['command_entry'].focus_set()
        self.root.update()
        self.panel.new_shell()
        new_item = list(self.panel.sessions.values())[-1]
        self.root.update()
        self.assertIs(self.root.focus_get(), new_item['output'])
        self.assertIn('已启用', new_item['input_status'].get())

    def test_background_tab_never_takes_focus(self):
        self.panel.new_shell()
        newer = list(self.panel.sessions.values())[-1]
        self.root.update()
        newer['command_entry'].focus_set()
        self.root.update()
        self.panel.activate_terminal(self.item)
        self.root.update()
        self.assertIs(self.root.focus_get(), newer['command_entry'])

    def test_command_entry_displays_input_and_return_sends_once(self):
        entry = self.item['command_entry']
        entry.focus_set()
        self.root.update()
        for key in ('p', 'w', 'd'):
            self.root.event_generate('<KeyPress-' + key + '>')
            self.root.update()
        self.assertEqual(entry.get(), 'pwd')
        self.root.event_generate('<KeyPress-Return>')
        self.root.update()
        self.item['session'].send.assert_called_once_with('pwd\r')
        self.assertEqual(entry.get(), '')

    def test_unready_command_is_preserved_and_explained(self):
        self.item['ready'] = False
        self.item['command_entry'].insert(0, 'pwd')
        self.panel.execute_command(self.item)
        self.item['session'].send.assert_not_called()
        self.assertEqual(self.item['command_entry'].get(), 'pwd')
        self.assertIn('连接', self.panel.notice.get())


class RefreshPolicyTests(unittest.TestCase):
    def test_tick_pauses_snapshot_in_command_page_and_resumes_elsewhere(self):
        page = ServerPage.__new__(ServerPage)
        page.closed = False
        page.root = MagicMock()
        page.tabs = MagicMock()
        page.commands = SimpleNamespace(frame='command-frame')
        page.refresh = MagicMock()
        page.tabs.select.return_value = 'command-frame'
        page.tick()
        page.refresh.assert_not_called()
        page.root.after.assert_called_once()
        page.tabs.select.return_value = 'task-frame'
        page.tick()
        page.refresh.assert_called_once()


if __name__ == '__main__':
    unittest.main()
