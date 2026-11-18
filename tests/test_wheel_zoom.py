import tkinter as tk
from tkinter import font
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from server_look.ui.theme import apply_theme
from server_look.ui.wheel_zoom import WheelZoom


class WheelZoomTests(unittest.TestCase):
    def test_existing_and_new_dialog_widgets_zoom_without_scrolling(self):
        root = tk.Tk()
        try:
            text = tk.Text(root)
            text.pack()
            root._serverlook_options = {'global_scale': 100}
            app = SimpleNamespace(root=root, preferences=root._serverlook_options,
                                  retheme=lambda: apply_theme(root), server_tabs=SimpleNamespace(draw=Mock()))
            apply_theme(root)
            zoom = WheelZoom(app)
            root.update()
            before = font.Font(root=root, font=text.cget('font')).metrics('linespace')
            scroll = Mock(return_value='break')
            text.bind('<MouseWheel>', scroll)
            with patch('server_look.ui.wheel_zoom.save_preferences') as save:
                text.event_generate('<Control-MouseWheel>', delta=120)
                root.update()
                self.assertEqual(app.preferences['global_scale'], 110)
                self.assertGreater(font.Font(root=root, font=text.cget('font')).metrics('linespace'), before)
                scroll.assert_not_called()
                win = tk.Toplevel(root)
                entry = tk.Entry(win)
                entry.pack()
                root.update()
                entry.event_generate('<Control-MouseWheel>', delta=-120)
                root.update()
                self.assertEqual(app.preferences['global_scale'], 100)
                for _ in range(25):
                    entry.event_generate('<Control-MouseWheel>', delta=120)
                self.assertEqual(app.preferences['global_scale'], 200)
                zoom.persist()
                save.assert_called_once_with(app.preferences)
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main()
