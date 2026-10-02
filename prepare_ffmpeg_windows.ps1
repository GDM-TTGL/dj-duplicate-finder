param([Parameter(Mandatory=$true)][string]$FfmpegArchive)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ffmpegDir = Join-Path $root 'ffmpeg'
$tempDir = Join-Path $root '.ffmpeg-download'
if (-not (Test-Path -LiteralPath $FfmpegArchive)) { throw "No existe el archivo: $FfmpegArchive" }
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
Expand-Archive -LiteralPath $FfmpegArchive -DestinationPath $tempDir -Force
$bin = Get-ChildItem -LiteralPath $tempDir -Directory -Recurse | Where-Object { (Test-Path (Join-Path $_.FullName 'bin\ffmpeg.exe')) -and (Test-Path (Join-Path $_.FullName 'bin\ffprobe.exe')) } | Select-Object -First 1
if (-not $bin) { throw 'No se encontraron ffmpeg.exe y ffprobe.exe en el paquete.' }
New-Item -ItemType Directory -Path $ffmpegDir -Force | Out-Null
Get-ChildItem -LiteralPath (Join-Path $bin.FullName 'bin') -File | Where-Object { $_.Name -match '\.dll$|^(ffmpeg|ffprobe)\.exe$' } | Copy-Item -Destination $ffmpegDir -Force
$license = Get-ChildItem -LiteralPath $bin.FullName -File | Where-Object { $_.Name -match 'LICENSE|COPYING' } | Select-Object -First 1
if ($license) { Copy-Item -LiteralPath $license.FullName -Destination $ffmpegDir -Force }
Remove-Item -LiteralPath $tempDir -Recurse -Force
Write-Host 'FFmpeg Windows LGPL preparado en ./ffmpeg.'
