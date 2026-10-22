$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Set-Location -LiteralPath $taskRoot
try {
    $env:UV_CACHE_DIR = Join-Path $taskRoot '.local\uv-cache'
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $taskRoot '.local\python'
    $env:UV_PROJECT_ENVIRONMENT = Join-Path $taskRoot '.venv'
    Write-Host 'Installing optional local voice dependencies from the lockfile...'
    & uv sync --project backend --extra desktop --extra dev --extra local --extra voice --python 3.12 --locked
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    Write-Host 'Downloading public voice models. No chat or audio content will be uploaded.'
    & (Join-Path $taskRoot '.venv\Scripts\python.exe') (Join-Path $taskRoot 'scripts\prepare_voice.py')
    if ($LASTEXITCODE -ne 0) { throw 'Model preparation failed.' }
    Write-Host 'Local voice is ready. Restart Herta if it is already running.'
} catch {
    Write-Host 'Voice preparation failed. Check uv/network access and try again.' -ForegroundColor Red
    exit 1
} finally {
    Read-Host 'Press Enter to close'
}
