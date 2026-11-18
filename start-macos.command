#!/bin/bash
set -eu
cd -- "$(dirname -- "$0")"
if [ ! -x .venv/bin/python ]; then
  echo '请先运行 install-macos.command 安装。按回车关闭。'
  read -r reply
  exit 1
fi
exec .venv/bin/python npu_client.pyw
