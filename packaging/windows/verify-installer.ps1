param(
    [Parameter(Mandatory = $true)][string]$Installer,
    [Parameter(Mandatory = $true)][string]$Version,
    [Parameter(Mandatory = $true)][string]$Revision
)

$ErrorActionPreference = 'Stop'
$installerExe = (Resolve-Path -LiteralPath $Installer).Path
$session = Join-Path ([IO.Path]::GetTempPath()) "Comic Sequence Studio smoke-$([guid]::NewGuid())"
$application = Join-Path $session 'Installed App'
$report = Join-Path $session 'installed-smoke.json'
$installLog = Join-Path $session 'install.log'
$uninstallLog = Join-Path $session 'uninstall.log'
$appExe = Join-Path $application 'Comic-Sequence-Studio.exe'
$installerArgs = "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- /DIR=`"$application`" /LOG=`"$installLog`""
$uninstallerArgs = "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /LOG=`"$uninstallLog`""
$startMenu = [Environment]::GetFolderPath('Programs')
$shortcut = Join-Path $startMenu 'Comic Sequence Studio.lnk'
$uninstallEntry = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{DB866465-3034-46A5-9E90-6FC8857FA624}_is1'
if ((Test-Path -LiteralPath $shortcut) -or (Test-Path -LiteralPath $uninstallEntry)) {
    throw 'Use a clean Windows test account so setup and uninstall leave any existing installation intact.'
}

function Invoke-CheckedProcess {
    param([string]$Path, [string]$Arguments, [int]$TimeoutSeconds = 180)

    $process = Start-Process -FilePath $Path -ArgumentList $Arguments -WorkingDirectory $session -PassThru
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        Stop-Process -Id $process.Id -Force
        throw "Timed out running $Path."
    }
    if ($process.ExitCode -ne 0) {
        throw "$Path returned exit code $($process.ExitCode)."
    }
}

$savedEnvironment = @{}
foreach ($name in @('PATH', 'PYTHONHOME', 'PYTHONPATH', 'VIRTUAL_ENV', 'LOCALAPPDATA')) {
    $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}

try {
    New-Item -ItemType Directory -Path $session | Out-Null
    Invoke-CheckedProcess $installerExe $installerArgs
    if (-not (Test-Path -LiteralPath $shortcut -PathType Leaf)) {
        throw 'Setup did not create the Start menu shortcut.'
    }
    $shell = New-Object -ComObject WScript.Shell
    if ($shell.CreateShortcut($shortcut).TargetPath -ne $appExe) {
        throw 'The Start menu shortcut does not target the installed app.'
    }
    $frozen = Join-Path $application '_internal'
    $metadata = @{'VERSION.txt' = $Version; 'REVISION.txt' = $Revision}
    foreach ($entry in $metadata.GetEnumerator()) {
        $value = (Get-Content -LiteralPath (Join-Path $frozen $entry.Key) -Raw).Trim()
        if ($value -cne $entry.Value) {
            throw "The installed $($entry.Key) expected $($entry.Value). Got $value."
        }
    }

    $env:Path = "$env:SystemRoot\System32;$env:SystemRoot"
    foreach ($name in @('PYTHONHOME', 'PYTHONPATH', 'VIRTUAL_ENV')) {
        [Environment]::SetEnvironmentVariable($name, $null, 'Process')
    }
    $env:LOCALAPPDATA = (New-Item -ItemType Directory -Path (Join-Path $session 'Local App Data')).FullName
    Invoke-CheckedProcess $appExe "--installer-smoke `"$report`""
    $result = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
    if ($result.status -ne 'ok' -or $result.revision -cne $Revision) {
        throw 'The installed application smoke report does not match the release.'
    }
    Get-Content -LiteralPath $report -Raw

    $process = Start-Process -FilePath $appExe -WorkingDirectory $session -PassThru
    try {
        $deadline = (Get-Date).AddSeconds(45)
        do {
            $process.Refresh()
            if ($process.HasExited) {
                throw "The app closed before opening its main window. Exit code $($process.ExitCode)."
            }
            if ($process.MainWindowHandle -and $process.Responding) {
                break
            }
            Start-Sleep -Milliseconds 200
        } until ((Get-Date) -ge $deadline)
        if (-not $process.MainWindowHandle -or -not $process.Responding) {
            throw 'The app did not open a responsive main window.'
        }
        Write-Output "Opened installed Tk window: $($process.MainWindowTitle)"
        if (-not $process.CloseMainWindow() -or -not $process.WaitForExit(15000)) {
            throw 'The installed app did not close cleanly.'
        }
    } finally {
        if (-not $process.HasExited) {
            Stop-Process -Id $process.Id -Force
        }
    }

    $uninstaller = Get-ChildItem -LiteralPath $application -Filter 'unins*.exe' -File | Select-Object -First 1
    if (-not $uninstaller) {
        throw 'The installer did not register an uninstaller.'
    }
    Invoke-CheckedProcess $uninstaller.FullName $uninstallerArgs
    if ((Test-Path -LiteralPath $appExe) -or (Test-Path -LiteralPath $shortcut) -or
        (Test-Path -LiteralPath $uninstallEntry)) {
        throw 'The uninstaller did not remove the app, its shortcut, or its registration.'
    }
    Write-Output 'Verified silent Windows installation, the frozen app and uninstall.'
} catch {
    foreach ($log in @($installLog, $report, $uninstallLog)) {
        if (Test-Path -LiteralPath $log -PathType Leaf) {
            Get-Content -LiteralPath $log -Tail 35 | Write-Output
        }
    }
    throw
} finally {
    foreach ($name in $savedEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name], 'Process')
    }
    if (Test-Path -LiteralPath $application) {
        $uninstaller = Get-ChildItem -LiteralPath $application -Filter 'unins*.exe' -File | Select-Object -First 1
        if ($uninstaller) {
            try {
                Invoke-CheckedProcess $uninstaller.FullName $uninstallerArgs 60
            } catch {
                Write-Warning "Could not clean up the test installation: $_"
            }
        }
    }
    if (Test-Path -LiteralPath $session) {
        Remove-Item -LiteralPath $session -Force -Recurse -ErrorAction SilentlyContinue
    }
}
