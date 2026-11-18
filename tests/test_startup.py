"""Startup failures must remain visible when pythonw has no console."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class StartupTests(unittest.TestCase):
    def test_missing_dependency_reports_traceback_to_file_and_dialog(self):
        from server_look.app.launcher import run
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ, APPDATA=folder), \
                    patch('server_look.app.launcher.start_application', side_effect=ImportError('missing pyte')), \
                    patch('server_look.app.launcher.show_error') as dialog:
                self.assertEqual(run(), 1)
                log = Path(folder) / 'ServerLook' / 'startup.log'
                self.assertIn('missing pyte', log.read_text(encoding='utf-8'))
                self.assertIn(str(log), dialog.call_args.args[0])

    def test_normal_start_returns_success_without_error_dialog(self):
        from server_look.app.launcher import run
        with patch('server_look.app.launcher.start_application'), \
                patch('server_look.app.launcher.show_error') as dialog:
            self.assertEqual(run(), 0)
            dialog.assert_not_called()
