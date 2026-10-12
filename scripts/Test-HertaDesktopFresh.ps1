function Assert-HertaDesktopFresh {
    param([Parameter(Mandatory=$true)][string]$Root)
    $desktopRoot = [IO.Path]::GetFullPath($Root)
    $entry = Join-Path $desktopRoot 'frontend\dist\electron\main.cjs'
    $renderer = Join-Path $desktopRoot 'frontend\dist\renderer\index.html'
    $executable = Join-Path $desktopRoot 'frontend\node_modules\electron\dist\electron.exe'
    $folder = Join-Path $desktopRoot 'frontend'
    $built = [datetime]::MinValue
    $missing = $false
    foreach ($file in @($entry, $renderer)) {
        if (Test-Path -LiteralPath $file) {
            $changed = (Get-Item -LiteralPath $file).LastWriteTimeUtc
            if ($changed -gt $built) { $built = $changed }
        } else { $missing = $true }
    }
    foreach ($instance in @(Get-CimInstance Win32_Process -Filter "Name='electron.exe'" -ErrorAction Stop)) {
        if (!$instance.ExecutablePath -or $instance.CommandLine -match '--type=') { continue }
        if ([IO.Path]::GetFullPath($instance.ExecutablePath) -ne $executable) { continue }
        $sameEntry = $false
        foreach ($argument in [regex]::Matches($instance.CommandLine, '"([^"]*)"|(\S+)')) {
            $value = if ($argument.Groups[1].Success) { $argument.Groups[1].Value } else { $argument.Groups[2].Value }
            if ($value -notmatch '^(?:[A-Za-z]:[\\/]|\\\\)') { continue }
            $full = [IO.Path]::GetFullPath($value)
            if ($full -eq $entry -or $full -eq $folder) { $sameEntry = $true; break }
        }
        if (!$sameEntry) { continue }
        $started = ([datetimeoffset]$instance.CreationDate).UtcDateTime
        if ($missing -or $started -lt $built) {
            throw ("An older Herta desktop is still running (PID {0}). Save your draft, choose 'Exit Herta' from the system tray, then reopen this launcher. Closing the window only hides it." -f $instance.ProcessId)
        }
    }
}
