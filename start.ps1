$ErrorActionPreference = 'Stop'
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$log = Join-Path $PSScriptRoot 'start-check.log'
if (-not (Test-Path -LiteralPath $python)) { throw 'Please run install.cmd or install-d.cmd first.' }
Push-Location -LiteralPath $PSScriptRoot
try {
    & $python -c 'import sys, tkinter, paramiko, tkinterdnd2, pyte; assert sys.version_info >= (3,12)' *> $log
    if ($LASTEXITCODE -ne 0) {
        Get-Content -LiteralPath $log
        throw "Startup check failed. Run install.cmd to repair dependencies. Log: $log"
    }
    Start-Process -FilePath (Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe') -ArgumentList ('"' + (Join-Path $PSScriptRoot 'npu_client.pyw') + '"') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
} finally { Pop-Location }
