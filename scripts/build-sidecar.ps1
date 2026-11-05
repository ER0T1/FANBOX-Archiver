$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
# FANBOX_SIDECAR_PYTHON picks the interpreter that freezes the sidecar (an official CPython
# virtual environment with the desktop dependencies); otherwise .venv, then python on PATH.
$VirtualEnvironmentPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Python = if ($env:FANBOX_SIDECAR_PYTHON) {
    $env:FANBOX_SIDECAR_PYTHON
} elseif (Test-Path -LiteralPath $VirtualEnvironmentPython -PathType Leaf) {
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

# PyInstaller resolves DLL dependencies through PATH; tools such as the Windows Performance
# Toolkit or ImageMagick ship their own C runtime copies, which must never be bundled. Freeze
# with only the interpreter's folders and the Windows system folders on PATH.
$BasePrefix = (& $Python -c "import sys; print(sys.base_prefix)").Trim()
$PythonScripts = Split-Path -Parent $Python
$OriginalPath = $env:PATH
$env:PATH = @($PythonScripts, $BasePrefix, (Join-Path $BasePrefix "DLLs"),
    (Join-Path $env:SystemRoot "System32"), $env:SystemRoot) -join ";"
try {
    New-Item -ItemType Directory -Force -Path $OutputDirectory, $WorkDirectory, $SpecDirectory, $BinaryDirectory | Out-Null
    & $Python -m PyInstaller `
        --noconfirm `
        --clean `
        --onefile `
        --name "fanbox-archiver-sidecar" `
        --paths (Join-Path $ProjectRoot "src") `
        --collect-all "fanbox_archiver" `
        --collect-submodules "uvicorn" `
        --collect-data "tzdata" `
        --collect-submodules "tzlocal" `
        --distpath $OutputDirectory `
        --workpath $WorkDirectory `
        --specpath $SpecDirectory `
        (Join-Path $ProjectRoot "scripts\sidecar_entry.py")
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller sidecar build failed."
    }
} finally {
    $env:PATH = $OriginalPath
}

$Built = Join-Path $OutputDirectory "fanbox-archiver-sidecar.exe"
if (-not (Test-Path -LiteralPath $Built)) {
    throw "PyInstaller output was not found: $Built"
}

# The Universal C Runtime is part of Windows; a bundled copy loads a second runtime.
$Bundled = & $Python -c "import sys; from PyInstaller.archive.readers import CArchiveReader as R; print('\n'.join(n for n in R(sys.argv[1]).toc if n.lower() == 'ucrtbase.dll' or n.lower().startswith('api-ms-win-crt-')))" $Built
if ($LASTEXITCODE -ne 0) {
    throw "Could not inspect the sidecar bundle."
}
if ($Bundled) {
    throw "The sidecar bundles C runtime DLLs that must come from Windows: $($Bundled -join ', ')"
}

# Every FANBOX request needs HTTPS; refuse to ship a sidecar whose TLS stack cannot start.
$Check = & $Built --self-check
if ($LASTEXITCODE -ne 0) {
    throw ("Sidecar self-check failed: $Check. Freeze the sidecar with an official CPython " +
        "(python.org or Microsoft Store) virtual environment, for example by setting FANBOX_SIDECAR_PYTHON.")
}
Write-Host "Sidecar self-check passed: $Check"

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
