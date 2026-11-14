import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from server_look.remote.file_search import run_search
from server_look.config.ui_preferences import validate, save_preferences, load_preferences

class SearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root/'nested').mkdir()
        (self.root/'Model.BIN').write_text('x')
        (self.root/'nested'/'model.bin').write_text('x')
        (self.root/'notes.txt').write_text('x')
    def search(self, pattern, **options):
        return run_search(str(self.root), pattern, **options)
    def test_matching_modes_and_case(self):
        self.assertEqual(len(self.search('model')['results']), 2)
        self.assertEqual(len(self.search('model', case_sensitive=True)['results']), 1)
        self.assertEqual(len(self.search('Model.BIN', mode='完全匹配')['results']), 2)
        self.assertEqual(len(self.search('*.bin', mode='通配符')['results']), 2)
        self.assertEqual(len(self.search('mdl', mode='近似匹配')['results']), 2)
        self.assertFalse(self.search('lmd', mode='近似匹配')['results'])
        self.assertEqual(len(self.search(r'^model\.bin$', mode='正则表达式')['results']), 2)
        self.assertEqual(len(self.search(r'^model\.bin$', mode='正则表达式', case_sensitive=True)['results']), 1)
    def test_scope_kind_limits_and_validation(self):
        self.assertEqual(len(self.search('model', recursive=False)['results']), 1)
        self.assertEqual(len(self.search('nested', kind='文件夹')['results']), 1)
        self.assertFalse(self.search('nested', kind='文件')['results'])
        limited = self.search('model', limit=1)
        self.assertEqual(limited['reason'], '达到结果上限')
        self.assertEqual(len(limited['results']), 1)
        with self.assertRaises(Exception):
            self.search('[', mode='正则表达式')
        with self.assertRaises(ValueError):
            run_search(str(self.root/'missing'), 'a')
    def test_cancel_and_deadline(self):
        event = threading.Event()
        event.set()
        self.assertIn('已停止', self.search('x', cancel=event)['reason'])
        self.assertIn('超时', self.search('x', seconds=0)['reason'])

    def test_batches_match_final_results(self):
        batches = []
        result = self.search('model', on_batch=batches.extend)
        self.assertEqual(batches, result['results'])
    def test_windows_junction_is_not_followed(self):
        import os
        if os.name != 'nt':
            self.skipTest('Windows junction test')
        import subprocess
        junction = self.root/'link'
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        (Path(outside.name)/'external.txt').write_text('x')
        subprocess.run(['cmd', '/c', 'mklink', '/J', str(junction), outside.name], check=True, capture_output=True)
        try:
            self.assertFalse(self.search('external')['results'])
        finally:
            junction.rmdir()

class PreferencesTests(unittest.TestCase):
    def test_roundtrip_and_conflicting_keys(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'prefs.json'
            values = validate({'readonly': True, 'font_size': 14, 'navigation': '左侧竖排'})
            save_preferences(values, path)
            self.assertEqual(load_preferences(path), values)
            values['shortcuts']['搜索'] = values['shortcuts']['帮助']
            with self.assertRaises(ValueError):
                validate(values)
            path.write_text('[]')
            self.assertEqual(load_preferences(path)['font_size'], 10)
    def test_live_layout_and_readonly_and_dialogs(self):
        import tkinter as tk
        from server_look.app.desktop_app import MultiServerApp
        root = tk.Tk()
        root.withdraw()
        with tempfile.TemporaryDirectory() as folder:
            from server_look.transport.connection_history import ConnectionHistory
            store = ConnectionHistory(Path(folder)/'history.json')
            with patch('server_look.app.server_page.ConnectionHistory', return_value=store), patch('server_look.app.desktop_app.load_preferences', return_value=validate({})):
                app = MultiServerApp(root)
                try:
                    app.apply_preferences(validate({'readonly': True, 'navigation': '左侧竖排', 'font_size': 12, 'button_font': 11, 'button_size': '宽松'}))
                    root.update_idletasks()
                    self.assertEqual(app.navigation.pack_info()['side'], 'left')
                    self.assertTrue(app.current_page().readonly.get())
                    self.assertTrue(app.add_server().readonly.get())
                    app.show_settings()
                    app.show_search()
                    app.show_help()
                    root.update_idletasks()
                    self.assertTrue(app.help_window.winfo_exists())
                    self.assertEqual(str(tk.ttk.Style(root).lookup('TButton', 'font')), '{Microsoft YaHei UI} 11')
                finally:
                    app.close()

if __name__ == '__main__':
    unittest.main()
