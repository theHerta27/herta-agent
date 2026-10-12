param([switch]$Demo, [switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$taskPythonHome = Join-Path $taskRoot '.local\python\runtime'
if (-not (Test-Path -LiteralPath (Join-Path $taskPythonHome 'python.exe'))) { throw 'Bundled Python is missing.' }
foreach ($taskVenv in @('.venv', '.local\gpt-sovits\.venv')) {
    $taskVenvRoot = Join-Path $taskRoot $taskVenv
    if (Test-Path -LiteralPath $taskVenvRoot) {
        [IO.File]::WriteAllText((Join-Path $taskVenvRoot 'pyvenv.cfg'), "home = $taskPythonHome`ninclude-system-site-packages = false`nversion_info = 3.12.13`n", [Text.UTF8Encoding]::new($false))
    }
}
[IO.File]::WriteAllText((Join-Path $taskRoot '.venv\Lib\site-packages\_editable_impl_herta_agent.pth'), (Join-Path $taskRoot 'backend') + "`n", [Text.UTF8Encoding]::new($false))
$env:PYTHONPATH = Join-Path $taskRoot 'backend'
$taskEmbedding = Join-Path $taskRoot '.local\embedding\bge-large-zh'
if (Test-Path -LiteralPath $taskEmbedding) { $env:HERTA_LOCAL_EMBEDDING_MODEL = $taskEmbedding }
if ($CheckOnly) {
    & (Join-Path $taskRoot '.venv\Scripts\python.exe') -c 'import herta_agent,sys; from herta_agent.companion.speech import SpeechService; print(herta_agent.__file__); print(sys.base_prefix); print(SpeechService().status())'
    exit $LASTEXITCODE
}
& (Join-Path $PSScriptRoot 'Start-Herta.ps1') -Demo:$Demo
