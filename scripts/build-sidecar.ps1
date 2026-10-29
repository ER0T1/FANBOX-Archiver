$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$OutputDirectory = Join-Path $ProjectRoot "build\sidecar-dist"
$WorkDirectory = Join-Path $ProjectRoot "build\sidecar-work"
$SpecDirectory = Join-Path $ProjectRoot "build\sidecar-spec"
$BinaryDirectory = Join-Path $ProjectRoot "src-tauri\binaries"
$Target = Join-Path $BinaryDirectory "fanbox-archiver-sidecar-x86_64-pc-windows-msvc.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "找不到虛擬環境 Python：$Python"
}

& $Python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "尚未安裝桌面建置依賴，請先執行 .venv\Scripts\python.exe -m pip install -e '.[desktop]'"
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
    throw "PyInstaller sidecar 建置失敗"
}

$Built = Join-Path $OutputDirectory "fanbox-archiver-sidecar.exe"
if (-not (Test-Path -LiteralPath $Built)) {
    throw "找不到 PyInstaller 輸出：$Built"
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
    throw "無法更新 sidecar：$Target"
}
Write-Host "Sidecar ready: $Target"
