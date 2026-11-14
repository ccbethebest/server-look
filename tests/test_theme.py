import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from server_look.transport.connection_history import ConnectionHistory
from server_look.ui.theme import PALETTES, apply_theme, load_theme, save_theme


class ThemeTests(unittest.TestCase):
    def test_preferences_roundtrip_and_invalid_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'appearance.json'
            self.assertEqual(load_theme(path), '深海蓝')
            for name in PALETTES:
                save_theme(name, path)
                self.assertEqual(load_theme(path), name)
            path.write_text('{broken', encoding='utf-8')
            self.assertEqual(load_theme(path), '深海蓝')
            with self.assertRaises(ValueError):
                save_theme('unknown', path)

    def test_live_switch_existing_widgets_and_new_pages(self):
        from server_look.app.desktop_app import MultiServerApp
        with tempfile.TemporaryDirectory() as folder:
            root = tk.Tk()
            root.withdraw()
            store = ConnectionHistory(Path(folder) / 'connections.json')
            with patch('server_look.app.server_page.ConnectionHistory', return_value=store), patch('server_look.app.desktop_app.load_theme', return_value='深海蓝'), patch('server_look.app.desktop_app.save_theme') as persist:
                app = MultiServerApp(root)
                try:
                    page = next(iter(app.pages.values()))
                    self.assertEqual(len(PALETTES), 3)
                    self.assertEqual(page.connection_dialog.state(), 'withdrawn')
                    page.host.set('example.test')
                    root.deiconify()
                    root.update()
                    page.show_connection_dialog()
                    root.update()
                    self.assertEqual(page.connection_dialog.state(), 'normal')
                    page.connection_dialog.withdraw()
                    root.withdraw()
                    self.assertEqual(page.host.get(), 'example.test')
                    for name, palette in PALETTES.items():
                        app.theme_name.set(name)
                        app.change_theme()
                        root.update_idletasks()
                        self.assertEqual(root.cget('background'), palette[0])
                        self.assertEqual(page.npu.cget('background'), palette[1])
                        self.assertEqual(page.npu.cget('foreground'), palette[3])
                        self.assertEqual(tk.ttk.Style(root).lookup('ConnectionPending.TLabel', 'foreground'),
                                         palette[5] if name == '云雾白' else '#8dd9ff')
                        self.assertEqual(str(page.error_button.cget('compound')), 'left')
                        self.assertTrue(page.error_button._serverlook_image.width())
                    persist.assert_called_with('云雾白')
                    other = app.add_server()
                    self.assertEqual(root._serverlook_theme, '云雾白')
                    self.assertEqual(other.details.cget('background'), PALETTES['云雾白'][1])
                    self.assertIsNone(page.connection)
                    self.assertIsNone(other.connection)
                    self.assertEqual(str(app.notebook.cget('style')), 'Server.TNotebook')
                    app.close_page()
                    self.assertEqual(str(app.notebook.cget('style')), 'Solo.Server.TNotebook')
                    page.tabs.select(2)
                    root.update()
                    self.assertEqual(page.view_choice.get(), page.tabs.select())
                    self.assertFalse(page.controls.winfo_manager())
                    self.assertFalse(page.details.winfo_manager())
                    page.tabs.select(0)
                    root.update()
                    self.assertEqual(page.controls.winfo_manager(), 'pack')
                    self.assertFalse(page.details.winfo_manager())
                    for widget in app.navigation_buttons:
                        self.assertFalse(widget.cget('text'))
                        self.assertEqual(widget._serverlook_image.width(), 40)
                        widget.tooltip.show()
                        self.assertTrue(widget.tooltip.window.winfo_exists())
                        widget.tooltip.hide()
                        self.assertIsNone(widget.tooltip.window)
                finally:
                    app.close()
