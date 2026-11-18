"""Platform boundaries can be verified without a Mac or a live SSH server."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
import plistlib
import shlex

from server_look import paths
from server_look.transport.terminal_input import encode_key


class MacPlatformTests(unittest.TestCase):
    def test_bundle_launcher_quotes_install_paths_and_has_icon(self):
        from tools.install_macos import make_application
        with tempfile.TemporaryDirectory(prefix="Server Look ' ") as folder, patch('subprocess.run') as run:
            target = Path(folder)
            app = make_application(target, '2.22.0')
            with (app / 'Contents' / 'Info.plist').open('rb') as stream:
                metadata = plistlib.load(stream)
            self.assertEqual(metadata['CFBundleShortVersionString'], '2.22.0')
            self.assertEqual(metadata['CFBundleIconFile'], 'server.icns')
            launcher = (app / 'Contents' / 'MacOS' / 'server-look').read_text()
            self.assertEqual(shlex.split(launcher.splitlines()[1]),
                             ['exec', str(target / '.venv/bin/python'), str(target / 'npu_client.pyw')])
            self.assertEqual(run.call_count, 11)
            self.assertEqual(run.call_args.args[0][0], 'iconutil')

    def test_installer_rejects_home_before_writing(self):
        from tools.install_macos import install
        with patch.object(Path, 'mkdir') as mkdir:
            with self.assertRaisesRegex(ValueError, '专用'):
                install(Path.home())
            mkdir.assert_not_called()

    def test_mac_shortcut_aliases_keep_control_and_add_command(self):
        from server_look.ui.platform_ui import command_aliases, shortcut_sequences, window_mode
        bindings = {'<Control-Key-s>': 'save-script', '<F3>': 'find-script'}
        def bind(sequence=None, script=None):
            if sequence is None: return tuple(bindings)
            if script is None: return bindings.get(sequence, '')
            bindings[sequence] = script
        widget = Mock()
        widget.bind.side_effect = bind
        with patch('sys.platform', 'darwin'):
            command_aliases(widget)
            self.assertEqual(shortcut_sequences('<Control-c>'), ('<Control-c>', '<Command-c>'))
            root = Mock()
            root.winfo_screenwidth.return_value = 1440
            root.winfo_screenheight.return_value = 900
            window_mode(root, True)
        self.assertEqual(bindings['<Control-Key-s>'], bindings['<Command-Key-s>'])
        self.assertEqual(bindings['<F3>'], 'find-script')
        root.state.assert_called_once_with('normal')
        root.geometry.assert_called_once_with('1440x820+0+25')

    def test_preferences_use_application_support(self):
        with patch('sys.platform', 'darwin'), patch.object(Path, 'home', return_value=Path('/Users/test')):
            self.assertEqual(paths.user_data_dir(), Path('/Users/test/Library/Application Support/ServerLook'))

    def test_option_is_alt_and_command_is_not_alt(self):
        with patch('sys.platform', 'darwin'):
            self.assertEqual(encode_key('Left', state=16), '\x1b[1;3D')
            self.assertEqual(encode_key('Left', state=8), '\x1b[D')
            self.assertEqual(encode_key('c', state=4), '\x03')

    def test_finder_receives_literal_path(self):
        from server_look.files.file_transfer import open_local_folder
        with tempfile.TemporaryDirectory(prefix='Server Look ') as folder:
            with patch('sys.platform', 'darwin'), patch('subprocess.Popen') as launch:
                open_local_folder(folder)
            launch.assert_called_once_with(['open', str(Path(folder).resolve())])

    def test_keychain_reference_and_forget(self):
        from server_look.transport.connection_history import ConnectionHistory
        secrets = {}
        class Keychain:
            def set_password(self, service, name, password): secrets[name] = password
            def get_password(self, service, name): return secrets.get(name)
            def delete_password(self, service, name): secrets.pop(name)
        with tempfile.TemporaryDirectory() as folder, patch('sys.platform', 'darwin'), patch(
                'server_look.transport.mac_keychain.backend', return_value=Keychain()):
            history = ConnectionHistory(Path(folder) / 'connections.json')
            record = dict(host='example.test', user='root', port='22', auth_mode='password')
            history.save(record, 'private-password', True)
            self.assertNotIn('private-password', history.path.read_text())
            self.assertEqual(history.password(history.load()[0]), 'private-password')
            history.save(record, 'updated-secret', True)
            self.assertEqual(len(secrets), 1)
            history.save(record, remember=False)
            self.assertEqual(secrets, {})
            history.save(record, 'delete-secret', True)
            history.delete(record)
            self.assertEqual(secrets, {})

    def test_history_write_failure_removes_only_new_keychain_secret(self):
        from server_look.transport.connection_history import ConnectionHistory
        from server_look.transport import mac_keychain
        with tempfile.TemporaryDirectory() as folder, patch('sys.platform', 'darwin'), patch.object(
                mac_keychain, 'save', return_value='keychain:new'), patch.object(mac_keychain, 'delete') as delete:
            history = ConnectionHistory(Path(folder) / 'connections.json')
            record = dict(host='example.test', user='root', port='22', auth_mode='password', password='keychain:old')
            history._write([record])
            with patch.object(history, '_write', side_effect=OSError('disk full')):
                with self.assertRaises(OSError): history.save(record, 'secret', True)
                delete.assert_called_once_with('keychain:new')
                delete.reset_mock()
                with self.assertRaises(OSError): history.delete(record)
                delete.assert_not_called()
            self.assertEqual(history.load(), [record])


if __name__ == '__main__':
    unittest.main()
