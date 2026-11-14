import tempfile, unittest
from pathlib import Path
from server_look.transport.connection_history import ConnectionHistory, protect, unprotect

class HistoryTests(unittest.TestCase):
    def test_encrypted_roundtrip_deduplicate_forget(self):
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'history.json'; store=ConnectionHistory(file)
            record=dict(host='example.test',user='root',port='22',auth_mode='password')
            store.save(record,'private-password',True)
            self.assertNotIn('private-password',file.read_text())
            self.assertEqual(store.password(store.load()[0]),'private-password')
            store.save(record,'new-secret',True)
            self.assertEqual(len(store.load()),1)
            self.assertEqual(store.password(store.load()[0]),'new-secret')
            store.save(record,'ignored',False)
            self.assertEqual(store.password(store.load()[0]),'')
            store.delete(store.load()[0]); self.assertEqual(store.load(),[])
    def test_dpapi_rejects_modified_ciphertext(self):
        token=protect('秘密 password')
        self.assertEqual(unprotect(token),'秘密 password')
        import base64
        data=bytearray(base64.b64decode(token)); data[-1]^=1
        with self.assertRaises(OSError): unprotect(base64.b64encode(data).decode())
    def test_corrupt_history_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'history.json';file.write_text('broken')
            with self.assertRaises(ValueError): ConnectionHistory(file).save(dict(host='host',user='root',port='22',auth_mode='key'))
            self.assertEqual(file.read_text(),'broken')

class HistoryUITests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from unittest.mock import patch
        self.temporary=tempfile.TemporaryDirectory()
        self.store=ConnectionHistory(Path(self.temporary.name)/'connections.json')
        self.root=tk.Tk(); self.root.withdraw()
        with patch('server_look.app.server_page.ConnectionHistory',return_value=self.store):
            from server_look.app.server_page import ServerPage
            self.page=ServerPage(self.root)
    def tearDown(self):
        self.page.close(); self.temporary.cleanup()
    def test_history_fills_credentials_and_delete_removes_password(self):
        self.store.save(dict(host='example.test',user='alice',port='2222',auth_mode='password'),'secret',True)
        self.page.reload_history();self.page.history_selector.current(0);self.page.select_history()
        self.assertEqual((self.page.host.get(),self.page.user.get(),self.page.port.get(),self.page.password.get()),('example.test','alice','2222','secret'))
        self.assertEqual(str(self.page.password_entry.cget('state')),'normal')
        self.page.forget_history()
        self.assertEqual(self.store.load(),[]);self.assertEqual(self.page.password.get(),'')
    def test_only_success_saves_original_attempt_not_edited_fields(self):
        from unittest.mock import patch, Mock
        self.page.host.set('example.test');self.page.user.set('alice');self.page.auth_mode.set('账号密码');self.page.password.set('secret')
        with patch('server_look.app.server_page.Connection',return_value=Mock(session=None)),patch.object(self.page,'refresh'):
            self.page.connect()
        self.assertEqual(self.store.load(),[])
        self.assertEqual(self.page.connection_state.get(),'连接中…')
        self.page.host.set('edited.test')
        self.root.after_cancel(self.page.poll_job)
        self.page.results.put((self.page.generation,'snapshot',None,'failed'))
        self.page.poll();self.assertEqual(self.store.load(),[])
        self.assertEqual(self.page.connection_state.get(),'连接失败')
        self.assertEqual(self.page.connection_error,'failed')
        self.root.after_cancel(self.page.poll_job)
        self.page.results.put((self.page.generation,'snapshot',{'host':'server','time':'now'},None))
        with patch.object(self.page,'render'):
            self.page.poll()
        self.assertEqual(self.page.connection_state.get(),'连接成功')
        self.assertEqual(self.page.connection_error,'')
        saved=self.store.load()[0]
        self.assertEqual(saved['host'],'example.test');self.assertEqual(self.store.password(saved),'secret')
        self.assertIsNone(self.page.pending_history)

    def test_validation_failure_and_disconnect_states(self):
        from unittest.mock import patch
        with patch('server_look.app.server_page.Connection',side_effect=ValueError('端口必须为 1–65535')), patch('server_look.app.server_page.messagebox.showerror') as dialog:
            self.page.connect()
            self.assertEqual(self.page.connection_state.get(),'连接失败')
            self.page.show_connection_error()
            self.assertEqual(dialog.call_count,2)
        self.page.disconnect()
        self.assertEqual(self.page.connection_state.get(),'已断开')
        self.assertEqual(self.page.connection_error,'')
        self.assertIn('disabled',self.page.error_button.state())
