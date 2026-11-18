"""Keep startup errors visible even when launched without a console."""
from server_look.paths import user_data_dir
from datetime import datetime
import os
from pathlib import Path
import sys
import tempfile
import traceback
import subprocess


def start_application():
    from server_look.app.desktop_app import main
    main()


def show_error(message):
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, '服务器看看：启动失败', 0x10)
    elif sys.platform == 'darwin':
        print(message, file=sys.stderr)
        try:
            subprocess.run(['osascript', '-e',
                            'on run argv\ndisplay alert "服务器看看：启动失败" message (item 1 of argv) as critical\nend run',
                            message], check=True, timeout=60)
        except (OSError, subprocess.SubprocessError):
            pass
    else:
        print(message, file=sys.stderr)


def run():
    try:
        start_application()
    except Exception:
        detail = traceback.format_exc()
        location = '无法写入启动日志。'
        for directory in (user_data_dir(),
                          Path(tempfile.gettempdir()) / 'ServerLook'):
            try:
                directory.mkdir(parents=True, exist_ok=True)
                log = directory / 'startup.log'
                with log.open('a', encoding='utf-8') as output:
                    output.write(f'\n{datetime.now().isoformat()} Python: {sys.executable}\n{detail}')
                location = f'日志：{log}'
                break
            except OSError:
                continue
        show_error(f'程序未能启动，请重新运行安装脚本修复依赖。\n{location}\n\n{detail[-1800:]}')
        return 1
    return 0
