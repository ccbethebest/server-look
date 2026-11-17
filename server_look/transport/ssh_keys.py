"""Local public key lifecycle. Private keys never leave the local SSH directory."""
from pathlib import Path
import base64
import shlex
import shutil
import subprocess
import threading

_KEY_LOCK = threading.Lock()

_KEY_LOOKUP = '''import shlex, sys
found = False
with open('authorized_keys', encoding='utf-8', errors='replace') as stream:
    for line in stream:
        try:
            fields = shlex.split(line, comments=True)
        except ValueError:
            continue
        # OpenSSH permits one options field before the key type and blob.
        for offset in (0, 1):
            if fields[offset:offset + 2] == sys.argv[1:3]:
                found = True
sys.exit(0 if found else 1)
'''


def detect_keys(directory=None):
    root = Path(directory) if directory else Path.home() / '.ssh'
    return sorted(path for path in root.glob('*.pub')
                  if path.is_file() and path.with_suffix('').is_file())


def ensure_key(directory=None):
    root = Path(directory) if directory else Path.home() / '.ssh'
    with _KEY_LOCK:
        pairs = detect_keys(root)
        if pairs:
            return pairs[0]
        # Do not replace even an incomplete existing private key.
        root.mkdir(parents=True, exist_ok=True)
        target = root / 'id_ed25519'
        if target.exists() or target.with_suffix('.pub').exists():
            raise ValueError('id_ed25519 已存在但密钥对不完整，请先检查，程序不会覆盖')
        generator = shutil.which('ssh-keygen')
        if not generator:
            raise RuntimeError('未安装 ssh-keygen，请安装 Windows OpenSSH 客户端')
        result = subprocess.run([generator, '-t', 'ed25519', '-N', '', '-C', 'ServerLook', '-f', str(target)],
                                capture_output=True, text=True, timeout=30,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or '密钥生成失败')
        return target.with_suffix('.pub')


def install_script(public_key, check_only=False):
    parts = public_key.strip().split()
    if '\n' in public_key.strip() or '\r' in public_key.strip() or len(parts) < 2:
        raise ValueError('公钥格式无效')
    if parts[0] not in ('ssh-ed25519', 'ssh-rsa', 'ecdsa-sha2-nistp256', 'ecdsa-sha2-nistp384', 'ecdsa-sha2-nistp521'):
        raise ValueError('仅允许 OpenSSH 公钥')
    try:
        base64.b64decode(parts[1], validate=True)
    except ValueError:
        raise ValueError('公钥编码无效') from None
    key = shlex.quote(' '.join(parts))
    # Match type/blob even when authorized_keys includes options before the key.
    lookup = f'python3 -c {shlex.quote(_KEY_LOOKUP)} {shlex.quote(parts[0])} {shlex.quote(parts[1])}'
    if check_only:
        # Do not create directories/files or change permissions during detection.
        return f'''set -eu
[ ! -L "$HOME/.ssh" ] || {{ echo '.ssh is a symlink' >&2; exit 1; }}
if [ ! -d "$HOME/.ssh" ]; then printf 'MISSING\\n'; exit 0; fi
cd "$HOME/.ssh"
[ ! -L authorized_keys ] || {{ echo 'authorized_keys is a symlink' >&2; exit 1; }}
if [ ! -e authorized_keys ]; then printf 'MISSING\\n'; exit 0; fi
[ -f authorized_keys ] && [ -r authorized_keys ] || {{ echo 'Cannot read authorized_keys' >&2; exit 1; }}
status=0
{lookup} || status=$?
case "$status" in 0) printf 'PAIRED\\n';; 1) printf 'MISSING\\n';; *) exit "$status";; esac
'''
    # Restrict changes to the authenticated user's account, preserve existing entries,
    # and serialize concurrent clicks/processes without rewriting the file.
    return f'''set -eu
umask 077
[ ! -L "$HOME/.ssh" ] || {{ echo '.ssh is a symlink' >&2; exit 1; }}
mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"
cd "$HOME/.ssh"
[ ! -L authorized_keys ] || {{ echo 'authorized_keys is a symlink' >&2; exit 1; }}
command -v flock >/dev/null || {{ echo 'flock is required' >&2; exit 1; }}
exec 9>>authorized_keys
flock -x 9
chmod 600 authorized_keys
key={key}
status=0
{lookup} || status=$?
case "$status" in
0) printf 'Public key already configured\\n';;
1) printf '\\n%s\\n' "$key" >&9; printf 'Public key configured\\n';;
*) exit "$status";;
esac
'''


def configure_key(connection, public_key):
    return _execute(connection, install_script(public_key))


def check_key(connection, public_key):
    result = _execute(connection, install_script(public_key, check_only=True)).strip()
    if result not in ('PAIRED', 'MISSING'):
        raise RuntimeError('无法确认服务器公钥配置状态：' + result)
    return result == 'PAIRED'


def _execute(connection, script):
    if connection.session:
        return connection.session.execute('sh -s', script)
    result = subprocess.run(connection.args + ['sh -s'], input=script, capture_output=True,
                            encoding='utf-8', errors='replace', timeout=40,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout
