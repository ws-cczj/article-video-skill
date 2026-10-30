<#
.SYNOPSIS
Download the Windows x64 FFmpeg essentials ZIP, verify SHA256 and print its paths.
.EXAMPLE
& ./scripts/download_ffmpeg.ps1
.EXAMPLE
& ./scripts/download_ffmpeg.ps1 -ShowPaths
#>
[CmdletBinding()]
param(
    [string]$Destination,
    [string]$DownloadDirectory,
    [uri]$Proxy,
    [switch]$ShowPaths
)

$ErrorActionPreference = 'Stop'
$skillRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$toolsRoot = Join-Path $skillRoot 'tools'

function Resolve-ToolDirectory([string]$Directory) {
    $candidate = if ([IO.Path]::IsPathRooted($Directory)) { $Directory } else { Join-Path $skillRoot $Directory }
    $fullPath = [IO.Path]::GetFullPath($candidate).TrimEnd([char[]]@('\','/'))
    if ($fullPath -ne $toolsRoot -and -not $fullPath.StartsWith($toolsRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Tool download and installation directories must be inside this skill folder''s tools directory.'
    }
    # Reject directory links which could redirect an otherwise local path outside the skill.
    $ancestor = $fullPath
    while ($ancestor -and $ancestor -ne $skillRoot) {
        if (Test-Path -LiteralPath $ancestor) {
            if ((Get-Item -LiteralPath $ancestor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Linked tool directories are not supported: $ancestor"
            }
        }
        $ancestor = [IO.Path]::GetDirectoryName($ancestor)
    }
    return $fullPath
}

if (-not $Destination) { $Destination = Join-Path $toolsRoot 'ffmpeg' }
$destinationPath = Resolve-ToolDirectory $Destination
if (-not $DownloadDirectory) { $DownloadDirectory = Join-Path $destinationPath 'downloads' }
$downloadPath = Resolve-ToolDirectory $DownloadDirectory
$downloadUrl = 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'
$archivePath = Join-Path $downloadPath 'ffmpeg-release-essentials.zip'

if ($ShowPaths) {
    [pscustomobject]@{
        DownloadUrl = $downloadUrl
        ChecksumUrl = "$downloadUrl.sha256"
        ArchivePath = $archivePath
        InstallDirectory = $destinationPath
        SkillDirectory = $skillRoot
        ToolsDirectory = $toolsRoot
    }
    return
}
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT -or -not [Environment]::Is64BitOperatingSystem) {
    throw 'This downloader requires 64-bit Windows. For other platforms use https://ffmpeg.org/download.html'
}

function Find-FFmpegBin {
    $candidates = @(Join-Path $destinationPath 'bin')
    if (Test-Path -LiteralPath $destinationPath -PathType Container) {
        $candidates += @(Get-ChildItem -LiteralPath $destinationPath -Directory -Filter 'ffmpeg-*' |
            Sort-Object LastWriteTime -Descending | ForEach-Object { Join-Path $_.FullName 'bin' })
    }
    foreach ($candidate in $candidates) {
        $candidate = Resolve-ToolDirectory $candidate
        if ((Test-Path -LiteralPath (Join-Path $candidate 'ffmpeg.exe') -PathType Leaf) -and
            (Test-Path -LiteralPath (Join-Path $candidate 'ffprobe.exe') -PathType Leaf)) { return $candidate }
    }
}

$binPath = Find-FFmpegBin
if (-not $binPath) {
    New-Item -ItemType Directory -Path $destinationPath, $downloadPath -Force | Out-Null
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $requestOptions = @{ UseBasicParsing = $true; TimeoutSec = 300 }
    if ($Proxy) { $requestOptions.Proxy = $Proxy }
    Write-Host "Downloading: $downloadUrl"
    Write-Host "Saving ZIP: $archivePath"
    $checksumResponse = Invoke-WebRequest -Uri "$downloadUrl.sha256" @requestOptions
    $checksumMatch = [regex]::Match([string]$checksumResponse.Content, '(?i)\b[a-f0-9]{64}\b')
    if (-not $checksumMatch.Success) { throw 'The download source did not return a SHA256 checksum.' }
    Invoke-WebRequest -Uri $downloadUrl -OutFile $archivePath @requestOptions
    if ((Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash -ne $checksumMatch.Value) {
        throw "SHA256 mismatch. ZIP was not extracted; run again to download a new copy: $archivePath"
    }
    # Retain the full distribution, including its license and documentation.
    Expand-Archive -LiteralPath $archivePath -DestinationPath $destinationPath
    $binPath = Find-FFmpegBin
    if (-not $binPath) { throw 'Downloaded package does not contain ffmpeg.exe and ffprobe.exe.' }
}

foreach ($toolName in @('ffmpeg', 'ffprobe')) {
    $toolPath = Join-Path $binPath "$toolName.exe"
    $versionLines = @(& $toolPath -version 2>&1)
    if ($LASTEXITCODE -ne 0) { throw "Cannot run $toolPath" }
    Write-Host $versionLines[0]
}
[pscustomobject]@{
    DownloadUrl = $downloadUrl
    ArchivePath = $archivePath
    InstallDirectory = $destinationPath
    SkillDirectory = $skillRoot
    ToolsDirectory = $toolsRoot
    BinPath = $binPath
    FFmpeg = (Join-Path $binPath 'ffmpeg.exe')
    FFprobe = (Join-Path $binPath 'ffprobe.exe')
}
