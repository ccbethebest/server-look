"""Interactive PTY channels; all blocking I/O happens outside the Tk thread."""
import codecs
import json
from pathlib import Path
import queue
import threading


def python_command(source):
    return 'exec(compile(' + json.dumps(source, ensure_ascii=True) + ", '<ServerLook cell>', 'exec'))\n"


class TerminalSession:
    def __init__(self, connection, python=False, columns=100, rows=28):
        self.connection, self.python = connection, python
        self.columns, self.rows = columns, rows
        self.events = queue.Queue(maxsize=128)
        self.input = queue.Queue(maxsize=128)
        self.stop = threading.Event()
        self.channel = self.client = None
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _event(self, kind, value):
        while not self.stop.is_set():
            try:
                self.events.put((kind, value), timeout=.1)
                return
            except queue.Full:
                pass

    def _run(self):
        import paramiko
        try:
            if self.connection.session:
                client = self.connection.session.client()
            else:
                client = self.client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.RejectPolicy())
                client.load_system_host_keys()
                for filename in ('known_hosts', 'server_look_known_hosts'):
                    path = Path.home() / '.ssh' / filename
                    if path.exists():
                        client.load_host_keys(str(path))
                args = self.connection.args
                identities = [args[index + 1] for index, value in enumerate(args[:-1]) if value == '-i']
                client.connect(hostname=args[-1], username=args[args.index('-l') + 1],
                               port=int(args[args.index('-p') + 1]), timeout=10,
                               auth_timeout=10, banner_timeout=10,
                               key_filename=identities or None)
                client.get_transport().set_keepalive(5)
            if self.stop.is_set():
                return
            channel = self.channel = client.get_transport().open_session(timeout=10)
            channel.get_pty(term='xterm', width=self.columns, height=self.rows)
            if self.python:
                channel.exec_command('python3 -u -i -q')
            else:
                channel.invoke_shell()
            channel.settimeout(.2)
            self._event('ready', None)
            decoder = codecs.getincrementaldecoder('utf-8')('replace')
            while not self.stop.is_set():
                try:
                    kind, value = self.input.get_nowait()
                except queue.Empty:
                    pass
                else:
                    if kind == 'send':
                        channel.sendall(value.encode('utf-8'))
                    else:
                        channel.resize_pty(width=value[0], height=value[1])
                if channel.recv_ready():
                    data = channel.recv(32768)
                    if not data:
                        break
                    self._event('data', decoder.decode(data))
                elif channel.closed or channel.exit_status_ready():
                    break
                else:
                    self.stop.wait(.015)
            self._event('data', decoder.decode(b'', final=True))
            self._event('closed', '会话已结束')
        except Exception as exc:
            self._event('error', str(exc))
        finally:
            if self.channel:
                self.channel.close()
            if self.client:
                self.client.close()

    def send(self, text):
        if not self.stop.is_set():
            self.input.put_nowait(('send', text))

    def resize(self, columns, rows):
        if (columns, rows) != (self.columns, self.rows):
            self.columns, self.rows = columns, rows
            if not self.stop.is_set():
                try:
                    self.input.put_nowait(('resize', (columns, rows)))
                except queue.Full:
                    pass

    def close(self):
        self.stop.set()
        if self.channel:
            self.channel.close()
        if self.client:
            self.client.close()
