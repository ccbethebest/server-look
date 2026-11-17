"""Bounded plain-text I/O shared by local editing and the SSH worker."""
import hashlib
import os
from pathlib import Path
import stat

MAX_TEXT_BYTES = 4 * 1024 * 1024
EXECUTABLE_SUFFIXES = {'.exe', '.com', '.dll', '.bat', '.cmd', '.ps1', '.msi', '.lnk', '.scr'}


def checked_file(stream, path):
    info = os.fstat(stream.fileno())
    if not stat.S_ISREG(info.st_mode):
        raise ValueError('只能编辑普通文本文件')
    if Path(path).suffix.lower() in EXECUTABLE_SUFFIXES or (os.name != 'nt' and info.st_mode & 0o111):
        raise ValueError('不支持编辑可执行文件')
    if info.st_size > MAX_TEXT_BYTES:
        raise ValueError('文本文件超过 4 MiB，请使用外部编辑器')
    return stream.read(MAX_TEXT_BYTES + 1)


def decode_text(raw):
    if len(raw) > MAX_TEXT_BYTES:
        raise ValueError('文本文件超过 4 MiB')
    encoding = 'utf-8-sig' if raw.startswith(b'\xef\xbb\xbf') else 'utf-8'
    if raw.startswith((b'\xff\xfe', b'\xfe\xff')):
        encoding = 'utf-16-le' if raw[:2] == b'\xff\xfe' else 'utf-16-be'
        raw_text = raw[2:].decode(encoding)
        encoding += '-bom'
    else:
        try:
            raw_text = raw.decode(encoding)
        except UnicodeDecodeError:
            encoding = 'gb18030'
            raw_text = raw.decode(encoding)
    if any(ord(c) < 32 and c not in '\t\n\r' for c in raw_text):
        raise ValueError('文件包含二进制内容，无法作为文本编辑')
    newline = '\r\n' if '\r\n' in raw_text else '\r' if '\r' in raw_text else '\n'
    return dict(text=raw_text.replace('\r\n', '\n').replace('\r', '\n'), encoding=encoding,
                newline=newline, digest=hashlib.sha256(raw).hexdigest())


def edit_file(path, text=None, encoding=None, newline=None, digest=None):
    # Do not follow links to devices/FIFOs, which could block a worker indefinitely.
    if not stat.S_ISREG(os.stat(path).st_mode):
        raise ValueError('只能编辑普通文本文件')
    with open(path, 'rb' if text is None else 'r+b') as stream:
        raw = checked_file(stream, path)
        if text is None:
            return decode_text(raw)
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError('文件已被外部修改，请另行保留编辑内容后重新打开')
        if encoding not in ('utf-8', 'utf-8-sig', 'gb18030', 'utf-16-le-bom', 'utf-16-be-bom') or newline not in ('\n', '\r\n', '\r'):
            raise ValueError('无效的文本编码或换行格式')
        codec = encoding[:-4] if encoding.endswith('-bom') else encoding
        output = text.replace('\n', newline).encode(codec)
        if encoding.endswith('-bom'):
            output = (b'\xff\xfe' if codec == 'utf-16-le' else b'\xfe\xff') + output
        if len(output) > MAX_TEXT_BYTES:
            raise ValueError('保存内容超过 4 MiB')
        stream.seek(0)
        stream.write(output)
        stream.truncate()
        stream.flush()
        os.fsync(stream.fileno())
        return dict(digest=hashlib.sha256(output).hexdigest())
