param(
    [string]$ExpectedVersion = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))

function Read-MatchedVersion([string]$Path, [string]$Pattern, [string]$Label) {
    $Contents = [System.IO.File]::ReadAllText((Join-Path $ProjectRoot $Path))
    $Match = [regex]::Match($Contents, $Pattern)
    if (-not $Match.Success) {
        throw "Could not read $Label version from $Path."
    }
    return $Match.Groups[1].Value
}

$Versions = [ordered]@{
    PythonProject = Read-MatchedVersion "pyproject.toml" '(?ms)^\[project\]\s*.*?^version\s*=\s*"([^"]+)"' "Python project"
    PythonPackage = Read-MatchedVersion "src\fanbox_archiver\__init__.py" '__version__\s*=\s*"([^"]+)"' "Python package"
    RustPackage = Read-MatchedVersion "src-tauri\Cargo.toml" '(?ms)^\[package\]\s*.*?^version\s*=\s*"([^"]+)"' "Rust package"
    Tauri = (Get-Content -LiteralPath (Join-Path $ProjectRoot "src-tauri\tauri.conf.json") -Raw | ConvertFrom-Json).version
}

$UniqueVersions = @($Versions.Values | Sort-Object -Unique)
if ($UniqueVersions.Count -ne 1) {
    $Details = ($Versions.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join ", "
    throw "Project versions do not match: $Details"
}

$Version = $UniqueVersions[0]
if ($ExpectedVersion) {
    if ($ExpectedVersion -notmatch '^v?\d+\.\d+\.\d+(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?$') {
        throw "Release version must use vMAJOR.MINOR.PATCH or a semantic prerelease such as vMAJOR.MINOR.PATCH-alpha."
    }
    $NormalizedExpected = $ExpectedVersion.TrimStart([char]'v')
    if ($Version -ne $NormalizedExpected) {
        throw "Release tag version $NormalizedExpected does not match project version $Version."
    }
}

Write-Host "Version check passed: $Version"

