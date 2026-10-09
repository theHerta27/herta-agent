param([switch]$Demo)
$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Set-Location -LiteralPath $taskRoot
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
$taskElectron = Join-Path $taskRoot 'frontend\node_modules\electron\dist\electron.exe'
$taskEntry = Join-Path $taskRoot 'frontend\dist\electron\main.cjs'

try {
    if (!(Test-Path -LiteralPath $taskPython) -or !(Test-Path -LiteralPath $taskElectron)) {
        throw 'Project dependencies are missing. Follow README installation steps first.'
    }
    Remove-Item -LiteralPath 'Env:ELECTRON_RUN_AS_NODE' -ErrorAction SilentlyContinue
    foreach ($taskName in @('DEEPSEEK_API_KEY','HERTA_API_KEY','HERTA_EMBEDDING_API_KEY')) {
        if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($taskName, 'Process'))) {
            $taskValue = [Environment]::GetEnvironmentVariable($taskName, 'User')
            if (![string]::IsNullOrWhiteSpace($taskValue)) {
                [Environment]::SetEnvironmentVariable($taskName, $taskValue, 'Process')
            }
        }
    }
    $taskSettings = Join-Path $taskRoot '.local\desktop\settings.json'
    if (Test-Path -LiteralPath $taskSettings) {
        $taskPublic = Get-Content -LiteralPath $taskSettings -Raw | ConvertFrom-Json
        $taskMap = @{
            chatBaseUrl='HERTA_BASE_URL'; chatModel='HERTA_MODEL';
            embeddingBaseUrl='HERTA_EMBEDDING_BASE_URL'; embeddingModel='HERTA_EMBEDDING_MODEL';
            embeddingProvider='HERTA_EMBEDDING_PROVIDER'; contextWindow='HERTA_CONTEXT_WINDOW';
            outputReserve='HERTA_CONTEXT_OUTPUT_RESERVE'; summaryEnabled='HERTA_CONTEXT_SUMMARY'
        }
        foreach ($taskField in $taskMap.Keys) {
            if ($null -ne $taskPublic.$taskField) {
                $taskValue = [string]$taskPublic.$taskField
                [Environment]::SetEnvironmentVariable($taskMap[$taskField], $taskValue.ToLowerInvariant(), 'Process')
            }
        }
        # Preserve case-sensitive model names and URL paths.
        foreach ($taskField in @('chatBaseUrl','chatModel','embeddingBaseUrl','embeddingModel')) {
            if ($null -ne $taskPublic.$taskField) {
                [Environment]::SetEnvironmentVariable($taskMap[$taskField], [string]$taskPublic.$taskField, 'Process')
            }
        }
    }
    if ($Demo) { $env:HERTA_SERVICE_PROVIDER = 'demo' }
    else {
        $env:HERTA_SERVICE_PROVIDER = 'openai'
        if ([string]::IsNullOrWhiteSpace($env:HERTA_API_KEY) -and [string]::IsNullOrWhiteSpace($env:DEEPSEEK_API_KEY)) {
            $taskSecret = Read-Host 'Chat API Key (masked; used only for this launch)' -AsSecureString
            $env:HERTA_API_KEY = [Net.NetworkCredential]::new('', $taskSecret).Password
            Remove-Variable taskSecret
        }
    }
    Write-Host 'Checking knowledge index...'
    $taskBootstrapArgs = @('-m','herta_agent.bootstrap','--prepare','--report',(Join-Path $taskRoot '.local\desktop\startup-report.json'))
    if ($Demo) { $taskBootstrapArgs += '--offline' }
    & $taskPython @taskBootstrapArgs
    if ($LASTEXITCODE -ne 0) { throw 'Startup check failed. Review README and local configuration.' }
    if (!(Test-Path -LiteralPath $taskEntry)) {
        & npm --prefix (Join-Path $taskRoot 'frontend') run build
        if ($LASTEXITCODE -ne 0) { throw 'Desktop build failed.' }
    }
    Start-Process -FilePath $taskElectron -ArgumentList @('"' + $taskEntry + '"') -WorkingDirectory $taskRoot -WindowStyle Normal
    Write-Host 'Herta desktop opened.'
} catch {
    Write-Host 'Unable to start Herta. Check dependencies and public settings in README.' -ForegroundColor Red
    Read-Host 'Press Enter to close'
    exit 1
}
