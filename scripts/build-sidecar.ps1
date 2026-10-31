$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VirtualEnvironmentPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Python = if (Test-Path -LiteralPath $VirtualEnvironmentPython -PathType Leaf) {
    $VirtualEnvironmentPython
} else {
    $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $PythonCommand) {
        throw "Python was not found. Create .venv or add Python to PATH."
    }
    $PythonCommand.Source
}
$OutputDirectory = Join-Path $ProjectRoot "build\sidecar-dist"
$WorkDirectory = Join-Path $ProjectRoot "build\sidecar-work"
$SpecDirectory = Join-Path $ProjectRoot "build\sidecar-spec"
$BinaryDirectory = Join-Path $ProjectRoot "src-tauri\binaries"
$Target = Join-Path $BinaryDirectory "fanbox-archiver-sidecar-x86_64-pc-windows-msvc.exe"

& $Python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is not installed for $Python. Install the desktop dependencies first."
}

New-Item -ItemType Directory -Force -Path $OutputDirectory, $WorkDirectory, $SpecDirectory, $BinaryDirectory | Out-Null
& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --name "fanbox-archiver-sidecar" `
    --paths (Join-Path $ProjectRoot "src") `
    --collect-all "fanbox_archiver" `
    --collect-submodules "uvicorn" `
    --distpath $OutputDirectory `
    --workpath $WorkDirectory `
    --specpath $SpecDirectory `
    (Join-Path $ProjectRoot "scripts\sidecar_entry.py")
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller sidecar build failed."
}

$Built = Join-Path $OutputDirectory "fanbox-archiver-sidecar.exe"
if (-not (Test-Path -LiteralPath $Built)) {
    throw "PyInstaller output was not found: $Built"
}
$Copied = $false
foreach ($Attempt in 1..10) {
    try {
        Copy-Item -LiteralPath $Built -Destination $Target -Force
        $Copied = $true
        break
    } catch [System.IO.IOException] {
        if ($Attempt -eq 10) { throw }
        Start-Sleep -Milliseconds 500
    }
}
if (-not $Copied) {
    throw "Could not update the sidecar: $Target"
}
Write-Host "Sidecar ready: $Target"
