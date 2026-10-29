$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Binary = Join-Path $ProjectRoot "src-tauri\binaries\fanbox-archiver-sidecar-x86_64-pc-windows-msvc.exe"
$SmokeDirectory = Join-Path $ProjectRoot "build\sidecar-smoke"
$Config = Join-Path $SmokeDirectory "config.yaml"
$StandardOutput = Join-Path $SmokeDirectory "stdout.log"
$StandardError = Join-Path $SmokeDirectory "stderr.log"

if (-not (Test-Path -LiteralPath $Binary -PathType Leaf)) {
    throw "Sidecar not found: $Binary. Run npm run desktop:sidecar first."
}

New-Item -ItemType Directory -Force -Path $SmokeDirectory | Out-Null
Set-Content -LiteralPath $Config -Value "{}" -Encoding UTF8
Remove-Item -LiteralPath $StandardOutput, $StandardError -Force -ErrorAction SilentlyContinue

$Listener = [System.Net.Sockets.TcpListener]::new(
    [System.Net.IPAddress]::Loopback, 0
)
$Listener.Start()
$Port = ([System.Net.IPEndPoint]$Listener.LocalEndpoint).Port
$Listener.Stop()
$QuotedConfig = '"' + $Config + '"'

$Process = Start-Process `
    -FilePath $Binary `
    -ArgumentList @("serve", "--no-open", "--port", $Port.ToString(), "--config", $QuotedConfig) `
    -PassThru `
    -WindowStyle Hidden `
    -RedirectStandardOutput $StandardOutput `
    -RedirectStandardError $StandardError

try {
    $Deadline = [DateTime]::UtcNow.AddSeconds(30)
    $Healthy = $false
    while ([DateTime]::UtcNow -lt $Deadline) {
        if ($Process.HasExited) {
            $ErrorText = if (Test-Path -LiteralPath $StandardError) {
                Get-Content -LiteralPath $StandardError -Raw
            } else { "" }
            throw "Sidecar exited early (exit $($Process.ExitCode)): $ErrorText"
        }
        try {
            $Response = Invoke-WebRequest `
                -UseBasicParsing `
                -Uri "http://127.0.0.1:$Port/api/health" `
                -TimeoutSec 1
            if ($Response.StatusCode -eq 200) {
                $Healthy = $true
                break
            }
        } catch {
            Start-Sleep -Milliseconds 100
        }
    }
    if (-not $Healthy) {
        throw "Sidecar did not pass its health check within 30 seconds."
    }
    Write-Host "Sidecar smoke test passed: http://127.0.0.1:$Port/api/health"
} finally {
    if (-not $Process.HasExited) {
        & taskkill.exe /PID $Process.Id /T /F 2>$null | Out-Null
        [void]$Process.WaitForExit(5000)
    }
}
