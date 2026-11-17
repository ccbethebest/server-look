"""Bounded plain-text I/O shared by local editing and the SSH worker."""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess

MAX_TEXT_BYTES = 4 * 1024 * 1024


def editor_identity():
    return dict(boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                namespace=os.readlink('/proc/self/ns/mnt'), uid=str(os.geteuid()), gid=str(os.getegid()))


def verify_editor_identity(context):
    try:
        matches = editor_identity() == context
    except (OSError, AttributeError):
        matches = False
    if not matches:
        raise ValueError('编辑会话身份已改变或无法核对，请从当前终端重新打开文件')


def docker_editor_command(args, **options):
    result = subprocess.run(['docker', *args], text=True, encoding='utf-8',
                            errors='replace', capture_output=True, timeout=30, **options)
    if result.returncode:
        raise ValueError('容器文本编辑失败：' + (result.stderr or result.stdout).strip()[-1500:])
    return result.stdout


def edit_in_context(context, options, source):
    if (not isinstance(context, dict) or set(context) != {'boot', 'namespace', 'uid', 'gid'}
            or not all(isinstance(value, str) and value for value in context.values())
            or not context['uid'].isdecimal() or not context['gid'].isdecimal()):
        raise ValueError('无法确定终端文件系统身份，请在 Linux 终端重新打开文件')
    current = editor_identity()
    if context['boot'] != current['boot']:
        raise ValueError('终端已进入另一台服务器，请直接连接该服务器后编辑')
    if context['namespace'] == current['namespace']:
        verify_editor_identity(context)
        return dict(edit_file(**options), location='服务器')
    ids = docker_editor_command(['ps', '--quiet', '--no-trunc']).split()
    containers = json.loads(docker_editor_command(['inspect', *ids])) if ids else []
    matches = []
    for container in containers:
        pid = int(container['State']['Pid'])
        try:
            namespace = os.readlink('/proc/' + str(pid) + '/ns/mnt')
        except OSError:
            continue
        if namespace == context['namespace']:
            matches.append(container)
    if len(matches) != 1:
        raise ValueError('无法唯一定位终端所在的运行中 Docker 容器，请检查容器状态及 Docker 权限')
    container = matches[0]
    # Validate again inside the container to reject restart/namespace races.
    program = source + '\nimport json,sys\np=json.load(sys.stdin)\nverify_editor_identity(p["context"])\nprint(json.dumps(edit_file(**p["options"])))\n'
    launcher = 'if command -v python3 >/dev/null 2>&1; then exec python3 -c "$1"; elif command -v python >/dev/null 2>&1; then exec python -c "$1"; else echo "容器内未找到 Python，请安装 Python 3 后重试" >&2; exit 127; fi'
    output = docker_editor_command(['exec', '-i', '--user', context['uid'] + ':' + context['gid'],
                                    container['Id'], 'sh', '-c', launcher, 'server-look-editor', program],
                                   input=json.dumps(dict(context=context, options=options)))
    return dict(json.loads(output), location='Docker ' + container['Name'].lstrip('/') + ' · ' + container['Id'][:12])


def checked_file(stream, path):
    info = os.fstat(stream.fileno())
    if not stat.S_ISREG(info.st_mode):
        raise ValueError('只能编辑普通文本文件')
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
    if not os.path.lexists(path):
        if text is None:
            return dict(text='', encoding='utf-8', newline='\n', digest=None)
        if digest is not None:
            raise ValueError('文件已被外部删除，请另行保留编辑内容后重新打开')
        output = encode_text(text, encoding, newline)
        # Exclusive creation prevents overwriting a file created since opening.
        try:
            with open(path, 'xb') as stream:
                stream.write(output)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            raise ValueError('文件已被外部创建，请重新打开') from None
        return dict(digest=hashlib.sha256(output).hexdigest())
    if not stat.S_ISREG(os.stat(path).st_mode):
        raise ValueError('只能编辑普通文本文件')
    with open(path, 'rb' if text is None else 'r+b') as stream:
        raw = checked_file(stream, path)
        if text is None:
            return decode_text(raw)
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError('文件已被外部修改，请另行保留编辑内容后重新打开')
        output = encode_text(text, encoding, newline)
        stream.seek(0)
        stream.write(output)
        stream.truncate()
        stream.flush()
        os.fsync(stream.fileno())
        return dict(digest=hashlib.sha256(output).hexdigest())


def encode_text(text, encoding, newline):
    if encoding not in ('utf-8', 'utf-8-sig', 'gb18030', 'utf-16-le-bom', 'utf-16-be-bom') or newline not in ('\n', '\r\n', '\r'):
        raise ValueError('无效的文本编码或换行格式')
    codec = encoding[:-4] if encoding.endswith('-bom') else encoding
    output = text.replace('\n', newline).encode(codec)
    if encoding.endswith('-bom'):
        output = (b'\xff\xfe' if codec == 'utf-16-le' else b'\xfe\xff') + output
    if len(output) > MAX_TEXT_BYTES:
        raise ValueError('保存内容超过 4 MiB')
    return output
