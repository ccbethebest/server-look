param(
    [string]$InstallDirectory = $PSScriptRoot,
    [string]$PythonExecutable,
    [string]$ShortcutDirectory = [Environment]::GetFolderPath('Desktop'),
    [switch]$Launch
)
$ErrorActionPreference = 'Stop'
$target = [IO.Path]::GetFullPath($InstallDirectory).TrimEnd('\')
$source = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
if ($target -eq [IO.Path]::GetPathRoot($target).TrimEnd('\')) { throw 'Choose an application folder, not a drive root.' }
if ($target.StartsWith($source + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'The installation folder must not be inside the source folder.' }
New-Item -ItemType Directory -Path $target -Force | Out-Null
Start-Transcript -Path (Join-Path $target 'install.log') -Append | Out-Null
try {
    if ($target -ne $source) {
        foreach ($name in @('server_look','assets','docs','tools','npu_client.pyw','requirements.txt','install.ps1','install.cmd','install-d.cmd','start.cmd','start.ps1','quick-install.ps1','README.md','build_client.ps1')) {
            Copy-Item -LiteralPath (Join-Path $source $name) -Destination $target -Recurse -Force
        }
    }
    function Find-Python {
        $candidates = @()
        if ($PythonExecutable) { $candidates += ,@($PythonExecutable) }
        else {
            $candidates += ,@('py','-3.12')
            $candidates += ,@('python')
            $candidates += ,@('py','-3')
            $candidates += ,@((Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'))
        }
        foreach ($candidate in $candidates) {
            try {
                $program = $candidate[0]
                $arguments = @($candidate | Select-Object -Skip 1)
                $result = & $program @arguments -c 'import sys, tkinter, venv; assert sys.version_info >= (3,12); print(sys.executable)' 2>$null
                if ($LASTEXITCODE -eq 0) { return ($result | Select-Object -Last 1) }
            } catch { continue }
        }
    }
    $basePython = Find-Python
    if (-not $basePython -and -not $PythonExecutable) {
        if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
            throw 'Python 3.12+ with Tcl/Tk is required. Install from https://www.python.org/downloads/windows/ then retry.'
        }
        & winget install --id Python.Python.3.12 --exact --source winget --scope user --silent --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) { throw 'Python installation failed. See install.log and retry.' }
        $basePython = Find-Python
    }
    if (-not $basePython) { throw 'No usable Python 3.12+ with Tcl/Tk was found.' }
    $venv = Join-Path $target '.venv'
    if ((Test-Path -LiteralPath $venv) -and ((Get-Item -LiteralPath $venv -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'The .venv folder must not be a symbolic link. Choose a new installation folder.'
    }
    $python = Join-Path $venv 'Scripts\python.exe'
    $healthy = $false
    if (Test-Path -LiteralPath $python) {
        try {
            & $python -c 'import sys, tkinter; assert sys.version_info >= (3,12)' 2>$null
            $healthy = $LASTEXITCODE -eq 0
        } catch { $healthy = $false }
    }
    if (-not $healthy) {
        # The absolute .venv path was checked above and is confined to this application folder.
        & $basePython -m venv --clear $venv
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the virtual environment.' }
    }
    & $python -m pip install -r (Join-Path $target 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check the network and retry.' }
    Push-Location -LiteralPath $target
    try {
        & $python -c 'import tkinter, paramiko, pyte; from tkinterdnd2 import TkinterDnD; import server_look.app.desktop_app; r=TkinterDnD.Tk(); r.withdraw(); r.update(); r.destroy()'
        if ($LASTEXITCODE -ne 0) { throw 'GUI/dependency verification failed. See install.log.' }
    } finally { Pop-Location }
    New-Item -ItemType Directory -Path $ShortcutDirectory -Force | Out-Null
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut((Join-Path $ShortcutDirectory 'Server Look.lnk'))
    $shortcut.TargetPath = Join-Path $venv 'Scripts\pythonw.exe'
    $shortcut.Arguments = '"' + (Join-Path $target 'npu_client.pyw') + '"'
    $shortcut.WorkingDirectory = $target
    $shortcut.IconLocation = (Join-Path $target 'assets\server.ico') + ',0'
    $shortcut.Description = 'Server Look'
    $shortcut.Save()
    Write-Host "Ready: $target. Desktop shortcut: Server Look."
    if ($Launch) {
        Start-Process -FilePath $shortcut.TargetPath -ArgumentList $shortcut.Arguments -WorkingDirectory $target -WindowStyle Hidden
    }
} finally { Stop-Transcript | Out-Null }
