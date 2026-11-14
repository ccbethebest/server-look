import unittest
import tkinter
from types import SimpleNamespace
from shortcut_capture import key_sequence, valid_shortcut
from shortcut_capture import shortcut_control
from ui_preferences import validate


class SettingsControlsTests(unittest.TestCase):
    def test_button_records_keys_and_escape_keeps_previous_value(self):
        root = tkinter.Tk()
        try:
            variable = tkinter.StringVar(root, '<F5>')
            control = shortcut_control(root, variable)
            control.pack()
            root.update()
            button = control.winfo_children()[0]
            button.invoke()
            button.focus_force()
            root.update()
            button.event_generate('<KeyPress>', keysym='P', state=5)
            root.update()
            self.assertEqual(variable.get(), '<Control-Shift-P>')
            triggered = []
            root.bind(variable.get(), lambda event: triggered.append(True))
            root.event_generate('<KeyPress>', keysym='P', state=5)
            root.update()
            self.assertTrue(triggered)
            button.invoke()
            button.event_generate('<KeyPress>', keysym='Escape')
            root.update()
            self.assertEqual(variable.get(), '<Control-Shift-P>')
            control.winfo_children()[1].invoke()
            self.assertEqual(variable.get(), '无')
        finally:
            root.destroy()

    def test_capture_actual_keys(self):
        self.assertEqual(key_sequence(SimpleNamespace(keysym='p', state=4)), '<Control-p>')
        self.assertEqual(key_sequence(SimpleNamespace(keysym='P', state=5)), '<Control-Shift-P>')
        self.assertEqual(key_sequence(SimpleNamespace(keysym='F12', state=0)), '<F12>')
        self.assertIsNone(key_sequence(SimpleNamespace(keysym='Control_L', state=4)))
        self.assertTrue(valid_shortcut('<Control-p>'))
        self.assertFalse(valid_shortcut('<Button-1>'))
        self.assertFalse(valid_shortcut('invalid'))

    def test_custom_keys_and_fresh_defaults(self):
        values = validate({})
        values['shortcuts']['搜索'] = '<Control-p>'
        self.assertEqual(validate(values)['shortcuts']['搜索'], '<Control-p>')
        self.assertEqual(validate({})['shortcuts']['搜索'], '<Control-f>')
        self.assertEqual(validate({})['language'], 'zh_CN')


if __name__ == '__main__':
    unittest.main()
