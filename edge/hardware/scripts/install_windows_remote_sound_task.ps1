param(
    [Parameter(Mandatory = $true)]
    [string]$PiHost,
    [string]$PiUser = "pi",
    [string]$IdentityFile = "$env:USERPROFILE\.ssh\id_ed25519",
    [string]$TaskName = "PSSA-Windows-Remote-Sound",
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"

$hardwareRoot = Split-Path -Parent $PSScriptRoot

function Stop-RemoteSoundProcesses {
    $targets = Get-CimInstance Win32_Process | Where-Object {
        (($_.Name -eq "python.exe") -and (
            ($_.CommandLine -match "study_space_hardware\.remote_sound_(supervisor|agent)") -or
            ($_.CommandLine -like "*run_windows_remote_sound_supervisor.py*")
        )) -or
        (($_.Name -eq "ssh.exe") -and
            ($_.CommandLine -like "*127.0.0.1:18766:127.0.0.1:8766*"))
    }
    foreach ($target in $targets) {
        Stop-Process -Id $target.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

if ($Uninstall) {
    Stop-RemoteSoundProcesses
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Output "Removed scheduled task: $TaskName"
    exit 0
}

$python = Join-Path $hardwareRoot ".venv-windows\Scripts\python.exe"
$launcher = Join-Path $PSScriptRoot "run_windows_remote_sound_supervisor.py"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Missing $python. Create the Windows environment and install .[remote-sound] first."
}
if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
    throw "Missing task bootstrap: $launcher"
}
if (-not (Test-Path -LiteralPath $IdentityFile -PathType Leaf)) {
    throw "SSH identity file does not exist: $IdentityFile"
}

$venvConfig = Join-Path $hardwareRoot ".venv-windows\pyvenv.cfg"
$executableLine = Get-Content -LiteralPath $venvConfig -Encoding UTF8 |
    Where-Object { $_ -like "executable = *" } |
    Select-Object -First 1
if (-not $executableLine) {
    throw "Cannot find the base Python executable in $venvConfig"
}
$basePython = $executableLine.Substring("executable = ".Length).Trim()
if (-not (Test-Path -LiteralPath $basePython -PathType Leaf)) {
    throw "Base Python executable does not exist: $basePython"
}

$token = [Environment]::GetEnvironmentVariable("PSSA_REMOTE_SOUND_TOKEN", "User")
if ([string]::IsNullOrWhiteSpace($token) -or $token.Length -lt 24) {
    throw "The user-level PSSA_REMOTE_SOUND_TOKEN is missing or too short."
}

$env:PSSA_REMOTE_SOUND_TOKEN = $token

$arguments = @(
    "`"$launcher`"",
    "--ssh-host",
    $PiHost,
    "--ssh-user",
    $PiUser,
    "--identity-file",
    "`"$IdentityFile`""
) -join " "
$action = New-ScheduledTaskAction `
    -Execute $basePython `
    -Argument $arguments `
    -WorkingDirectory $hardwareRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

Stop-RemoteSoundProcesses
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Privacy-safe Windows microphone summaries with resilient SSH reconnect" `
    -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 3

$supervisor = Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -eq "python.exe") -and
    ($_.CommandLine -like "*run_windows_remote_sound_supervisor.py*")
} | Select-Object -First 1
if (-not $supervisor) {
    # Task Scheduler can transiently return 0xC0000142 when a rapidly replaced
    # Python task is still releasing DLLs. A single delayed retry is sufficient.
    Start-ScheduledTask -TaskName $TaskName
    Start-Sleep -Seconds 5
    $supervisor = Get-CimInstance Win32_Process | Where-Object {
        ($_.Name -eq "python.exe") -and
        ($_.CommandLine -like "*run_windows_remote_sound_supervisor.py*")
    } | Select-Object -First 1
}
if (-not $supervisor) {
    $failedInfo = Get-ScheduledTaskInfo -TaskName $TaskName
    throw "Remote sound task did not stay running (result $($failedInfo.LastTaskResult))."
}

$task = Get-ScheduledTask -TaskName $TaskName
$info = Get-ScheduledTaskInfo -TaskName $TaskName
[pscustomobject]@{
    TaskName = $TaskName
    State = $task.State
    LastTaskResult = $info.LastTaskResult
    PiHost = $PiHost
    RawAudioPersisted = $false
}
