#!/bin/bash
set -eu
cd -- "$(dirname -- "$0")"
trap 'status=$?; if [ "$status" -ne 0 ]; then echo "安装失败，请保留上方错误信息。按回车关闭。"; read -r reply; fi' EXIT
if [ "$(uname -s)" != Darwin ]; then echo '此安装程序仅供 macOS 使用。'; exit 1; fi
PYTHON="${SERVERLOOK_PYTHON:-}"
if [ -z "$PYTHON" ]; then
  for candidate in /Library/Frameworks/Python.framework/Versions/Current/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
    if [ -x "$candidate" ]; then PYTHON="$candidate"; break; fi
  done
fi
if [ -z "$PYTHON" ]; then
  echo '请先从 https://www.python.org/downloads/macos/ 安装 Python 3.12 或更新版本（含 Tk）。'
  exit 1
fi
"$PYTHON" tools/install_macos.py "$@"
