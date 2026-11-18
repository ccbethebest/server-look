"""Explicit native Keychain backend; never fall back to plaintext storage."""
import uuid

PREFIX = 'keychain:'
SERVICE = 'server-look.ssh'


def backend():
    try:
        from keyring.backends.macOS import Keyring
        return Keyring()
    except ImportError as exc:
        raise OSError('无法加载 macOS 钥匙串，请重新运行 Mac 安装程序') from exc


def save(password):
    reference = PREFIX + str(uuid.uuid4())
    try:
        backend().set_password(SERVICE, reference, password)
    except Exception as exc:
        raise OSError('无法保存到 macOS 钥匙串，请检查钥匙串访问权限') from exc
    return reference


def read(reference):
    try:
        password = backend().get_password(SERVICE, reference)
        if password is None:
            raise ValueError('Missing Keychain item')
        return password
    except Exception as exc:
        raise OSError('无法读取 macOS 钥匙串密码，请解锁钥匙串或重新输入密码') from exc


def delete(reference):
    try:
        store = backend()
        if store.get_password(SERVICE, reference) is not None:
            store.delete_password(SERVICE, reference)
    except Exception as exc:
        raise OSError('无法删除 macOS 钥匙串密码，请检查钥匙串访问权限') from exc
