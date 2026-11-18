param([string]$InstallDirectory = 'D:\ServerLook', [switch]$NoLaunch)
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ProgressPreference = 'SilentlyContinue'
$headers = @{ Accept = 'application/vnd.github+json' }
if ($env:GH_TOKEN) { $headers.Authorization = 'Bearer ' + $env:GH_TOKEN }
try {
    $releases = Invoke-RestMethod 'https://api.github.com/repos/ccbethebest/server-look/releases?per_page=100' -Headers $headers
    $release = $releases | Where-Object { -not $_.draft -and -not $_.prerelease -and $_.tag_name -match '^v[0-9.]+(-windows)?$' } | Select-Object -First 1
    if (-not $release) { throw 'No Windows release found.' }
}
catch { throw ('Cannot read the latest Windows release. For a private repository, set GH_TOKEN with read access, or download the source ZIP in your browser and run install-d.cmd. Details: ' + $_.Exception.Message) }
$asset = @($release.assets | Where-Object { $_.name -match '^server-look-[0-9.]+-source\.zip$' })
if ($asset.Count -ne 1) { throw 'A unique source package was not found in the latest release.' }
$folder = Join-Path ([IO.Path]::GetTempPath()) ('server-look-install-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $folder | Out-Null
$archive = Join-Path $folder 'source.zip'
$downloadHeaders = $headers.Clone()
$downloadHeaders.Accept = 'application/octet-stream'
Invoke-WebRequest $asset[0].url -Headers $downloadHeaders -OutFile $archive -UseBasicParsing
if ($asset[0].digest -notmatch '^sha256:([0-9a-fA-F]{64})$') { throw 'The release has no SHA256 digest. Please download and inspect the source manually.' }
$expectedHash = $Matches[1]
$sha256 = [Security.Cryptography.SHA256]::Create()
$stream = [IO.File]::OpenRead($archive)
try { $actualHash = [BitConverter]::ToString($sha256.ComputeHash($stream)).Replace('-', '') }
finally { $stream.Dispose(); $sha256.Dispose() }
if ($actualHash -ne $expectedHash) { throw 'Source package checksum mismatch.' }
$expanded = Join-Path $folder 'source'
Add-Type -AssemblyName System.IO.Compression.FileSystem
[IO.Compression.ZipFile]::ExtractToDirectory($archive, $expanded)
$version = $asset[0].name -replace '^server-look-', '' -replace '-source\.zip$', ''
$installer = Join-Path $expanded ('server-look-' + $version + '\install.ps1')
if (-not (Test-Path -LiteralPath $installer)) { throw 'Installation script is missing from the source package.' }
& $installer -InstallDirectory $InstallDirectory -Launch:(-not $NoLaunch)
