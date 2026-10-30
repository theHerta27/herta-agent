param([string]$Repo, [string]$Resume, [switch]$ListSessions, [switch]$Demo, [switch]$Trace, [switch]$Plain, [ValidateSet('checkout','wordcount')][string]$Case)
$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$taskCli = Join-Path $taskRoot '.venv-cli\Scripts\herta-agent.exe'
try {
    if (!(Test-Path -LiteralPath $taskCli)) {
        throw '还没有安装CLI，请按 docs/CLI_GUIDE.md 中的安装步骤准备。'
    }
    if ($Case) {
        if ($Repo -or $Resume -or $ListSessions) {
            throw '-Case 会新建演示目录，不能同时指定 -Repo、-Resume 或 -ListSessions。'
        }
        $taskPython = Join-Path $taskRoot '.venv-cli\Scripts\python.exe'
        $taskPrepare = Join-Path $taskRoot 'examples\coding-task\prepare.py'
        $taskJson = & $taskPython -B -X utf8 $taskPrepare --case $Case
        if ($LASTEXITCODE -ne 0) { throw '演示目录准备失败，尚未调用模型。' }
        $taskPrepared = $taskJson | ConvertFrom-Json
        $Repo = [string]$taskPrepared.project
        Write-Host ('已新建演示文件夹：' + $Repo)
        Write-Host ('本次任务：' + $taskPrepared.task)
        if ($Demo) { Write-Host '离线回显检查：不会调用模型，也不会修复演示。' }
        else { Write-Host '即将调用真实模型；修改和测试仍会逐次询问你。' }
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
    if ($Case) {
        $taskArguments += @('--instructions','AGENTS.md','--max-steps','16','--message',[string]$taskPrepared.task)
    }
    & $taskCli @taskArguments
    $taskExitCode = $LASTEXITCODE
    if ($Case) {
        Write-Host ('演示文件已保留：' + $Repo)
        Write-Host '要独立检查，请复制下一整行；它会运行演示代码，不调用模型：'
        $taskCheck = Join-Path $taskRoot 'examples\coding-task\check.py'
        Write-Host ("& '{0}' -B -X utf8 '{1}' '{2}'" -f $taskPython.Replace("'", "''"), $taskCheck.Replace("'", "''"), $Repo.Replace("'", "''"))
    }
    exit $taskExitCode
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    Read-Host '按回车关闭'
    exit 1
}
