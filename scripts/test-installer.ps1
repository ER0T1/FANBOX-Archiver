param(
    [string]$InstallerPath = "",
    [string]$PreviousInstallerPath = "",
    [switch]$KeepArtifacts
)

$ErrorActionPreference = "Stop"

$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$TestRoot = [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot "build\installer-smoke"))
$AllowedRoot = [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot "build"))
if (-not $TestRoot.StartsWith($AllowedRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to use an installer test directory outside the project build folder."
}

if (-not $InstallerPath) {
    $Installer = Get-ChildItem -LiteralPath (Join-Path $ProjectRoot "src-tauri\target\release\bundle\nsis") `
        -Filter "*-setup.exe" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1
    if (-not $Installer) {
        throw "No NSIS installer was found. Build the desktop package first."
    }
    $InstallerPath = $Installer.FullName
}
$InstallerPath = [System.IO.Path]::GetFullPath($InstallerPath)
if (-not (Test-Path -LiteralPath $InstallerPath -PathType Leaf)) {
    throw "Installer not found: $InstallerPath"
}
if ($PreviousInstallerPath) {
    $PreviousInstallerPath = [System.IO.Path]::GetFullPath($PreviousInstallerPath)
    if (-not (Test-Path -LiteralPath $PreviousInstallerPath -PathType Leaf)) {
        throw "Previous installer not found: $PreviousInstallerPath"
    }
}

$UninstallRegistryRoots = @(
    "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall",
    "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall",
    "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
)

function Get-FanboxInstallEntries {
    foreach ($Root in $UninstallRegistryRoots) {
        if (-not (Test-Path -LiteralPath $Root)) { continue }
        Get-ChildItem -LiteralPath $Root -ErrorAction SilentlyContinue | ForEach-Object {
            $Entry = Get-ItemProperty -LiteralPath $_.PSPath -ErrorAction SilentlyContinue
            if ($Entry.DisplayName -eq "FANBOX Archiver") { $Entry }
        }
    }
}

$Existing = @(Get-FanboxInstallEntries)
if ($Existing.Count -gt 0) {
    $Locations = ($Existing | ForEach-Object { $_.InstallLocation }) -join ", "
    throw "FANBOX Archiver is already installed for this Windows environment ($Locations). Refusing to replace a real installation during the smoke test."
}

if (Test-Path -LiteralPath $TestRoot) {
    Remove-Item -LiteralPath $TestRoot -Recurse -Force
}
$InstallDirectory = Join-Path $TestRoot "installed app"
$ArchiveDirectory = Join-Path $TestRoot "user archive"
$ConfigPath = Join-Path $ArchiveDirectory "config.yaml"
$SentinelPath = Join-Path $ArchiveDirectory "keep-me.txt"
New-Item -ItemType Directory -Path $InstallDirectory, $ArchiveDirectory -Force | Out-Null
Set-Content -LiteralPath $ConfigPath -Encoding UTF8 -Value @(
    "storage:",
    "  output_dir: `"$ArchiveDirectory`"",
    "  database: `"$(Join-Path $ArchiveDirectory 'backup.db')`""
)
Set-Content -LiteralPath $SentinelPath -Encoding UTF8 -Value "installer-smoke-data"

function Invoke-SilentInstall([string]$Path) {
    $Arguments = "/S /D=$InstallDirectory"
    $Process = Start-Process -FilePath $Path -ArgumentList $Arguments -Wait -PassThru -WindowStyle Hidden
    if ($Process.ExitCode -ne 0) {
        throw "Installer exited with code $($Process.ExitCode): $Path"
    }
}

function Assert-InstalledPayload([string]$ExpectedVersion) {
    $Application = Join-Path $InstallDirectory "fanbox-archiver-desktop.exe"
    $Sidecar = Join-Path $InstallDirectory "fanbox-archiver-sidecar.exe"
    $Uninstaller = Join-Path $InstallDirectory "uninstall.exe"
    foreach ($Path in @($Application, $Sidecar, $Uninstaller)) {
        if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
            throw "Installed payload is missing: $Path"
        }
    }
    $InstalledVersion = (Get-Item -LiteralPath $Application).VersionInfo.ProductVersion
    if ($InstalledVersion -ne $ExpectedVersion) {
        throw "Installed application version is $InstalledVersion; expected $ExpectedVersion."
    }
}

$Installed = $false
$Succeeded = $false
try {
    $FirstInstaller = if ($PreviousInstallerPath) { $PreviousInstallerPath } else { $InstallerPath }
    $FirstVersion = (Get-Item -LiteralPath $FirstInstaller).VersionInfo.ProductVersion
    $CurrentVersion = (Get-Item -LiteralPath $InstallerPath).VersionInfo.ProductVersion
    Invoke-SilentInstall $FirstInstaller
    $Installed = $true
    Assert-InstalledPayload $FirstVersion

    Invoke-SilentInstall $InstallerPath
    Assert-InstalledPayload $CurrentVersion
    if ((Get-Content -LiteralPath $SentinelPath -Raw).Trim() -ne "installer-smoke-data") {
        throw "Archive sentinel changed during the overwrite upgrade."
    }

    $Uninstaller = Join-Path $InstallDirectory "uninstall.exe"
    $Process = Start-Process -FilePath $Uninstaller -ArgumentList "/S" -Wait -PassThru -WindowStyle Hidden
    if ($Process.ExitCode -ne 0) {
        throw "Uninstaller exited with code $($Process.ExitCode)."
    }
    $Installed = $false

    if (Test-Path -LiteralPath (Join-Path $InstallDirectory "fanbox-archiver-desktop.exe")) {
        throw "Application executable remains after uninstall."
    }
    if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $SentinelPath -PathType Leaf)) {
        throw "User archive data was removed by uninstall."
    }
    if (@(Get-FanboxInstallEntries).Count -gt 0) {
        throw "Uninstall registry entry remains after uninstall."
    }

    $Succeeded = $true
    Write-Host "Installer lifecycle smoke test passed."
    Write-Host "Install $FirstVersion -> $CurrentVersion upgrade, uninstall, and archive retention were verified."
}
finally {
    if ($Installed) {
        $Uninstaller = Join-Path $InstallDirectory "uninstall.exe"
        if (Test-Path -LiteralPath $Uninstaller -PathType Leaf) {
            Start-Process -FilePath $Uninstaller -ArgumentList "/S" -Wait -WindowStyle Hidden
        }
    }
    if ($Succeeded -and -not $KeepArtifacts -and (Test-Path -LiteralPath $TestRoot)) {
        Remove-Item -LiteralPath $TestRoot -Recurse -Force
    }
}
