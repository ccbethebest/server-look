import tempfile, unittest, zipfile
from pathlib import Path
from server_resources import file_operation

class OperationsTests(unittest.TestCase):
    def test_copy_rename_archive_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'a').mkdir(); (root/'a'/'x.txt').write_text('hello')
            (root/'dest').mkdir()
            file_operation(tmp, 'copy', names=['a'], destination=str(root/'dest'))
            file_operation(str(root/'dest'), 'rename', names=['a'], name='b')
            file_operation(str(root/'dest'), 'compress', names=['b'], name='bundle.zip')
            file_operation(str(root/'dest'), 'extract', names=['bundle.zip'], name='unpacked')
            self.assertEqual((root/'dest/unpacked/b/x.txt').read_text(), 'hello')
            with self.assertRaises(FileExistsError):
                file_operation(str(root/'dest'), 'rename', names=['b'], name='bundle.zip')
    def test_reject_traversal_and_recursive_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'a').mkdir()
            with self.assertRaises(ValueError): file_operation(tmp,'copy',names=['a'],destination=str(root/'a'))
            with zipfile.ZipFile(root/'bad.zip','w') as z: z.writestr('../escape','bad')
            with self.assertRaises(ValueError): file_operation(tmp,'extract',names=['bad.zip'],name='out')
            self.assertFalse((root/'out').exists())
            with self.assertRaises(ValueError): file_operation(tmp,'rename',names=['a'],name='../x')

if __name__ == '__main__': unittest.main()

class OperationUITests(unittest.TestCase):
    def setUp(self):
        from tkinterdnd2 import TkinterDnD
        from server_page import ServerPage
        self.root=TkinterDnD.Tk(); self.page=ServerPage(self.root)
        self.local=self.page.resources.local
    def tearDown(self): self.page.close()
    def test_copy_then_navigate_and_paste(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'a').write_text('copy'); (root/'dest').mkdir()
            self.local.path.set(tmp); self.local.browse()
            row=next(i for i,p in self.local.items.items() if p.name=='a')
            self.local.files.selection_set(row); self.local.operate(False,'copy')
            self.local.path.set(str(root/'dest')); self.local.browse()
            with patch.object(self.local,'launch',side_effect=lambda work,title:work()): self.local.operate(False,'paste')
            self.assertEqual((root/'dest/a').read_text(),'copy')
    def test_readonly_blocks_all_remote_mutations(self):
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        self.page.connection=SimpleNamespace(close=lambda:None)
        self.page.readonly.set(True)
        with patch.object(self.local,'launch') as launch, patch('local_files.simpledialog.askstring') as dialog:
            for action in ('mkdir','paste','rename','compress','extract'): self.local.operate(True,action)
            launch.assert_not_called(); dialog.assert_not_called()

class AgentOperationTests(unittest.TestCase):
    def test_persistent_agent_rename_and_compress(self):
        import json, subprocess, sys
        from directory_channel import DIRECTORY_AGENT
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'a').write_text('data')
            requests=[dict(source=Path('server_resources.py').read_text(encoding='utf-8')),
                      dict(path=tmp,action='rename',names=['a'],options={'name':'b'}),
                      dict(path=tmp,action='compress',names=['b'],options={'name':'b.zip'})]
            result=subprocess.run([sys.executable,'-c',DIRECTORY_AGENT],input=''.join(json.dumps(r)+'\n' for r in requests),capture_output=True,text=True,check=True)
            self.assertTrue(all('result' in json.loads(line) for line in result.stdout.splitlines()),result.stdout)
            self.assertTrue((Path(tmp)/'b.zip').is_file())
