param([switch]$NoPause)
$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$runtime = Join-Path $taskRoot '.local\libreoffice'
$engine = Join-Path $runtime 'unpacked\program\soffice.com'
$package = Join-Path $runtime 'LibreOffice_26.8.1_Win_x86-64.msi'
try {
    New-Item -ItemType Directory -Path $runtime -Force | Out-Null
    if (-not (Test-Path -LiteralPath $engine -PathType Leaf)) {
        if (-not (Test-Path -LiteralPath $package -PathType Leaf)) {
            & curl.exe -fL --retry 3 --connect-timeout 20 --max-time 1800 -o $package 'https://download.documentfoundation.org/libreoffice/stable/26.8.1/win/x86_64/LibreOffice_26.8.1_Win_x86-64.msi'
            if ($LASTEXITCODE -ne 0) { throw 'Public dependency download failed.' }
        }
        if ((Get-FileHash -LiteralPath $package -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'c6298b10cfa1748bcbedad94c62ce771e240e5021bfd6d7a967cd571b04b5312') { throw 'LibreOffice package SHA-256 mismatch. No extraction performed.' }
        $target = [IO.Path]::GetFullPath((Join-Path $runtime 'unpacked'))
        if (-not $target.StartsWith($runtime + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Extraction target is outside runtime directory.' }
        $arguments = @('/a', ('"' + $package + '"'), '/qn', ('TARGETDIR="' + $target + '"'))
        $process = Start-Process -FilePath 'msiexec.exe' -ArgumentList $arguments -WindowStyle Hidden -PassThru -Wait
        if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $engine -PathType Leaf)) { throw 'Local engine extraction failed.' }
    }
    Write-Host 'Local DOCX-to-PDF engine is ready. No documents were uploaded.'
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
} finally {
    if (-not $NoPause) { Read-Host 'Press Enter to close' }
}
