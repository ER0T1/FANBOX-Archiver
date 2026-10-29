param(
    [Parameter(Mandatory = $true)]
    [string]$Tag
)

$ErrorActionPreference = "Stop"
$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$BuildRoot = [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot "build"))
$TemporaryRoot = [System.IO.Path]::GetFullPath((Join-Path $BuildRoot "release-signing"))
$ReleaseRoot = [System.IO.Path]::GetFullPath((Join-Path $BuildRoot "release"))
foreach ($Directory in @($TemporaryRoot, $ReleaseRoot)) {
    if (-not $Directory.StartsWith($BuildRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to use a release directory outside the project build folder."
    }
}
$CertificatePath = Join-Path $TemporaryRoot "windows-signing.pfx"
$SigningConfigPath = Join-Path $TemporaryRoot "tauri.signing.json"
$ImportedThumbprints = @()
$ExistingThumbprints = @(Get-ChildItem -LiteralPath "Cert:\CurrentUser\My" -ErrorAction SilentlyContinue | ForEach-Object { $_.Thumbprint })
$OriginalLocation = Get-Location

if (-not $env:WINDOWS_CERTIFICATE -or -not $env:WINDOWS_CERTIFICATE_PASSWORD) {
    throw "WINDOWS_CERTIFICATE and WINDOWS_CERTIFICATE_PASSWORD are required for a formal release."
}

& (Join-Path $PSScriptRoot "check-version.ps1") -ExpectedVersion $Tag
if ($LASTEXITCODE -ne 0) { throw "Version validation failed." }

if (Test-Path -LiteralPath $TemporaryRoot) {
    Remove-Item -LiteralPath $TemporaryRoot -Recurse -Force
}
if (Test-Path -LiteralPath $ReleaseRoot) {
    Remove-Item -LiteralPath $ReleaseRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $TemporaryRoot, $ReleaseRoot -Force | Out-Null

try {
    Set-Location $ProjectRoot
    $CertificateBase64 = $env:WINDOWS_CERTIFICATE `
        -replace '-----BEGIN [^-]+-----', '' `
        -replace '-----END [^-]+-----', '' `
        -replace '\s', ''
    [System.IO.File]::WriteAllBytes(
        $CertificatePath,
        [System.Convert]::FromBase64String($CertificateBase64)
    )

    $SecurePassword = ConvertTo-SecureString $env:WINDOWS_CERTIFICATE_PASSWORD -AsPlainText -Force
    $ImportedCertificates = @(Import-PfxCertificate `
        -FilePath $CertificatePath `
        -CertStoreLocation "Cert:\CurrentUser\My" `
        -Password $SecurePassword)
    $ImportedThumbprints = @(
        $ImportedCertificates |
            ForEach-Object { $_.Thumbprint } |
            Where-Object { $_ -notin $ExistingThumbprints } |
            Sort-Object -Unique
    )
    $SigningCertificate = $ImportedCertificates | Where-Object { $_.HasPrivateKey } | Select-Object -First 1
    if (-not $SigningCertificate) {
        throw "The imported PFX does not contain a certificate with a private key."
    }

    $TimestampUrl = if ($env:WINDOWS_TIMESTAMP_URL) {
        $env:WINDOWS_TIMESTAMP_URL
    } else {
        "http://timestamp.digicert.com"
    }
    $SigningConfig = @{
        bundle = @{
            windows = @{
                certificateThumbprint = $SigningCertificate.Thumbprint
                digestAlgorithm = "sha256"
                timestampUrl = $TimestampUrl
                tsp = $true
                allowDowngrades = $false
            }
        }
    } | ConvertTo-Json -Depth 5
    [System.IO.File]::WriteAllText($SigningConfigPath, $SigningConfig)

    $CargoBin = Join-Path $env:USERPROFILE ".cargo\bin"
    $env:PATH = "$CargoBin;$env:PATH"
    & npm run desktop:sidecar
    if ($LASTEXITCODE -ne 0) { throw "Sidecar build failed." }
    & npx tauri build --ci --config $SigningConfigPath
    if ($LASTEXITCODE -ne 0) { throw "Signed Tauri build failed." }

    $Installer = Get-ChildItem -LiteralPath (Join-Path $ProjectRoot "src-tauri\target\release\bundle\nsis") `
        -Filter "*-setup.exe" | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
    if (-not $Installer) { throw "NSIS installer was not produced." }

    $Signature = Get-AuthenticodeSignature -LiteralPath $Installer.FullName
    if ($Signature.Status -ne [System.Management.Automation.SignatureStatus]::Valid) {
        throw "Installer Authenticode signature is not valid: $($Signature.Status)"
    }
    if ($Signature.SignerCertificate.Thumbprint -ne $SigningCertificate.Thumbprint) {
        throw "Installer was signed by an unexpected certificate."
    }

    $ReleaseInstaller = Join-Path $ReleaseRoot $Installer.Name
    Copy-Item -LiteralPath $Installer.FullName -Destination $ReleaseInstaller
    $Hash = Get-FileHash -LiteralPath $ReleaseInstaller -Algorithm SHA256
    $ChecksumLine = "$($Hash.Hash.ToLowerInvariant()) *$($Installer.Name)`n"
    [System.IO.File]::WriteAllText((Join-Path $ReleaseRoot "SHA256SUMS.txt"), $ChecksumLine)

    Write-Host "Signed release ready: $ReleaseInstaller"
    Write-Host "SHA256: $($Hash.Hash)"
}
finally {
    Set-Location $OriginalLocation
    foreach ($Thumbprint in $ImportedThumbprints) {
        $CertificateStorePath = "Cert:\CurrentUser\My\$Thumbprint"
        if (Test-Path -LiteralPath $CertificateStorePath) {
            Remove-Item -LiteralPath $CertificateStorePath -Force
        }
    }
    if (Test-Path -LiteralPath $TemporaryRoot) {
        Remove-Item -LiteralPath $TemporaryRoot -Recurse -Force
    }
}

