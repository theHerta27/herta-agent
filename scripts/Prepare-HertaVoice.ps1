param([switch]$VerifyOnly, [switch]$NoPause)
$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$runtimeRoot = Join-Path $taskRoot '.local\gpt-sovits'
$runtimePython = Join-Path $runtimeRoot '.venv\Scripts\python.exe'
try {
    Set-Location -LiteralPath $taskRoot
    $env:HERTA_VOICE_RUNTIME = $runtimeRoot
    if (-not (Test-Path -LiteralPath $runtimePython)) {
        if ($VerifyOnly) { throw 'Isolated voice environment is missing.' }
        New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
        & uv venv --python 3.12 (Join-Path $runtimeRoot '.venv')
        if ($LASTEXITCODE -ne 0) { throw 'Voice venv preparation failed.' }
        & uv pip install --python $runtimePython --extra-index-url https://download.pytorch.org/whl/cu118 -r (Join-Path $PSScriptRoot 'gpt_sovits\requirements-lock.txt')
        if ($LASTEXITCODE -ne 0) { throw 'Voice dependency installation failed.' }
    }
    $upstreamPath = Join-Path $runtimeRoot 'upstream'
    if (-not (Test-Path -LiteralPath $upstreamPath)) {
        if ($VerifyOnly) { throw 'Pinned source is missing.' }
        & git clone https://github.com/RVC-Boss/GPT-SoVITS.git $upstreamPath
        if ($LASTEXITCODE -ne 0) { throw 'Source download failed.' }
        & git -C $upstreamPath checkout 1b47ca07ef43a284e0b8bd7f29d3e1e3ff76082a
        if ($LASTEXITCODE -ne 0) { throw 'Pinned checkout failed.' }
    }
    $sourceRevision = if (Test-Path -LiteralPath (Join-Path $upstreamPath '.git')) { & git -C $upstreamPath rev-parse HEAD } else { Get-Content -LiteralPath (Join-Path $runtimeRoot 'source-revision.txt') -Raw }
    if ($sourceRevision.Trim() -ne '1b47ca07ef43a284e0b8bd7f29d3e1e3ff76082a') { throw 'Unexpected upstream source revision.' }
    if (-not $VerifyOnly) {
        & $runtimePython (Join-Path $PSScriptRoot 'gpt_sovits\patch_upstream.py')
        if ($LASTEXITCODE -ne 0) { throw 'Hardening patch failed.' }
        & $runtimePython (Join-Path $PSScriptRoot 'gpt_sovits\download_models.py')
        if ($LASTEXITCODE -ne 0) { throw 'Base model preparation failed.' }
    }
    & (Join-Path $taskRoot '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'verify_herta_provider.py')
    if ($LASTEXITCODE -ne 0) { throw 'Real local voice verification failed.' }
    Write-Host 'Great Herta voice verified locally. Select it in the personality panel.'
} catch { Write-Host $_.Exception.Message -ForegroundColor Red; exit 1 }
finally { if (-not $NoPause) { Read-Host 'Press Enter to close' | Out-Null } }
