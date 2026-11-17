"""Terminal protocol regressions, independent of a particular remote host."""
import unittest
from types import SimpleNamespace
import pyte
from server_look.transport.terminal_screen import TerminalScreen
from tests.test_terminal_recovery import TerminalRecoveryTests


class ScreenCompatibilityTests(unittest.TestCase):
    def test_vim_alternate_screen_restores_shell_and_cursor(self):
        screen = TerminalScreen(30, 5, history=20)
        stream = pyte.Stream(screen)
        stream.feed('shell prompt> \x1b[?1049h\x1b[Hvim file\r\nline two')
        self.assertNotIn('shell', '\n'.join(screen.display))
        stream.feed('\x1b[?1049l')
        self.assertTrue(screen.display[0].startswith('shell prompt> '))
        self.assertEqual((screen.cursor.x, screen.cursor.y), (14, 0))

    def test_alternate_screen_scrolling_does_not_pollute_shell_history(self):
        screen = TerminalScreen(20, 3, history=20)
        stream = pyte.Stream(screen)
        stream.feed('shell\x1b[?1049h' + 'file line\r\n' * 10 + '\x1b[?1049l')
        self.assertEqual(len(screen.history.top), 0)
        self.assertTrue(screen.display[0].startswith('shell'))

    def test_resize_in_vim_preserves_shell_and_new_dimensions(self):
        screen = TerminalScreen(30, 6, history=20)
        stream = pyte.Stream(screen)
        stream.feed('shell\x1b[?1049hvim')
        screen.resize(lines=4, columns=25)
        stream.feed('\x1b[?1049l')
        self.assertEqual((screen.columns, screen.lines), (25, 4))
        self.assertIn('shell', '\n'.join(screen.display))


class KeyboardCompatibilityTests(TerminalRecoveryTests):
    def setUp(self):
        super().setUp()
        self.item['ready'] = True

    def press(self, key, state=0, char=''):
        self.panel.keypress(SimpleNamespace(keysym=key, state=state, char=char), self.item)

    def test_vim_application_arrow_mode(self):
        self.item['stream'].feed('\x1b[?1h')
        self.press('Up')
        self.item['session'].send.assert_called_with('\x1bOA')
        self.item['stream'].feed('\x1b[?1l')
        self.press('Up')
        self.item['session'].send.assert_called_with('\x1b[A')

    def test_function_keys_and_ctrl_arrow(self):
        self.press('F5')
        self.item['session'].send.assert_called_with('\x1b[15~')
        self.press('Left', state=4)
        self.item['session'].send.assert_called_with('\x1b[1;5D')

    def test_bracketed_paste_prevents_immediate_multiline_execution(self):
        self.item['output'].clipboard_clear()
        self.item['output'].clipboard_append('one\ntwo')
        self.item['stream'].feed('\x1b[?2004h')
        from unittest.mock import patch
        with patch('server_look.ui.command_panel.messagebox.askyesno', return_value=True):
            self.panel.paste(self.item)
        self.item['session'].send.assert_called_with('\x1b[200~one\ntwo\x1b[201~')

    def test_wide_text_cursor_uses_text_character_index(self):
        self.item['stream'].feed('中文a')
        self.panel.render(self.item)
        self.assertEqual(self.item['output'].index('insert'), '1.3')
