"""Per-user history; reusable passwords use Windows DPAPI or macOS Keychain."""
import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import tempfile
import sys
from server_look.paths import user_data_dir
from server_look.transport import mac_keychain


class _Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def _crypt(data, decrypt=False):
    if os.name != 'nt':
        raise OSError('密码保存仅支持 Windows DPAPI')
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source = _Blob(len(data), buffer)
    result = _Blob()
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
    function.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        raise OSError('Windows 无法加密或解密此密码，请重新输入')
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        kernel.LocalFree(result.data)


def protect(password):
    if sys.platform == 'darwin':
        return mac_keychain.save(password)
    return base64.b64encode(_crypt(password.encode('utf-8'))).decode('ascii')


def unprotect(token):
    if token.startswith(mac_keychain.PREFIX):
        if sys.platform != 'darwin':
            raise OSError('此密码保存在另一台 Mac 的钥匙串中，请重新输入')
        return mac_keychain.read(token)
    return _crypt(base64.b64decode(token, validate=True), decrypt=True).decode('utf-8')


class ConnectionHistory:
    def __init__(self, path=None):
        self.path = Path(path) if path else user_data_dir() / 'connections.json'

    @staticmethod
    def identity(record):
        return record['host'].lower(), record['user'], str(record['port'])

    def load(self):
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            return []
        if not isinstance(data, list) or any(not isinstance(r, dict) or
                not all(isinstance(r.get(k), str) for k in ('host', 'user', 'port', 'auth_mode'))
                or r['auth_mode'] not in ('key', 'password')
                or not isinstance(r.get('password', ''), str) for r in data):
            raise ValueError('连接历史格式无效，请备份并移走 connections.json 后重试')
        return data

    def _write(self, records):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(records, stream, ensure_ascii=False, indent=2)
            os.replace(temporary, self.path)
        finally:
            if temporary and temporary.exists(): temporary.unlink()

    def save(self, record, password='', remember=False):
        records = self.load()
        entry = {k: str(record[k]) for k in ('host', 'user', 'port', 'auth_mode')}
        if remember and entry['auth_mode'] == 'password' and password:
            entry['password'] = protect(password)
        previous = [r for r in records if self.identity(r) == self.identity(entry)]
        try:
            self._write([entry] + [r for r in records if self.identity(r) != self.identity(entry)])
        except Exception:
            self._forget_secrets([entry])
            raise
        self._forget_secrets(previous)

    @staticmethod
    def _forget_secrets(records):
        for record in records:
            token = record.get('password', '')
            if sys.platform == 'darwin' and token.startswith(mac_keychain.PREFIX):
                mac_keychain.delete(token)

    def password(self, record):
        return unprotect(record['password']) if record.get('password') else ''

    def delete(self, record):
        records = self.load()
        self._write([r for r in records if self.identity(r) != self.identity(record)])
        self._forget_secrets([r for r in records if self.identity(r) == self.identity(record)])
