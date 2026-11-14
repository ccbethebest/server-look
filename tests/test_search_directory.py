"""Search folder chooser routing without starting search workers."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from server_look.files.search_dialog import SearchDialog

class SearchDirectoryTests(unittest.TestCase):
    def dialog(self,target):
        dialog=SearchDialog.__new__(SearchDialog)
        dialog.target=Mock(get=lambda:target)
        dialog.path=Mock(get=lambda:'/data')
        dialog.window=object()
        dialog.page=SimpleNamespace(connection=object(), root='page1')
        dialog.target_pages={'当前服务器':dialog.page}
        dialog.app=SimpleNamespace(retheme=Mock(), pages={'page1':dialog.page})
        return dialog

    def test_local_selection_updates_search_path(self):
        dialog=self.dialog('本地')
        with patch('server_look.files.search_dialog.filedialog.askdirectory',return_value='C:/chosen'):
            dialog.choose_directory()
        dialog.path.set.assert_called_once_with('C:/chosen')

    def test_remote_selection_uses_existing_connection_and_callback(self):
        dialog=self.dialog('当前服务器')
        with patch('server_look.files.remote_directory_dialog.RemoteDirectoryDialog') as chooser:
            dialog.choose_directory()
        chooser.assert_called_once_with(dialog.window,dialog.page.connection,'/data',dialog.path.set)

    def test_unconnected_remote_shows_connect_message(self):
        dialog=self.dialog('当前服务器')
        dialog.page.connection=None
        with patch('server_look.files.search_dialog.messagebox.showinfo') as message, patch('server_look.files.remote_directory_dialog.RemoteDirectoryDialog') as chooser:
            dialog.choose_directory()
        message.assert_called_once()
        chooser.assert_not_called()

    def test_other_server_chooser_uses_selected_connection(self):
        dialog=self.dialog('root@other:22')
        other=SimpleNamespace(connection=object(), root='page2')
        dialog.target_pages['root@other:22']=other
        dialog.app.pages['page2']=other
        with patch('server_look.files.remote_directory_dialog.RemoteDirectoryDialog') as chooser:
            dialog.choose_directory()
        self.assertIs(chooser.call_args.args[1], other.connection)

    def test_closed_server_is_rejected(self):
        dialog=self.dialog('当前服务器')
        dialog.app.pages.clear()
        with self.assertRaisesRegex(ValueError, '已关闭'):
            dialog.selected_page()

    def test_results_locate_original_search_server(self):
        dialog=self.dialog('本地')
        other=SimpleNamespace(root='page2', connection=object(), tabs=Mock(), resources=Mock())
        dialog.search_page=other
        dialog.connection=other.connection
        dialog.remote=True
        dialog.closed=False
        dialog.tree=Mock(selection=lambda:('row',))
        dialog.items={'row':{'path':'/data/file', 'directory':False}}
        dialog.app.pages['page2']=other
        dialog.app.notebook=Mock()
        dialog.window=Mock()
        dialog.locate()
        dialog.app.notebook.select.assert_called_once_with('page2')
        other.resources.browse.assert_called_once_with('/data', select='/data/file')
        dialog.window.withdraw.assert_called_once()

    def test_remote_file_selected_after_directory_load(self):
        from server_look.ui.resource_views import ResourceViews
        view=ResourceViews.__new__(ResourceViews)
        view.path=Mock()
        view.target_node=None
        view.nodes={'/data':'node'}
        view.folders=Mock()
        view.folders.get_children.return_value=()
        view.files=Mock()
        view.files.get_children.return_value=()
        view.files.insert.return_value='file-row'
        view.hint=Mock()
        view.select_path='/data/model.bin'
        view.apply({'path':'/data','truncated':False,'entries':[
            {'path':'/data/model.bin','name':'model.bin','is_dir':False,
             'link':False,'size':12,'modified':'today'}]})
        view.files.selection_set.assert_called_once_with('file-row')
        view.files.see.assert_called_once_with('file-row')
        self.assertIsNone(view.select_path)
