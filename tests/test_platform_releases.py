"""Run the Windows installer with offline GitHub responses and a real ZIP."""
import json
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile


@unittest.skipUnless(os.name == 'nt', 'PowerShell installation is Windows-only')
class PlatformReleaseTests(unittest.TestCase):
    def test_windows_installer_ignores_mac_draft_and_prerelease(self):
        for tag in ('v2.22.0-windows', 'v2.21.1'):
            with self.subTest(tag=tag), tempfile.TemporaryDirectory() as folder:
                base = Path(folder)
                version = tag.removeprefix('v').removesuffix('-windows')
                archive = base / 'source.zip'
                with zipfile.ZipFile(archive, 'w') as output:
                    output.writestr(f'server-look-{version}/install.ps1',
                                    "param($InstallDirectory, [switch]$Launch)\n"
                                    "Set-Content -LiteralPath $InstallDirectory -Value 'installed'\n")
                releases = [
                    dict(tag_name='v9.0.0-macos', assets=[]),
                    dict(tag_name='v8.0.0-windows', draft=True, assets=[]),
                    dict(tag_name='v7.0.0-windows', prerelease=True, assets=[]),
                    dict(tag_name=tag, assets=[dict(name=f'server-look-{version}-source.zip', url='offline',
                                                  digest='sha256:' + hashlib.sha256(archive.read_bytes()).hexdigest())]),
                ]
                (base / 'releases.json').write_text(json.dumps(releases), encoding='utf-8')
                script = base / 'verify.ps1'
                script.write_text("""
param($Base, $Installer)
$ErrorActionPreference = 'Stop'
function Invoke-RestMethod {
    $items = @(Get-Content -LiteralPath (Join-Path $Base 'releases.json') -Raw | ConvertFrom-Json)
    return $items
}
function Invoke-WebRequest {
    param($OutFile, $Headers, [switch]$UseBasicParsing)
    Copy-Item -LiteralPath (Join-Path $Base 'source.zip') -Destination $OutFile
}
& $Installer -InstallDirectory (Join-Path $Base 'installed.txt') -NoLaunch
""", encoding='utf-8')
                installer = Path(__file__).resolve().parents[1] / 'quick-install.ps1'
                result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                                         '-File', str(script), str(base), str(installer)],
                                        capture_output=True, text=True, errors='replace', timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual((base / 'installed.txt').read_text().strip(), 'installed')


if __name__ == '__main__':
    unittest.main()
