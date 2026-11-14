"""Language switching preserves connection state and user data."""
import tempfile
import unittest
from pathlib import Path
import tkinter
from server_look.config.ui_preferences import validate, save_preferences, load_preferences
from server_look.localization.i18n import set_language, tr
from server_look.localization.localized_ui import ttk, tk

class LanguageTests(unittest.TestCase):
    def tearDown(self):
        set_language('zh_CN')

    def test_preferences_roundtrip_and_old_settings(self):
        self.assertEqual(validate({})['language'], 'zh_CN')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'ui.json'
            save_preferences(dict(validate({}), language='en'), path)
            self.assertEqual(load_preferences(path)['language'], 'en')
        with self.assertRaises(ValueError):
            validate({'language':'xx'})

    def test_translation_preserves_interpolated_paths(self):
        set_language('en')
        self.assertEqual(tr('连接成功'), 'Connected')
        self.assertEqual(tr('当前传输速度：12.5 MB/s'), 'Transfer speed: 12.5 MB/s')
        self.assertEqual(tr('来源 · C:/服务器/文件夹'), 'Source · C:/服务器/文件夹')
        self.assertEqual(tr('C:/服务器/文件夹'), 'C:/服务器/文件夹')

    def test_widgets_switch_without_changing_logical_values(self):
        root=tkinter.Tk();root.withdraw()
        try:
            raw=tkinter.StringVar(root, '连接成功')
            label=ttk.Label(root,textvariable=raw)
            choice=tkinter.StringVar(root,'公钥登录')
            combo=ttk.Combobox(root,textvariable=choice,values=('公钥登录','账号密码'))
            path=tkinter.StringVar(root,'C:/服务器/文件夹')
            entry=ttk.Entry(root,textvariable=path)
            notebook=ttk.Notebook(root)
            page=ttk.Frame(notebook);notebook.add(page,text='文件浏览')
            menu=tk.Menu(root,tearoff=False);menu.add_command(label='删除')
            tree=ttk.Treeview(root,columns=('name',));tree.heading('name',text='名称')
            set_language('en')
            self.assertEqual(root.getvar(label['textvariable']), 'Connected')
            self.assertEqual(raw.get(),'连接成功')
            self.assertEqual(tuple(combo['values']),('Public key','Password'))
            self.assertEqual(combo.get(),'Public key')
            combo.set('Password')
            self.assertEqual(choice.get(),'账号密码')
            self.assertEqual(entry.get(),'C:/服务器/文件夹')
            self.assertEqual(notebook.tab(page,'text'),'Files')
            self.assertEqual(menu.entrycget(0,'label'),'Delete')
            self.assertEqual(tree.heading('name','text'),'Name')
            raw.set('已断开')
            self.assertEqual(root.getvar(label['textvariable']),'Disconnected')
            set_language('zh_CN')
            self.assertEqual(combo.get(),'账号密码')
            self.assertEqual(notebook.tab(page,'text'),'文件浏览')
        finally:root.destroy()

if __name__=='__main__':unittest.main()
