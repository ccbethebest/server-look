"""Missing-only directory copies using the existing SSH identity and host-key policy."""
from contextlib import contextmanager
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import threading
import uuid

from file_transfer import local_name
from ui_preferences import preferences_path


def endpoint(connection):
    return '|'.join(connection.args[-4:])


def valid_mapping(record):
    if not isinstance(record, dict) or not isinstance(record.get('name'), str):
        return False
    if 'locations' not in record:
        return all(isinstance(record.get(key), str) for key in ('local', 'remote', 'direction', 'server'))
    locations = record['locations']
    if not isinstance(locations, list) or not locations:
        return False
    if not all(isinstance(item, dict) and all(isinstance(item.get(key), str) for key in ('server', 'path')) for item in locations):
        return False
    targets = record.get('targets')
    indices = [record.get('source')] + (targets if isinstance(targets, list) else [None])
    return all(type(index) is int and 0 <= index < len(locations) for index in indices)


def load_mappings():
    try:
        records = json.loads(preferences_path().with_name('mappings.json').read_text(encoding='utf-8'))
        return [record for record in records if valid_mapping(record)]
    except (OSError, ValueError, TypeError):
        return []


def save_mappings(records):
    path = preferences_path().with_name('mappings.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, path)


class ProcessSocket:
    """Adapt native OpenSSH's SFTP subsystem to Paramiko's protocol client."""
    def __init__(self, args):
        self.process = subprocess.Popen(args[:-1] + ['-s', args[-1], 'sftp'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))

    def get_name(self):
        return "openssh-sftp"

    def send(self, data):
        self.process.stdin.write(data)
        self.process.stdin.flush()
        return len(data)

    def recv(self, size):
        return self.process.stdout.read(size)

    def close(self):
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait(timeout=5)
        self.process.stdin.close()
        self.process.stdout.close()


class DirectoryMapping:
    """Merge directories with optional file replacement and cancellation."""
    def __init__(self):
        self.stopped = threading.Event()
        self.socket = None
        self.copied = self.skipped = 0

    def cancel(self):
        self.stopped.set()
        if self.socket:
            self.socket.close()

    def check(self):
        if self.stopped.is_set():
            raise RuntimeError('映射已取消')

    @contextmanager
    def channel(self, connection):
        import paramiko
        if connection.session:
            client = connection.session.client().open_sftp()
            self.socket = client
        else:
            self.socket = ProcessSocket(connection.args)
            client = None
        try:
            if client is None:
                client = paramiko.SFTPClient(self.socket)
            yield client
        finally:
            if client:
                client.close()
            elif self.socket:
                self.socket.close()
            self.socket = None

    def run(self, connection, record, selected=()):
        self.copied = self.skipped = 0
        self.overwrite = record.get('overwrite') is True
        local = Path(record['local'])
        remote = PurePosixPath(record['remote'])
        if not local.is_absolute() or not remote.is_absolute():
            raise ValueError('映射目录必须为绝对路径')
        if endpoint(connection) != record['server']:
            raise ValueError('请连接此映射配置对应的服务器')
        upload = record['direction'] == '本地 → 服务器'
        if record['direction'] not in ('本地 → 服务器', '服务器 → 本地'):
            raise ValueError('未知映射方向')
        self.check()
        with self.channel(connection) as sftp:
            if not local.is_dir() or not stat.S_ISDIR(sftp.lstat(str(remote)).st_mode):
                raise ValueError('请先建立并选择两端的目录')
            # Validate ancestors to avoid writing through linked destination folders.
            for parent in (local, *local.parents):
                if parent.is_symlink() or (hasattr(parent, 'is_junction') and parent.is_junction()):
                    raise ValueError('映射不支持符号链接或目录联接')
            for parent in (remote, *remote.parents):
                if stat.S_ISLNK(sftp.lstat(str(parent)).st_mode):
                    raise ValueError('映射不支持符号链接目录')
            source = local if upload else remote
            paths = [Path(p) if upload else PurePosixPath(p) for p in selected]
            for item in paths:
                item.relative_to(source)  # Reject selections outside this pair.
            if not paths:
                paths = self.children(sftp, source, upload)
            for item in paths:
                relative = item.relative_to(source)
                if not relative.parts or '..' in relative.parts:
                    raise ValueError('所选项必须位于映射源目录内')
                if not upload:
                    for part in relative.parts:
                        local_name(part)
                for depth in range(1, len(relative.parts)):
                    parent = source.joinpath(*relative.parts[:depth])
                    info = self.metadata(sftp, parent, not upload)
                    if info is None or not stat.S_ISDIR(info.st_mode) or (upload and parent.is_junction()):
                        raise ValueError('源目录包含链接或已被移除')
                target = remote.joinpath(*relative.parts) if upload else local.joinpath(*relative.parts)
                # A selected descendant may have missing parent directories.
                for depth in range(1, len(relative.parts)):
                    parent = remote.joinpath(*relative.parts[:depth]) if upload else local.joinpath(*relative.parts[:depth])
                    self.ensure_directory(sftp, parent, upload)
                self.copy(sftp, item, target, upload)
        return f'映射完成：复制 {self.copied} 个文件，跳过 {self.skipped} 项'

    def children(self, sftp, source, upload):
        if upload:
            return list(source.iterdir())
        names = [entry.filename for entry in sftp.listdir_attr(str(source))]
        for name in names:
            local_name(name)
        if len({name.casefold() for name in names}) != len(names):
            raise ValueError(f'Windows 下存在同名文件：{source}')
        return [source / name for name in names]

    def metadata(self, sftp, path, remote):
        try:
            return sftp.lstat(str(path)) if remote else path.lstat()
        except FileNotFoundError:
            return None

    def ensure_directory(self, sftp, path, remote):
        info = self.metadata(sftp, path, remote)
        if info is None:
            sftp.mkdir(str(path)) if remote else path.mkdir()
        elif not stat.S_ISDIR(info.st_mode) or (not remote and path.is_junction()):
            raise ValueError(f'目标目录被文件或链接占用：{path}')

    def copy(self, sftp, source, target, upload):
        self.check()
        info = self.metadata(sftp, source, not upload)
        if info is None:
            raise FileNotFoundError(str(source))
        if stat.S_ISLNK(info.st_mode) or (upload and source.is_junction()):
            self.skipped += 1
            return
        if not upload:
            local_name(target.name)
        existing = self.metadata(sftp, target, upload)
        if stat.S_ISDIR(info.st_mode):
            if existing and not stat.S_ISDIR(existing.st_mode):
                self.skipped += 1
                return
            self.ensure_directory(sftp, target, upload)
            for child in self.children(sftp, source, upload):
                self.copy(sftp, child, target / child.name, upload)
        elif stat.S_ISREG(info.st_mode):
            if existing is not None and (not self.overwrite or not stat.S_ISREG(existing.st_mode)):
                self.skipped += 1
                return
            # Stage replacements beside the target so failed copies retain the old file.
            destination = target.with_name('.mapping-' + uuid.uuid4().hex) if self.overwrite else target
            reader = source.open('rb') if upload else sftp.open(str(source), 'rb')
            with reader:
                writer = sftp.open(str(destination), 'wx') if upload else destination.open('xb')
                try:
                    with writer:
                        while True:
                            self.check()
                            chunk = reader.read(1024 * 1024)
                            if not chunk:
                                break
                            writer.write(chunk)
                    self.check()
                    if self.overwrite:
                        if upload:
                            sftp.posix_rename(str(destination), str(target))
                        else:
                            os.replace(destination, target)
                except Exception:
                    sftp.remove(str(destination)) if upload else destination.unlink(missing_ok=True)
                    raise
            self.copied += 1
        else:
            self.skipped += 1
