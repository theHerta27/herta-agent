param(
    [string]$RepoRoot = $env:HERTA_CODING_REPO_ROOT,
    [string]$DependencyFile = 'backend/pyproject.toml',
    [string]$DependencyExtra = 'dev',
    [string]$Image = 'herta-coding-sandbox:local'
)
$ErrorActionPreference = 'Stop'
if (-not $RepoRoot) { $RepoRoot = Split-Path -Parent $PSScriptRoot }
$targetRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
$manifest = (Resolve-Path -LiteralPath (Join-Path $targetRoot $DependencyFile)).Path
if (-not $manifest.StartsWith($targetRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'DependencyFile must be inside RepoRoot.'
}
$projectDir = Split-Path -Parent $manifest
$lock = Join-Path $projectDir 'uv.lock'
if (-not (Test-Path -LiteralPath $lock)) { throw 'Target uv.lock is required. Lock target dependencies first.' }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Install and start Docker Desktop (Linux containers) first.' }
$dockerOS = & docker info --format '{{.OSType}}'
if ($LASTEXITCODE -ne 0 -or $dockerOS -ne 'linux') { throw 'Docker Desktop Linux containers must be running.' }
$repoDir = Split-Path -Parent $PSScriptRoot
$dockerfile = Join-Path $repoDir 'docker/coding-sandbox/Dockerfile'
$plugin = Join-Path $repoDir 'backend/herta_agent/tools/coding/pytest_report.py'
$hashInputs = @($manifest, $lock, $dockerfile, $plugin) | ForEach-Object {
    (Get-FileHash -LiteralPath $_ -Algorithm SHA256).Hash
}
$hashBytes = [Text.Encoding]::UTF8.GetBytes(($hashInputs -join "`n") + "`n$DependencyExtra")
$hasher = [Security.Cryptography.SHA256]::Create()
try { $fingerprint = [BitConverter]::ToString($hasher.ComputeHash($hashBytes)).Replace('-', '').ToLowerInvariant() }
finally { $hasher.Dispose() }
$existing = & docker image inspect $Image --format '{{index .Config.Labels "herta.dependencies"}}' 2>$null
if ($LASTEXITCODE -eq 0 -and $existing -eq $fingerprint) {
    Write-Output "Reusing $Image (dependencies unchanged)"
    exit 0
}
# A minimal temporary build context, never the complete target repository.
$context = Join-Path ([IO.Path]::GetTempPath()) ('herta-sandbox-build-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $context | Out-Null
try {
    Copy-Item -LiteralPath $dockerfile -Destination (Join-Path $context 'Dockerfile')
    Copy-Item -LiteralPath $plugin -Destination (Join-Path $context 'herta_pytest_report.py')
    $exportArgs = @('export', '--project', $projectDir, '--locked', '--no-emit-project',
                    '--format', 'requirements-txt', '--output-file', (Join-Path $context 'requirements.txt'))
    if ($DependencyExtra) { $exportArgs += @('--extra', $DependencyExtra) }
    & uv @exportArgs
    if ($LASTEXITCODE -ne 0) { throw 'Target dependency export failed.' }
    & docker build --label "herta.dependencies=$fingerprint" --tag $Image $context
    if ($LASTEXITCODE -ne 0) { throw 'Sandbox image build failed.' }
    Write-Output "Built $Image ($fingerprint)"
} finally {
    $resolvedContext = [IO.Path]::GetFullPath($context)
    $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    if (-not $resolvedContext.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase) -or
        (Split-Path -Leaf $resolvedContext) -notlike 'herta-sandbox-build-*') {
        throw 'Refusing to clean unexpected temporary path.'
    }
    Remove-Item -LiteralPath $resolvedContext -Recurse -Force
}
