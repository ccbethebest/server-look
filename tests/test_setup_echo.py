"""Internal bridge installation must not flood the interactive terminal."""
import unittest
from unittest.mock import patch
from server_look.transport.terminal_editor import EditorBridge, editor_command, editor_setup


class SetupEchoTests(unittest.TestCase):
    def test_wrapped_chunked_echo_is_hidden_but_command_and_output_remain(self):
        bridge = EditorBridge('echo_test')
        command = editor_command('python', 'echo_test')
        # Readline may wrap at any column and toggle bracketed paste around input.
        echo = '\r\n'.join(command[i:i+71] for i in range(0, len(command), 71))
        wire = 'root# ' + '\x1b[?2004h' + echo + '\r\n\x1b[?2004l' + 'Python output\r\n'
        visible = ''
        for char in wire:
            visible += bridge.feed(char)[0]
        self.assertEqual(visible, 'root# \x1b[?2004hpython\r\n\x1b[?2004lPython output\r\n')

    def test_setup_errors_and_editor_protocol_are_preserved(self):
        bridge = EditorBridge('echo_test')
        wire = editor_setup('echo_test') + '\r\nsh: setup failed\r\n'
        visible, requests = bridge.feed(wire)
        self.assertEqual(visible, '\r\nsh: setup failed\r\n')
        self.assertEqual(requests, [])
        visible, requests = bridge.feed('\x1b]777;server-look;echo_test;@/tmp/a.py\x07')
        self.assertEqual(requests, ['/tmp/a.py'])

    def test_no_echo_and_unrelated_text_pass_through(self):
        bridge = EditorBridge('echo_test')
        text = 'banner\r\nroot# pwd\r\n/root\r\n'
        self.assertEqual(bridge.feed(text)[0], text)
        # An unrelated colon-prefixed command must not be swallowed.
        self.assertEqual(bridge.feed(': ordinary\r\n')[0], ': ordinary\r\n')

    def test_incomplete_echo_times_out_and_fails_open(self):
        bridge = EditorBridge('echo_test')
        with patch('server_look.transport.terminal_editor.time.monotonic', return_value=0):
            visible, _ = bridge.feed(editor_setup('echo_test')[:180])
        self.assertEqual(visible, '')
        with patch('server_look.transport.terminal_editor.time.monotonic', return_value=10):
            visible, _ = bridge.feed('')
        self.assertTrue(visible)
        self.assertEqual(bridge.feed('root# pwd')[0], 'root# pwd')

    def test_oversized_incomplete_echo_fails_open_and_foreign_marker_is_visible(self):
        bridge = EditorBridge('echo_test')
        text = editor_setup('foreign')
        self.assertEqual(bridge.feed(text)[0], text)
        text = editor_setup('echo_test')[:180] + 'x' * 33000
        self.assertEqual(bridge.feed(text)[0], text)
        self.assertEqual(bridge.feed('root# ')[0], 'root# ')
