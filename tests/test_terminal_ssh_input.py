"""Real encrypted SSH channel + mapped Tk key events, using a local test shell."""
import socket
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
import unittest
import paramiko

from server_look.ui.command_panel import CommandPanel


class TestShell(paramiko.ServerInterface):
    def check_auth_none(self, username):
        return paramiko.AUTH_SUCCESSFUL

    def check_channel_request(self, kind, chanid):
        return paramiko.OPEN_SUCCEEDED

    def check_channel_pty_request(self, *args):
        return True

    def check_channel_shell_request(self, channel):
        return True


class SSHKeyboardIntegrationTests(unittest.TestCase):
    def test_keyboard_command_entry_echo_interrupt_and_close(self):
        server_socket, client_socket = socket.socketpair()
        server = paramiko.Transport(server_socket)
        client = paramiko.Transport(client_socket)
        server.add_server_key(paramiko.RSAKey.generate(2048))
        errors = []
        def serve():
            try:
                server.start_server(server=TestShell())
                channel = server.accept(5)
                channel.sendall(b'(base) [root@test ~]# ')
                line = b''
                while True:
                    data = channel.recv(4096)
                    if not data:
                        return
                    for byte in data:
                        if byte == 3:
                            line = b''
                            channel.sendall(b'^C\r\n(root@test)# ')
                        elif byte in (10, 13):
                            if line == b'pwd':
                                channel.sendall(b'\r\n/test/home\r\n(root@test)# ')
                            line = b''
                        else:
                            line += bytes([byte])
                            channel.sendall(bytes([byte]))
            except (EOFError, OSError):
                pass  # Expected when the test closes the client.
            except Exception as exc:
                errors.append(exc)
        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        root = panel = None
        try:
            client.start_client(timeout=5)
            client.auth_none('tester')
            ssh_client = SimpleNamespace(get_transport=lambda: client)
            connection = SimpleNamespace(session=SimpleNamespace(client=lambda: ssh_client))
            root = tk.Tk()
            root.geometry('1000x700')
            tabs = ttk.Notebook(root)
            tabs.pack(fill='both', expand=True)
            page = SimpleNamespace(root=root, tabs=tabs, connection=connection,
                                   readonly=tk.BooleanVar(value=False), generation=1)
            panel = CommandPanel(page)
            panel.new_shell()
            item = next(iter(panel.sessions.values()))
            def wait_for(predicate):
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline:
                    root.update()
                    if predicate():
                        return
                    time.sleep(.01)
                self.fail('SSH/Tk condition timed out: ' + panel.notice.get())
            wait_for(lambda: item['ready'] and 'root@test' in item['output'].get('1.0', 'end'))
            # Let the editor setup finish before sending the interactive command.
            wait_for(lambda: item['session'].input.empty())
            root.focus_force()
            item['output'].focus_set()
            root.update()
            root.event_generate('<KeyPress-Z>')
            wait_for(lambda: 'Z' in item['output'].get('1.0', 'end'))
            root.event_generate('<Control-KeyPress-c>')
            wait_for(lambda: '^C' in item['output'].get('1.0', 'end'))
            # Num Lock must not turn plain terminal typing into Alt shortcuts.
            for key in ('p', 'w', 'd', 'Return'):
                root.event_generate('<KeyPress-' + key + '>',
                                    state=8 if sys.platform == 'win32' else 0)
                root.update()
            wait_for(lambda: '/test/home' in item['output'].get('1.0', 'end'))
            item['command_entry'].focus_set()
            root.update()
            for key in ('p', 'w', 'd', 'Return'):
                root.event_generate('<KeyPress-' + key + '>')
                root.update()
            wait_for(lambda: item['output'].get('1.0', 'end').count('/test/home') == 2)
            session = item['session']
            panel.close_current()
            session.thread.join(2)
            self.assertFalse(session.thread.is_alive())
            self.assertEqual(errors, [])
        finally:
            if panel:
                panel.close()
            if root:
                root.destroy()
            client.close()
            server.close()
            thread.join(2)


if __name__ == '__main__':
    unittest.main()
