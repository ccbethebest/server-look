"""Install a private virtual environment and a Finder-launchable application."""
import argparse
from pathlib import Path
import plistlib
import shlex
import shutil
import subprocess
import sys
import tempfile
import venv


def make_application(target, version):
    app = target / '服务器看看.app'
    contents = app / 'Contents'
    executable = contents / 'MacOS' / 'server-look'
    resources = contents / 'Resources'
    executable.parent.mkdir(parents=True, exist_ok=True)
    resources.mkdir(parents=True, exist_ok=True)
    python = target / '.venv' / 'bin' / 'python'
    # Shell quotes preserve spaces, Chinese characters and shell metacharacters.
    executable.write_text('#!/bin/sh\nexec ' + shlex.quote(str(python)) + ' ' +
                          shlex.quote(str(target / 'npu_client.pyw')) + '\n', encoding='utf-8')
    executable.chmod(0o755)
    metadata = dict(CFBundleName='服务器看看', CFBundleDisplayName='服务器看看',
                    CFBundleIdentifier='com.ccbethebest.server-look', CFBundleExecutable='server-look',
                    CFBundlePackageType='APPL', CFBundleShortVersionString=version,
                    CFBundleVersion=version, NSHighResolutionCapable=True)
    with tempfile.TemporaryDirectory(prefix='server-look-icon-') as temporary:
        iconset = Path(temporary) / 'server.iconset'
        iconset.mkdir()
        for size in (16, 32, 128, 256, 512):
            for scale, suffix in ((1, ''), (2, '@2x')):
                subprocess.run(['sips', '-z', str(size * scale), str(size * scale),
                                str(target / 'assets' / 'server.png'), '--out',
                                str(iconset / f'icon_{size}x{size}{suffix}.png')],
                               check=True, stdout=subprocess.DEVNULL)
        subprocess.run(['iconutil', '-c', 'icns', str(iconset), '-o', str(resources / 'server.icns')], check=True)
    metadata['CFBundleIconFile'] = 'server.icns'
    with (contents / 'Info.plist').open('wb') as stream:
        plistlib.dump(metadata, stream)
    return app


def install(target):
    source = Path(__file__).resolve().parents[1]
    target = target.expanduser().resolve()
    if target == Path.home() or target == Path(target.anchor):
        raise ValueError('请选择专用的应用目录')
    if target != source and (target.is_relative_to(source) or source.is_relative_to(target)):
        raise ValueError('安装目录不能与源码目录互相包含')
    target.mkdir(parents=True, exist_ok=True)
    # Never write through an existing link into another application or environment.
    for name in ('server_look', 'assets', 'docs', 'tools', '.venv', '服务器看看.app',
                 'npu_client.pyw', 'requirements.txt', 'README.md', 'start-macos.command', 'install-macos.command'):
        destination = target / name
        if destination.is_symlink() or (name != '.venv' and destination.is_dir()
                                        and any(p.is_symlink() for p in destination.rglob('*'))):
            raise ValueError(f'安装路径含符号链接，请选择新的专用目录：{destination}')
    # A venv normally contains Python symlinks, so only reject the venv root itself.
    if target != source:
        for name in ('server_look', 'assets', 'docs', 'tools'):
            shutil.copytree(source / name, target / name, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        for name in ('npu_client.pyw', 'requirements.txt', 'README.md', 'start-macos.command', 'install-macos.command'):
            shutil.copy2(source / name, target / name)
    venv.EnvBuilder(with_pip=True).create(target / '.venv')
    python = target / '.venv' / 'bin' / 'python'
    subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(target / 'requirements.txt')], check=True)
    subprocess.run([str(python), '-c',
                    'import tkinter, paramiko, pyte; from keyring.backends.macOS import Keyring; '
                    'from tkinterdnd2 import TkinterDnD; r=TkinterDnD.Tk(); r.withdraw(); r.destroy()'], check=True)
    sys.path.insert(0, str(target))
    from server_look.app.settings import APP_VERSION
    app = make_application(target, APP_VERSION)
    for name in ('start-macos.command', 'install-macos.command'):
        (target / name).chmod(0o755)
    print(f'安装完成：{app}\n双击此应用启动；此应用依赖当前安装目录，请不要单独移动。')
    subprocess.run(['open', '-R', str(app)], check=True)


def main():
    if sys.platform != 'darwin':
        raise SystemExit('此安装程序只能在 macOS 上运行。')
    if sys.version_info < (3, 12):
        raise SystemExit('请先从 python.org 安装 Python 3.12 或更新版本（包含 Tk）。')
    import tkinter
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', nargs='?', type=Path, default=Path.home() / 'Applications' / 'ServerLook')
    install(parser.parse_args().directory)


if __name__ == '__main__':
    main()
