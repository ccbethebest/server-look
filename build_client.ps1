$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONPATH = Join-Path $PSScriptRoot '.build-deps'
$env:PYINSTALLER_CONFIG_DIR = Join-Path $PSScriptRoot '.pyinstaller-cache'
$version = python -c 'from settings import APP_VERSION; print(APP_VERSION)'
if ($LASTEXITCODE -ne 0) { throw 'Cannot read client version' }
python -m PyInstaller --noconfirm --onefile --windowed --collect-all tkinterdnd2 --icon assets/server.ico --add-data assets:assets --add-data 'npu_top.py:.' --add-data 'server_resources.py:.' --add-data 'file_search.py:.' --add-data 'HELP.md:.' --name "服务器看看-$version" npu_client.pyw
if ($LASTEXITCODE -ne 0) { throw 'Client build failed' }
