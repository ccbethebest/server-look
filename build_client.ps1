param([string]$OutputDirectory = "dist")
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONPATH = Join-Path $PSScriptRoot '.build-deps'
$env:PYINSTALLER_CONFIG_DIR = Join-Path $PSScriptRoot '.pyinstaller-cache'
$version = python -c 'from server_look.app.settings import APP_VERSION; print(APP_VERSION)'
if ($LASTEXITCODE -ne 0) { throw 'Cannot read client version' }
python -m PyInstaller --noconfirm --distpath "$OutputDirectory" --onefile --windowed --collect-all tkinterdnd2 --icon assets/server.ico --add-data assets:assets --add-data 'server_look/remote/npu_top.py:server_look/remote' --add-data 'server_look/remote/server_resources.py:server_look/remote' --add-data 'server_look/remote/file_search.py:server_look/remote' --add-data 'docs:docs' --name "服务器看看-$version" npu_client.pyw
if ($LASTEXITCODE -ne 0) { throw 'Client build failed' }
