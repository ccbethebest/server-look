"""SFTP batch transport. Paths are data, never shell commands."""
import os
from pathlib import Path
import subprocess
import threading
import shutil


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
    os.startfile(str(folder))


class Transfer:
    def __init__(self):
        self.lock = threading.Lock()
        self.process = None
        self.cancelled = False
        self.sftp = None

    def check(self):
        if self.cancelled:
            raise RuntimeError('传输已取消；目标可能保留部分文件')

    def run_many_connection(self, connection, direction, sources, destination):
        if direction == 'download':
            import posixpath
            names = [local_name(posixpath.basename(source.rstrip('/'))) for source in sources]
            if len({name.casefold() for name in names}) != len(names):
                raise ValueError('选中项含 Windows 下重名的文件')
        for source in sources:
            self.check()
            self.run_connection(connection, direction, source, destination)

    def copy_local(self, sources, destination):
        destination = Path(destination)

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
                shutil.copystat(src, dst)
            else:
                raise ValueError('仅支持普通文件和文件夹')

        for source in sources:
            source = Path(source)
            copy(source, destination / local_name(source.name))

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

            def check(*args):
                if self.cancelled:
                    raise RuntimeError('传输已取消；目标可能保留部分文件')

            def copy(src, dst):
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
