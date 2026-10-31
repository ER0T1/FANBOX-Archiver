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

& $Python -m pytest tests/e2e -m e2e
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
