"""Local SSH protocol integration: no real credentials or remote configuration changes."""
import json
import os
from types import SimpleNamespace
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import patch
import paramiko
from password_transport import PasswordSession
from directory_channel import DirectoryChannel

class Server(paramiko.ServerInterface):
    def check_auth_password(self, username, password):
        return paramiko.AUTH_SUCCESSFUL if (username, password) == ('tester', 'test-only') else paramiko.AUTH_FAILED

    def get_allowed_auths(self, username):
        return 'password'

    def check_channel_request(self, kind, chanid):
        return paramiko.OPEN_SUCCEEDED if kind == 'session' else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_channel_exec_request(self, channel, command):
        def respond():
            try:
                if command == b'echo-json':
                    chunks = []
                    while True:
                        part = channel.recv(65536)
                        if not part:
                            break
                        chunks.append(part)
                    channel.sendall(b''.join(chunks))
                else:
                    stream = channel.makefile('rb')
                    json.loads(stream.readline())  # Directory bootstrap source.
                    for line in stream:
                        request = json.loads(line)
                        channel.sendall((json.dumps({'result': {'path': request['path']}}) + '\n').encode())
                channel.send_exit_status(0)
            except (EOFError, OSError):
                pass
            finally:
                try:
                    channel.close()
                except (EOFError, OSError):
                    pass
        threading.Thread(target=respond, daemon=True).start()
        return True

class LocalSFTP(paramiko.SFTPServerInterface):
    def __init__(self, server, root):
        super().__init__(server)
        self.root = Path(root).resolve()

    def path(self, value):
        path = (self.root / value.lstrip('/')).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError('outside fixture')
        return path

    def stat(self, path):
        try:
            return paramiko.SFTPAttributes.from_stat(self.path(path).stat())
        except OSError as exc:
            return paramiko.SFTPServer.convert_errno(exc.errno)

    lstat = stat

    def list_folder(self, path):
        rows = []
        for item in self.path(path).iterdir():
            attrs = paramiko.SFTPAttributes.from_stat(item.stat())
            attrs.filename = item.name
            rows.append(attrs)
        return rows

    def mkdir(self, path, attr):
        try:
            self.path(path).mkdir()
            return paramiko.SFTP_OK
        except OSError as exc:
            return paramiko.SFTPServer.convert_errno(exc.errno)

    def open(self, path, flags, attr):
        try:
            fd = os.open(self.path(path), flags | getattr(os, 'O_BINARY', 0), 0o600)
            stream = os.fdopen(fd, 'wb' if flags & os.O_WRONLY else 'rb')
            handle = paramiko.SFTPHandle(flags)
            handle.readfile = handle.writefile = stream
            return handle
        except OSError as exc:
            return paramiko.SFTPServer.convert_errno(exc.errno)


class PasswordIntegrationTests(unittest.TestCase):
    def test_real_password_auth_exec_and_persistent_directory(self):
        key = paramiko.RSAKey.generate(2048)
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        fixture = tempfile.TemporaryDirectory()
        done = threading.Event()
        transports = []
        def serve():
            sock, _ = listener.accept()
            transport = paramiko.Transport(sock)
            transports.append(transport)
            transport.add_server_key(key)
            transport.set_subsystem_handler("sftp", paramiko.SFTPServer, LocalSFTP, root=fixture.name)
            transport.start_server(server=Server())
            done.wait(20)
            transport.close()
        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        session = PasswordSession('127.0.0.1', 'tester', port, 'test-only')
        directory = DirectoryChannel([], opener=session.open_process)
        try:
            with tempfile.TemporaryDirectory() as folder:
                home = Path(folder)
                (home / '.ssh').mkdir()
                (home / '.ssh' / 'known_hosts').write_text(f'[127.0.0.1]:{port} {key.get_name()} {key.get_base64()}\n')
                with patch('password_transport.Path.home', return_value=home):
                    self.assertEqual(json.loads(session.execute('echo-json', '{"ok":true}')), {'ok': True})
                    self.assertEqual(directory.request('/')['path'], '/')
                    process = directory.process
                    self.assertEqual(directory.request('/mnt')['path'], '/mnt')
                    self.assertIs(directory.process, process)
                    from file_transfer import Transfer
                    source = home / 'example [folder]'
                    source.mkdir()
                    (source / '中文.txt').write_text('双向传输', encoding='utf-8')
                    destination = home / 'download'
                    destination.mkdir()
                    connection = SimpleNamespace(session=session)
                    Transfer().run_connection(connection, 'upload', source.as_posix(), '/')
                    Transfer().run_connection(connection, 'download', '/example [folder]', destination.as_posix())
                    self.assertEqual((destination / source.name / '中文.txt').read_text(encoding='utf-8'), '双向传输')
                    from directory_mapping import DirectoryMapping, endpoint
                    connection.args = ['ssh', '-p', str(port), '-l', 'tester', '127.0.0.1']
                    record = dict(local=source.as_posix(), remote='/example [folder]',
                                  direction='本地 → 服务器', server=endpoint(connection))
                    (source / 'added.txt').write_text('mapped', encoding='utf-8')
                    DirectoryMapping().run(connection, record)
                    self.assertEqual((Path(fixture.name) / source.name / 'added.txt').read_text(), 'mapped')
                    (source / 'added.txt').write_text('keep local', encoding='utf-8')
                    record['direction'] = '服务器 → 本地'
                    DirectoryMapping().run(connection, record)
                    self.assertEqual((source / 'added.txt').read_text(), 'keep local')
                    (Path(fixture.name) / 'second.txt').write_text('second', encoding='utf-8')
                    Transfer().run_many_connection(connection, 'download',
                                                   ['/second.txt', '/example [folder]'], destination.as_posix())
                    self.assertEqual((destination / 'second.txt').read_text(encoding='utf-8'), 'second')
                    self.assertEqual((destination / source.name / '中文.txt').read_text(encoding='utf-8'), '双向传输')
        finally:
            directory.close()
            session.close()
            done.set()
            listener.close()
            thread.join(5)
            fixture.cleanup()
