"""Native OpenSSH must reuse app trust and custom-named private keys."""
from pathlib import Path
import socket
import os
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
import paramiko
from tests.test_password_integration import Server
from server_look.transport.client_core import connection_args


class KeyIntegrationTests(unittest.TestCase):
    def test_native_key_login_uses_app_known_host_with_spaces(self):
        host_key = paramiko.RSAKey.generate(2048)
        login_key = paramiko.RSAKey.generate(2048)

        class KeyServer(Server):
            def get_allowed_auths(self, username):
                return 'publickey'

            def check_auth_publickey(self, username, key):
                return (paramiko.AUTH_SUCCESSFUL if username == 'tester' and key == login_key
                        else paramiko.AUTH_FAILED)

        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        listener.settimeout(15)
        port = listener.getsockname()[1]
        done = threading.Event()
        errors = []

        def serve():
            try:
                sock, _ = listener.accept()
                with paramiko.Transport(sock) as transport:
                    transport.add_server_key(host_key)
                    transport.start_server(server=KeyServer())
                    done.wait(15)
            except Exception as exc:
                errors.append(exc)

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory(prefix='ssh home ') as folder:
                home = Path(folder)
                ssh = home / '.ssh'
                ssh.mkdir()
                private = ssh / 'custom_key'
                if os.name == 'nt':
                    account = subprocess.check_output(['whoami'], text=True).strip()
                    login_key.write_private_key_file(str(private))
                    subprocess.run(['icacls', str(private), '/inheritance:r', '/grant:r',
                                    account + ':F', '/remove:g', '*S-1-3-4'],
                                   capture_output=True, check=True)
                else:
                    login_key.write_private_key_file(str(private))
                    private.chmod(0o600)
                private.with_suffix('.pub').write_text(
                    f'{login_key.get_name()} {login_key.get_base64()} fixture\n')
                (ssh / 'server_look_known_hosts').write_text(
                    f'[127.0.0.1]:{port} {host_key.get_name()} {host_key.get_base64()}\n')
                with patch('pathlib.Path.home', return_value=home):
                    args = connection_args('127.0.0.1', 'tester', port)
                result = subprocess.run(args + ['echo-json'], input=b'{"ok":true}',
                                        capture_output=True, timeout=12)
                self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
                self.assertEqual(result.stdout, b'{"ok":true}')
                self.assertFalse(errors)
        finally:
            done.set()
            listener.close()
            thread.join(5)
