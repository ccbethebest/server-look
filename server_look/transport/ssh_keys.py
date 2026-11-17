"""Local public key lifecycle. Private keys never leave the local SSH directory."""
from pathlib import Path
import base64
import shlex
import shutil
import subprocess
import threading

_KEY_LOCK = threading.Lock()


def detect_keys(directory=None):
    root = Path(directory) if directory else Path.home() / '.ssh'
    return sorted(path for path in root.glob('*.pub')
                  if path.with_suffix('').is_file())


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


def install_script(public_key):
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
if awk -v t="$(printf '%s' "$key" | cut -d ' ' -f1)" -v k="$(printf '%s' "$key" | cut -d ' ' -f2)" '$1==t && $2==k {{found=1}} END {{exit !found}}' authorized_keys; then
    printf 'Public key already configured\\n'
else
    printf '\\n%s\\n' "$key" >&9
    printf 'Public key configured\\n'
fi
'''


def configure_key(connection, public_key):
    script = install_script(public_key)
    if connection.session:
        return connection.session.execute('sh -s', script)
    result = subprocess.run(connection.args + ['sh -s'], input=script, capture_output=True,
                            encoding='utf-8', errors='replace', timeout=40,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout
