param([switch]$Lite, [switch]$NoPause)
$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
try {
    Set-Location -LiteralPath $taskRoot
    & npm --prefix frontend run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    $taskDestination = Join-Path $taskRoot ('release\Herta-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    $taskArguments = @((Join-Path $PSScriptRoot 'package_product.py'), '--destination', $taskDestination)
    if ($Lite) { $taskArguments += '--lite' }
    & (Join-Path $taskRoot '.venv\Scripts\python.exe') @taskArguments
    if ($LASTEXITCODE -ne 0) { throw 'Product packaging failed.' }
    Write-Host "Product ready: $taskDestination"
} catch { Write-Host $_.Exception.Message -ForegroundColor Red; exit 1 }
finally { if (-not $NoPause) { Read-Host 'Press Enter to close' | Out-Null } }
