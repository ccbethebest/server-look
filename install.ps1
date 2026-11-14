param([switch]$Launch)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

# Keep dependencies inside the project instead of changing global Python.
python -c "import sys, tkinter; assert sys.version_info >= (3, 12), 'Python 3.12 or newer is required'"
if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12 with Tcl/Tk and add Python to PATH first.' }
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the virtual environment.' }
}
& $python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed; check the network and retry.' }
& $python -c 'import tkinter, paramiko, tkinterdnd2'
if ($LASTEXITCODE -ne 0) { throw 'Dependency verification failed.' }
Write-Host 'Ready. Double-click start.cmd to launch.'
if ($Launch) { Start-Process -FilePath (Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe') -ArgumentList 'npu_client.pyw' -WorkingDirectory $PSScriptRoot }
