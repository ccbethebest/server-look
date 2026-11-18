"""SFTP batch transport. Paths are data, never shell commands."""
import os
import sys
from pathlib import Path
import subprocess
import threading
import shutil
import time
import stat
import posixpath


def local_name(name):
    """Reject names Windows would reinterpret or silently alias."""
    reserved = {'CON', 'PRN', 'AUX', 'NUL'} | {f'{p}{n}' for p in ('COM', 'LPT') for n in range(1, 10)}
    if (not name or name in ('.', '..') or name.endswith((' ', '.'))
            or any(ord(c) < 32 or c in '/\\:<>"|?*' for c in name)
            or name.split('.')[0].upper() in reserved):
        raise ValueError('Windows 不支持该文件名：' + name)
    return name


def sftp_quote(path):
    if any(char in str(path) for char in '\r\n\0'):
        raise ValueError('路径不能包含换行或空字符')
    return '"' + str(path).replace('\\', '\\\\').replace('"', '\\"') + '"'


def open_local_folder(path):
    folder = Path(path).resolve(strict=True)
    if not folder.is_dir():
        raise ValueError('请选择本地文件夹')
    if sys.platform == 'darwin':
        subprocess.Popen(['open', str(folder)])
    elif os.name == 'nt':
        os.startfile(str(folder))
    else:
        subprocess.Popen(['xdg-open', str(folder)])


