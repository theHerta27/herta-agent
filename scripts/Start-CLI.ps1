param([string]$Repo, [string]$Resume, [switch]$ListSessions, [switch]$Demo, [switch]$Trace, [switch]$Plain)
$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$taskCli = Join-Path $taskRoot '.venv-cli\Scripts\herta-agent.exe'
try {
    if (!(Test-Path -LiteralPath $taskCli)) {
        throw '还没有安装CLI，请按 docs/CLI_GUIDE.md 中的安装步骤准备。'
    }
    if ([string]::IsNullOrWhiteSpace($Repo)) { $Repo = Read-Host '请输入要处理的项目文件夹路径，然后按回车' }
    if ([string]::IsNullOrWhiteSpace($Repo) -or !(Test-Path -LiteralPath $Repo -PathType Container)) {
        throw '找不到这个文件夹。请粘贴已有文件夹的完整路径，不要加引号。'
    }
    if (!$Demo -and !$ListSessions) {
        foreach ($taskName in @('DEEPSEEK_API_KEY','HERTA_API_KEY')) {
            if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($taskName, 'Process'))) {
                $taskValue = [Environment]::GetEnvironmentVariable($taskName, 'User')
                if (![string]::IsNullOrWhiteSpace($taskValue)) {
                    [Environment]::SetEnvironmentVariable($taskName, $taskValue, 'Process')
                }
            }
        }
    }
    $taskArguments = @('--repo', [IO.Path]::GetFullPath($Repo))
    if ($Trace) { $taskArguments += '--trace' }
    if ($Plain) { $taskArguments += '--plain' }
    if ($Demo) { $taskArguments += @('--provider','demo') }
    else { $taskArguments += @('--provider','openai') }
    if ($ListSessions) { $taskArguments += '--list-sessions' }
    if ($Resume) { $taskArguments += @('--resume', $Resume) }
    & $taskCli @taskArguments
    exit $LASTEXITCODE
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    Read-Host '按回车关闭'
    exit 1
}
