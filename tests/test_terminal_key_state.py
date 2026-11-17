"""Lock keys must not become terminal Alt shortcuts on Windows."""
import unittest
from unittest.mock import patch

from server_look.transport.terminal_input import encode_key


class TerminalKeyStateTests(unittest.TestCase):
    def test_windows_num_lock_does_not_modify_text_or_navigation(self):
        with patch('sys.platform', 'win32'):
            self.assertEqual(encode_key('p', 'p', 8), 'p')
            self.assertEqual(encode_key('Return', '\r', 8), '\r')
            self.assertEqual(encode_key('Up', state=8), '\x1b[A')
            self.assertEqual(encode_key('F5', state=8), '\x1b[15~')

    def test_windows_alt_uses_the_native_mask_even_with_num_lock(self):
        with patch('sys.platform', 'win32'):
            self.assertEqual(encode_key('p', 'p', 0x20000 | 8), '\x1bp')
            self.assertEqual(encode_key('Left', state=0x20000 | 8), '\x1b[1;3D')
            self.assertEqual(encode_key('F1', state=0x20000 | 8 | 4), '\x1b[1;7P')

    def test_x11_alt_retains_mod1_mask(self):
        with patch('sys.platform', 'linux'):
            self.assertEqual(encode_key('p', 'p', 8), '\x1bp')
            self.assertEqual(encode_key('Up', state=8), '\x1b[1;3A')


if __name__ == '__main__':
    unittest.main()
