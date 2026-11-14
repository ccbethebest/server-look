import unittest
from unittest.mock import patch
from file_transfer import sftp_quote, open_local_folder
import tkinter as tk
from server_page import ServerPage


class FileTransferTests(unittest.TestCase):
    def test_protocol_quotes_spaces_quotes_and_backslashes(self):
        self.assertEqual(sftp_quote('a "b"'), '"a \\"b\\""')
        for path in ('bad\nput x y', 'bad\rname', 'bad\0name'):
            with self.assertRaises(ValueError):
                sftp_quote(path)

    def test_open_folder_uses_explorer_without_shell(self):
        with patch('file_transfer.os.startfile', create=True) as launch:
            open_local_folder('.')
            launch.assert_called_once()

    def test_local_folder_double_click_enters_client_directory(self):
        root = tk.Tk()
        page = ServerPage(root)
        try:
            local = page.resources.local
            iid = next(i for i, path in local.items.items() if path.is_dir())
            local.files.selection_set(iid)
            target = local.items[iid]
            with patch('local_files.open_local_folder') as launch:
                self.assertIn('enter', local.files.bind('<Double-1>'))
                local.enter(object())
                launch.assert_not_called()
            self.assertEqual(local.current, target.resolve())
            self.assertEqual(local.path.get(), str(target.resolve()))
        finally:
            page.close()

    def test_open_window_button_keeps_client_directory(self):
        root = tk.Tk()
        page = ServerPage(root)
        try:
            local = page.resources.local
            current = local.current
            with patch('local_files.open_local_folder') as launch:
                local.open()
                launch.assert_called_once_with(current)
            self.assertEqual(local.current, current)
        finally:
            page.close()