class Transfer:
    def __init__(self, progress=None):
        self.progress = progress
        self.batch = (0, 1)
        self.last_progress = 0
        self.lock = threading.Lock()
        self.process = None
        self.cancelled = False
        self.sftp = None
        self.bytes_done = 0
        self.bytes_total = None
        self.phase = 'counting'

    def report(self, completed=None, force=False):
        now = time.monotonic()
        if self.progress and (force or now - self.last_progress >= 0.1):
            self.last_progress = now
            self.progress({'completed': self.batch[0] if completed is None else completed,
                           'total': self.batch[1], 'bytes_done': self.bytes_done,
                           'bytes_total': self.bytes_total, 'phase': self.phase})

    def measure(self, sources, sftp=None):
        """Count the whole batch before copying, without following links."""
        def size(path):
            self.check()
            info = sftp.lstat(str(path)) if sftp else Path(path).lstat()
            if stat.S_ISLNK(info.st_mode) or (not sftp and Path(path).is_junction()):
                raise ValueError('暂不传输符号链接或目录联接：' + str(path))
            if stat.S_ISDIR(info.st_mode):
                if sftp:
                    names = sftp.listdir(str(path))
                    if any(name in ('.', '..') or any(c in name for c in '/\\\0') for name in names):
                        raise ValueError('目录包含不支持的文件名')
                    children = [posixpath.join(str(path), name) for name in names]
                else:
                    children = Path(path).iterdir()
                return sum(size(child) for child in children)
            if not stat.S_ISREG(info.st_mode):
                raise ValueError('仅支持普通文件和文件夹')
            return info.st_size
        self.bytes_total = sum(size(source) for source in sources)
        self.bytes_done = 0
        self.phase = 'transferring'
        self.report(force=True)

    def check(self):
        if self.cancelled:
            raise RuntimeError('传输已取消；目标可能保留部分文件')

    def run_many_connection(self, connection, direction, sources, destination):
        sources = [Path(source).as_posix() if direction == 'upload' else str(source) for source in sources]
        if direction == 'download':
            import posixpath
            names = [local_name(posixpath.basename(source.rstrip('/'))) for source in sources]
            if len({name.casefold() for name in names}) != len(names):
                raise ValueError('选中项含 Windows 下重名的文件')
        self.batch = (0, len(sources))
        self.report(force=True)
        if direction == 'upload' and getattr(connection, 'session', None):
            self.measure(sources)
        elif getattr(connection, 'session', None):
            sftp = connection.session.client().open_sftp()
            try:
                with self.lock:
                    self.check()
                    self.sftp = sftp
                sftp.get_channel().settimeout(40)
                self.measure(sources, sftp)
            finally:
                with self.lock:
                    self.sftp = None
                sftp.close()
        self.phase = 'transferring'
        for index, source in enumerate(sources):
            self.batch = (index, len(sources))
            self.check()
            self.report(force=True)
            self.run_connection(connection, direction, source, destination)
            self.report(completed=index + 1, force=True)

    def copy_local(self, sources, destination):
        destination = Path(destination)
        self.batch = (0, len(sources))
        self.report(force=True)
        self.measure(sources)

        def copy(src, dst):
            self.check()
            if src.is_symlink() or dst.is_symlink() or src.is_junction() or dst.is_junction():
                raise ValueError('暂不复制符号链接或目录联接')
            if src.resolve() == dst.resolve() or src.resolve() in dst.resolve().parents:
                raise ValueError('目标不能为来源或来源的子目录')
            if src.is_dir():
                dst.mkdir(exist_ok=True)
                for child in src.iterdir():
                    copy(child, dst / child.name)
            elif src.is_file():
                with src.open('rb') as reader, dst.open('wb') as writer:
                    while chunk := reader.read(1024 * 1024):
                        self.check()
                        writer.write(chunk)
                        self.bytes_done += len(chunk)
                        self.report()
                shutil.copystat(src, dst)
            else:
                raise ValueError('仅支持普通文件和文件夹')

        for index, source in enumerate(sources):
            self.batch = (index, len(sources))
            source = Path(source)
            copy(source, destination / local_name(source.name))
            self.report(completed=index + 1, force=True)

    def cancel(self):
        with self.lock:
            self.cancelled = True
            if self.sftp:
                self.sftp.close()
            if self.process and self.process.poll() is None:
                self.process.kill()

    def run_connection(self, connection, direction, source, destination):
        if not connection.session:
            return self.run(connection.args, direction, source, destination)
        import posixpath
        import stat
        sftp = connection.session.client().open_sftp()
        try:
            with self.lock:
                if self.cancelled:
                    raise RuntimeError('传输已取消')
                self.sftp = sftp
            sftp.get_channel().settimeout(40)

            file_done = 0

            def check(*args):
                nonlocal file_done
                if self.cancelled:
                    raise RuntimeError('传输已取消；目标可能保留部分文件')
                if len(args) == 2:
                    self.bytes_done += max(0, args[0] - file_done)
                    file_done = args[0]
                    if self.bytes_total is not None:
                        self.bytes_total = max(self.bytes_total, self.bytes_done)
                    self.report(force=args[0] == args[1])

            def copy(src, dst):
                nonlocal file_done
                check()
                mode = Path(src).lstat().st_mode if direction == 'upload' else sftp.lstat(src).st_mode
                if stat.S_ISLNK(mode):
                    raise ValueError('暂不传输符号链接：' + src)
                if stat.S_ISDIR(mode):
                    if direction == 'upload':
                        try:
                            sftp.mkdir(dst)
                        except OSError:
                            if not stat.S_ISDIR(sftp.lstat(dst).st_mode):
                                raise
                        names = [p.name for p in Path(src).iterdir()]
                    else:
                        if Path(dst).is_symlink() or Path(dst).is_junction():
                            raise ValueError('目标为符号链接：' + dst)
                        Path(dst).mkdir(exist_ok=True)
                        names = sftp.listdir(src)
                        if len({n.casefold() for n in names}) != len(names):
                            raise ValueError('目录包含 Windows 下重名的文件：' + src)
                    for name in names:
                        if name in ('.', '..') or any(c in name for c in '/\\\x00'):
                            raise ValueError('目录包含不支持的文件名')
                        if direction == 'download':
                            local_name(name)
                        copy(posixpath.join(src, name), posixpath.join(dst, name))
                elif stat.S_ISREG(mode):
                    file_done = 0
                    if direction == 'upload':
                        try:
                            if stat.S_ISLNK(sftp.lstat(dst).st_mode):
                                raise ValueError('目标为符号链接：' + dst)
                        except FileNotFoundError:
                            pass
                        sftp.put(src, dst, callback=check)
                    else:
                        if Path(dst).is_symlink() or Path(dst).is_junction():
                            raise ValueError('目标为符号链接：' + dst)
                        sftp.get(src, dst, callback=check)
                else:
                    raise ValueError('仅支持普通文件和文件夹：' + src)

            name = posixpath.basename(source.rstrip('/'))
            if not name or name in ('.', '..') or any(c in name for c in '/\\\x00'):
                raise ValueError('请选择具体文件或文件夹')
            if direction == 'download':
                local_name(name)
            copy(source, posixpath.join(destination, name))
        finally:
            sftp.close()
            with self.lock:
                self.sftp = None

    def run(self, ssh_args, direction, source, destination):
        executable = Path(ssh_args[0]).with_name('sftp.exe' if os.name == 'nt' else 'sftp')
        # Keep the validated SSH options, using sftp's uppercase port option.
        args = list(ssh_args[1:-1])
        args[args.index('-p')] = '-P'
        user_index = args.index('-l')
        args[user_index:user_index + 2] = ['-o', 'User=' + args[user_index + 1]]
        command = ('put' if direction == 'upload' else 'get') + ' -r ' + sftp_quote(source) + ' ' + sftp_quote(destination)
        with self.lock:
            if self.cancelled:
                raise RuntimeError('传输已取消')
            self.process = subprocess.Popen([str(executable), '-b', '-', *args, ssh_args[-1]],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                encoding='utf-8', errors='replace', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        output, _ = self.process.communicate(command + '\n')
        if self.cancelled:
            raise RuntimeError('传输已取消；目标可能保留部分文件')
        if self.process.returncode:
            raise RuntimeError(output[-2000:] or 'SFTP 传输失败')
