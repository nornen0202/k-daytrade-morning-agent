[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Checkout,
    [Parameter(Mandatory)][string]$Python,
    [Parameter(Mandatory)][string]$EnvironmentFile,
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
$Checkout = (Resolve-Path -LiteralPath $Checkout).Path
$Python = (Resolve-Path -LiteralPath $Python).Path
$env:DAYTRADE_ENV_FILE = (Resolve-Path -LiteralPath $EnvironmentFile).Path
$env:DAYTRADE_PRIVATE_ARTIFACTS_DIR = Join-Path $Checkout 'private_artifacts'
$env:PYTHONUTF8 = '1'
$env:CODEX_HOME = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.codex'
Push-Location -LiteralPath $Checkout
try {
    if ($CheckOnly) {
        & $Python -c 'from daytrade_agent.operations.morning import SEOUL, now_kst; print(SEOUL, now_kst().isoformat())'
        if ($LASTEXITCODE) { exit $LASTEXITCODE }
        Write-Output "account=$([Security.Principal.WindowsIdentity]::GetCurrent().Name)"
        exit 0
    }
    $logDir = Join-Path $env:DAYTRADE_PRIVATE_ARTIFACTS_DIR 'morning/logs'
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $start = [DateTimeOffset]::UtcNow.ToOffset([TimeSpan]::FromHours(9))
    $log = Join-Path $logDir "windows-$($start.ToString('yyyy-MM-dd')).log"
    "launcher start $($start.ToString('o'))" | Add-Content -LiteralPath $log -Encoding utf8
    & $Python -m daytrade_agent.operations.morning --trigger windows *>> $log
    $code = $LASTEXITCODE
    "launcher exit $code $([DateTimeOffset]::UtcNow.ToString('o'))" |
        Add-Content -LiteralPath $log -Encoding utf8
    exit $code
} finally {
    Pop-Location
}
