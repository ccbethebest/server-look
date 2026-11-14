"""Password SSH transport. Secrets stay in memory; host keys must be trusted already."""
from pathlib import Path
import base64
import hashlib
import threading
import time

from settings import SSH_REQUEST_TIMEOUT_SECONDS


class Utf8Stream:
    def __init__(self, stream):
        self.stream = stream

    def write(self, value):
        return self.stream.write(value.encode('utf-8'))

    def flush(self):
        self.stream.flush()

    def __iter__(self):
        for line in self.stream:
            yield line.decode('utf-8', errors='replace') if isinstance(line, bytes) else line

    def close(self):
        self.stream.close()


class RemoteProcess:
    def __init__(self, client, command):
        stdin, stdout, _ = client.exec_command(command, timeout=SSH_REQUEST_TIMEOUT_SECONDS)
        self.channel = stdout.channel
        self.channel.settimeout(None)  # Directory protocol enforces its own request deadline.
        self.stdin = Utf8Stream(stdin)
        self.stdout = Utf8Stream(stdout)

    def poll(self):
        return 0 if self.channel.closed or self.channel.exit_status_ready() else None

    def kill(self):
        self.channel.close()


class PasswordSession:
    def __init__(self, host, user, port, password):
        self.host, self.user, self.port = host, user, port
        self.password = password
        self.lock = threading.Lock()
        self._client = None
        self.closed = False
        self.failure = None
        self.pending_host_key = None

    def client(self):
        import paramiko
        with self.lock:
            if self.closed:
                raise RuntimeError('服务器已断开')
            if self.failure:
                raise RuntimeError(self.failure)
            if self._client is not None:
                transport = self._client.get_transport()
                if transport is not None and transport.is_active():
                    return self._client
                self._client.close()
                self._client = None
            client = paramiko.SSHClient()
            session = self
            class ConfirmHostKey(paramiko.MissingHostKeyPolicy):
                def missing_host_key(self, client, hostname, key):
                    session.pending_host_key = (hostname, key)
                    raise paramiko.SSHException('需要确认服务器主机指纹')
            client.set_missing_host_key_policy(ConfirmHostKey())
            known = Path.home() / '.ssh' / 'known_hosts'
            if known.exists():
                client.load_host_keys(str(known))
            app_known = Path.home() / '.ssh' / 'server_look_known_hosts'
            if app_known.exists():
                client.load_host_keys(str(app_known))
            try:
                client.connect(hostname=self.host, port=self.port, username=self.user,
                               password=self.password, allow_agent=False, look_for_keys=False,
                               timeout=10, auth_timeout=10, banner_timeout=10)
            except paramiko.AuthenticationException:
                client.close()
                self.failure = '账号密码认证失败，请检查密码及服务器是否允许密码登录，然后重新连接'
                raise RuntimeError(self.failure) from None
            except paramiko.BadHostKeyException:
                client.close()
                self.failure = '服务器主机密钥已变化，连接已阻止。请联系管理员核对，不能直接信任替换后的密钥'
                raise RuntimeError(self.failure) from None
            except paramiko.SSHException:
                client.close()
                self.failure = ('首次连接，需要确认服务器主机指纹' if self.pending_host_key else
                                'SSH 握手失败，请检查 SSH 端口、网络以及服务器支持的加密算法')
                raise RuntimeError(self.failure) from None
            except Exception:
                client.close()
                raise
            if self.closed:
                client.close()
                raise RuntimeError("服务器已断开")
            client.get_transport().set_keepalive(5)
            self._client = client
            return client

    def host_key_prompt(self):
        if not self.pending_host_key:
            return None
        hostname, key = self.pending_host_key
        fingerprint = base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip('=')
        return f'服务器：{hostname}\n密钥类型：{key.get_name()}\n指纹：SHA256:{fingerprint}\n\n请与服务器管理员提供的指纹核对。是否信任并继续连接？'

    def confirm_host_key(self, trusted):
        import paramiko
        with self.lock:
            pending, self.pending_host_key = self.pending_host_key, None
            if not trusted or not pending or self.closed:
                return
            hostname, key = pending
            known = Path.home() / '.ssh' / 'server_look_known_hosts'
            known.parent.mkdir(parents=True, exist_ok=True)
            keys = paramiko.HostKeys()
            if known.exists():
                keys.load(str(known))
            keys.add(hostname, key.get_name(), key)
            keys.save(str(known))
            self.failure = None

    def open_process(self, command):
        return RemoteProcess(self.client(), command)

    def execute(self, command, payload):
        channel = self.client().get_transport().open_session(timeout=10)
        channel.settimeout(SSH_REQUEST_TIMEOUT_SECONDS)
        try:
            channel.exec_command(command)
            channel.sendall(payload.encode('utf-8'))
            channel.shutdown_write()
            output, errors = bytearray(), bytearray()
            deadline = time.monotonic() + SSH_REQUEST_TIMEOUT_SECONDS
            while True:
                if channel.recv_ready():
                    output.extend(channel.recv(65536))
                if channel.recv_stderr_ready():
                    errors.extend(channel.recv_stderr(65536))
                if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError('SSH 请求超时')
                time.sleep(0.01)
            if channel.recv_exit_status():
                raise RuntimeError((errors or output).decode('utf-8', errors='replace')[-2500:])
            return output.decode('utf-8')
        finally:
            channel.close()

    def close(self):
        # Closing the socket also interrupts in-flight directory/transfer requests.
        self.closed = True
        self.password = None
        if self._client:
            self._client.close()
