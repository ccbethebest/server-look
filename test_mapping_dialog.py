"""Tk mapping rows and two-pane selection regression tests."""
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from mapping_dialog import MappingDialog
from mapping_browser import MappingBrowser


class MappingDialogTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name)/'source'
        self.target = Path(self.temp.name)/'target'
        self.source.mkdir()
        self.target.mkdir()
        local = SimpleNamespace(current=self.source,active=False,launch=Mock())
        self.page = SimpleNamespace(connection=None,resources=SimpleNamespace(local=local,current='/'))
        app = SimpleNamespace(root=self.root,pages={},retheme=lambda:None)
        with patch('mapping_dialog.load_mappings',return_value=[]):
            self.dialog = MappingDialog(app,self.page)
        self.addCleanup(self.dialog.close)
        self.record = self.dialog.current()
        self.record['locations'][1]['path'] = str(self.target)

    def test_add_edit_save_and_cancel_are_independent(self):
        self.dialog.new_record()
        self.assertEqual(len(self.dialog.rows),2)
        self.dialog.directories.selection_set(self.record['id'])
        with patch('mapping_dialog.filedialog.askdirectory',return_value=str(self.target)):
            self.dialog.choose_folder(self.record['id'],1)
        with patch('mapping_dialog.save_mappings') as save:
            self.dialog.save()
        saved = save.call_args.args[0][0]
        self.assertEqual(saved['locations'][1]['path'],str(self.target))
        self.assertEqual(saved['source'],0)
        self.assertEqual(saved['targets'],[1])
        self.dialog.remove()
        self.assertEqual(len(self.dialog.rows),1)
        self.assertEqual(len(self.dialog.records),1) # Cancelling a row keeps history.

    def test_inline_path_editor_updates_row_and_visual_picker(self):
        self.root.update()
        iid = self.record['id']
        self.dialog.edit_cell(iid,'#3')
        editor = self.dialog.edit_widget
        self.assertIsNotNone(editor)
        entry = next(widget for widget in editor.winfo_children() if widget.winfo_class()=='TEntry')
        entry.delete(0,'end')
        entry.insert(0,str(self.target))
        self.assertEqual(self.record['locations'][1]['path'],str(self.target))
        with patch('mapping_dialog.filedialog.askdirectory',return_value=str(self.target)):
            self.dialog.choose_folder(iid,1)
        self.assertIsNone(self.dialog.edit_widget)

    def test_folder_buttons_are_visible_and_edit_selected_mapping(self):
        self.root.deiconify()
        self.dialog.window.deiconify()
        self.root.update()
        self.assertEqual([button.cget('text') for button in self.dialog.folder_buttons[self.record['id']]],
                         ['选择文件夹', '选择文件夹'])
        for index, button in enumerate(self.dialog.folder_buttons[self.record['id']]):
            self.assertTrue(button.winfo_ismapped())
            self.assertGreater(button.winfo_width(), 100)
            box = self.dialog.directories.bbox(self.record['id'],f'#{index+2}')
            self.assertGreater(button.winfo_x(),box[0])
            self.assertEqual(button.winfo_y(),box[1]+3)
            with patch('mapping_dialog.filedialog.askdirectory', return_value=str(self.target)) as picker:
                button.invoke()
                picker.assert_called_once()
            self.assertEqual(self.record['locations'][index]['path'], str(self.target))

    def test_row_buttons_select_their_own_mapping_and_clean_up(self):
        self.dialog.new_record()
        second = self.dialog.current()
        self.dialog.directories.selection_set(self.record['id'])
        with patch('mapping_dialog.filedialog.askdirectory',return_value=str(self.target)):
            self.dialog.folder_buttons[second['id']][0].invoke()
        self.assertEqual(self.dialog.current()['id'],second['id'])
        self.assertEqual(second['locations'][0]['path'],str(self.target))
        self.dialog.remove()
        self.assertNotIn(second['id'],self.dialog.folder_buttons)

    def test_confirmation_can_cancel_or_start_selected_mapping(self):
        with patch('mapping_dialog.messagebox.askyesno',return_value=False) as confirm, patch.object(self.dialog,'run') as run:
            self.dialog.confirm_run()
            run.assert_not_called()
            self.assertIn(str(self.target),confirm.call_args.args[1])
            confirm.return_value = True
            self.dialog.confirm_run()
            run.assert_called_once_with(self.record)

    def test_history_window_opens_larger(self):
        self.root.deiconify()
        self.dialog.window.deiconify()
        self.dialog.show_history()
        self.root.update()
        history = next(win for win in self.dialog.window.winfo_children() if isinstance(win,tk.Toplevel))
        self.assertGreaterEqual(history.winfo_width(),900)
        self.assertGreaterEqual(history.winfo_height(),500)
        history.destroy()

    def test_selected_paths_copy_only_requested_files(self):
        from multi_mapping import MultiMapping
        nested = self.source/'nested'
        nested.mkdir()
        (nested/'chosen.txt').write_text('chosen')
        (nested/'other.txt').write_text('other')
        MultiMapping().run_many({},self.record,(str(nested/'chosen.txt'),))
        self.assertEqual((self.target/'nested'/'chosen.txt').read_text(),'chosen')
        self.assertFalse((self.target/'nested'/'other.txt').exists())

    def test_one_click_uses_selected_row_and_full_directory(self):
        with patch('mapping_dialog.MultiMapping') as factory:
            self.assertTrue(self.dialog.run())
            worker = self.page.resources.local.launch.call_args.args[0]
            worker()
        args = factory.return_value.run_many.call_args.args
        self.assertEqual(args[1]['locations'],self.record['locations'])
        self.assertEqual(args[2],())
        self.dialog.running = False

    def test_browser_selection_and_nested_paths(self):
        (self.source/'one.txt').write_text('one')
        (self.source/'two.txt').write_text('two')
        nested = self.source/'nested'
        nested.mkdir()
        (nested/'inside.txt').write_text('inside')
        browser = MappingBrowser(self.dialog,self.record)
        self.dialog.browsers.append(browser)
        pane = browser.panes[0]
        self.wait_loaded(pane)
        selected = [iid for iid,item in pane.items.items() if not item['is_dir']]
        pane.tree.selection_set(selected)
        with patch.object(self.dialog,'run') as run:
            pane.map_selected()
            self.assertEqual(set(run.call_args.args[1]),{str(self.source/'one.txt'),str(self.source/'two.txt')})
            pane.map_directory()
            self.assertEqual(run.call_args.args[1],())
            pane.browse(nested)
            self.wait_loaded(pane)
            pane.map_directory()
            self.assertEqual(run.call_args.args[1],(str(nested),))
        pane.browse(self.source.parent)
        self.assertEqual(pane.current,nested)

    def test_browser_can_change_mapping_root_and_choose_local_folder(self):
        browser = MappingBrowser(self.dialog,self.record)
        self.dialog.browsers.append(browser)
        pane = browser.panes[1]
        self.wait_loaded(pane)
        with patch('mapping_browser.filedialog.askdirectory', return_value=str(self.source)):
            pane.choose_folder()
        self.wait_loaded(pane)
        self.assertEqual(pane.root,self.source)
        self.assertEqual(browser.record['locations'][1]['path'],str(self.source))
        self.assertEqual(self.record['locations'][1]['path'],str(self.source))
        self.assertIn(self.source.anchor.replace('\\','/'), pane.drive['values'])
        pane.browse(self.source/'missing',change_root=True)
        self.wait_loaded(pane)
        self.assertEqual(pane.root,self.source)
        self.assertEqual(self.record['locations'][1]['path'],str(self.source))

    def test_remote_listing_reuses_connection_and_cache(self):
        connection = Mock()
        connection.request.return_value = dict(path='/data',entries=[])
        from mapping_browser import DirectoryPane
        parent = tk.Toplevel(self.root)
        browser = SimpleNamespace(owner=self.dialog,record=self.record)
        pane = DirectoryPane(browser,parent,dict(server='host',path='/data'),connection,True)
        try:
            self.wait_loaded(pane)
            pane.browse('/data')
            connection.request.assert_called_once_with('list_directory',path='/data')
        finally:
            pane.close()
            parent.destroy()

    def wait_loaded(self,pane):
        deadline = time.monotonic()+3
        while pane.loading and time.monotonic()<deadline:
            self.root.update()
            time.sleep(.01)
        self.assertFalse(pane.loading)
