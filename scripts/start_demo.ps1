[CmdletBinding()]
param(
    [string]$PiHost = "raspberrypi.local",
    [string]$PiUser = "pi",
    [string]$IdentityFile = "$env:USERPROFILE\.ssh\id_ed25519",
    [switch]$CheckOnly,
    [switch]$NoBrowser,
    [switch]$SkipPi,
    [switch]$SkipMicrophone,
    [switch]$SkipWarmup
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $repoRoot ".runtime\demo"
$backendRoot = Join-Path $repoRoot "backend"
$frontendRoot = Join-Path $repoRoot "frontend"
$hardwareRoot = Join-Path $repoRoot "edge\hardware"
$dashboardUrl = "http://127.0.0.1:5173/?mode=api"
$backendHealthUrl = "http://127.0.0.1:8000/health"
$ollamaTagsUrl = "http://127.0.0.1:11434/api/tags"
$failures = [System.Collections.Generic.List[string]]::new()
$started = [System.Collections.Generic.List[object]]::new()

New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null

function Write-Status {
    param(
        [string]$Component,
        [string]$Message,
        [ValidateSet("ok", "info", "warning", "error")]
        [string]$Level = "info"
    )
    $color = switch ($Level) {
        "ok" { "Green" }
        "warning" { "Yellow" }
        "error" { "Red" }
        default { "Cyan" }
    }
    Write-Host ("[{0}] {1}" -f $Component, $Message) -ForegroundColor $color
}

function Add-Failure {
    param([string]$Component, [string]$Message)
    $failures.Add(("{0}: {1}" -f $Component, $Message))
    Write-Status $Component $Message "error"
}

function Test-Http {
    param([string]$Uri, [int]$TimeoutSeconds = 2)
    try {
        $null = Invoke-WebRequest `
            -Uri $Uri `
            -UseBasicParsing `
            -TimeoutSec $TimeoutSeconds
        return $true
    }
    catch {
        return $false
    }
}

function Wait-Http {
    param([string]$Uri, [int]$TimeoutSeconds = 30)
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if (Test-Http $Uri 2) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Test-TcpPort {
    param([string]$Address = "127.0.0.1", [int]$Port)
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $result = $client.BeginConnect($Address, $Port, $null, $null)
        if (-not $result.AsyncWaitHandle.WaitOne(700)) {
            return $false
        }
        $client.EndConnect($result)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

function Wait-TcpPort {
    param([string]$Address = "127.0.0.1", [int]$Port, [int]$TimeoutSeconds = 20)
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if (Test-TcpPort $Address $Port) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Get-DotEnvValue {
    param([string]$Path, [string]$Name, [string]$Default = "")
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $Default
    }
    $prefix = "$Name="
    $line = Get-Content -LiteralPath $Path -Encoding UTF8 |
        Where-Object { $_.Trim().StartsWith($prefix) } |
        Select-Object -Last 1
    if (-not $line) {
        return $Default
    }
    return $line.Trim().Substring($prefix.Length).Trim().Trim('"').Trim("'")
}

function Find-Executable {
    param([string]$Name, [string[]]$Candidates)
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }
    foreach ($candidate in $Candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            return $candidate
        }
    }
    return $null
}

function Start-LoggedProcess {
    param(
        [string]$Name,
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$WorkingDirectory
    )
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $stdout = Join-Path $runtimeRoot "$Name-$stamp.stdout.log"
    $stderr = Join-Path $runtimeRoot "$Name-$stamp.stderr.log"
    $process = Start-Process `
        -FilePath $FilePath `
        -ArgumentList $Arguments `
        -WorkingDirectory $WorkingDirectory `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr `
        -PassThru
    $started.Add(
        [pscustomobject]@{
            name = $Name
            pid = $process.Id
            stdout = $stdout
            stderr = $stderr
        }
    )
    return $process
}

Write-Host ""
Write-Host "Privacy-Preserving Study Space Advisor - demo startup" -ForegroundColor White
Write-Host "Repository: $repoRoot"
if ($CheckOnly) {
    Write-Host "Mode: check only (nothing will be started)" -ForegroundColor Yellow
}
Write-Host ""

# Local Ollama and model
$backendEnv = Join-Path $backendRoot ".env"
$llmEnabled = (Get-DotEnvValue $backendEnv "LLM_ENABLED" "false").ToLowerInvariant() -eq "true"
$llmModel = Get-DotEnvValue $backendEnv "LLM_MODEL" "qwen3:1.7b"
if ($llmEnabled) {
    if (-not (Test-Http $ollamaTagsUrl)) {
        if ($CheckOnly) {
            Add-Failure "Ollama" "not reachable at 127.0.0.1:11434"
        }
        else {
            $ollama = Find-Executable "ollama" @(
                (Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe")
            )
            if (-not $ollama) {
                Add-Failure "Ollama" "ollama.exe was not found"
            }
            else {
                $modelRoot = [Environment]::GetEnvironmentVariable(
                    "OLLAMA_MODELS",
                    "User"
                )
                if ([string]::IsNullOrWhiteSpace($modelRoot)) {
                    $modelRoot = "E:\Ollama\models"
                }
                if (-not (Test-Path -LiteralPath $modelRoot -PathType Container)) {
                    Add-Failure "Ollama" "model directory is missing: $modelRoot"
                }
                else {
                    $env:OLLAMA_MODELS = $modelRoot
                    $env:OLLAMA_NO_CLOUD = "1"
                    $env:OLLAMA_HOST = "127.0.0.1:11434"
                    $null = Start-LoggedProcess `
                        "ollama" `
                        $ollama `
                        @("serve") `
                        $repoRoot
                    if (Wait-Http $ollamaTagsUrl 30) {
                        Write-Status "Ollama" "started; models stay in $modelRoot" "ok"
                    }
                    else {
                        Add-Failure "Ollama" "did not become ready; check .runtime\demo logs"
                    }
                }
            }
        }
    }
    else {
        Write-Status "Ollama" "already running" "ok"
    }
    if (Test-Http $ollamaTagsUrl) {
        try {
            $tags = Invoke-RestMethod -Uri $ollamaTagsUrl -TimeoutSec 3
            $availableModels = @($tags.models | ForEach-Object { $_.name })
            if ($availableModels -notcontains $llmModel) {
                Add-Failure "Ollama" "required model is not installed: $llmModel"
            }
            else {
                Write-Status "Ollama" "model available: $llmModel" "ok"
            }
        }
        catch {
            Add-Failure "Ollama" "could not read the local model list"
        }
    }
}
else {
    Write-Status "Ollama" "LLM_ENABLED is false; skipped" "warning"
}

# FastAPI backend
if (Test-Http $backendHealthUrl) {
    Write-Status "Backend" "already running at http://127.0.0.1:8000" "ok"
}
elseif ($CheckOnly) {
    Add-Failure "Backend" "not reachable at http://127.0.0.1:8000"
}
else {
    $backendPython = Join-Path $backendRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $backendPython -PathType Leaf)) {
        Add-Failure "Backend" "missing virtual environment: $backendPython"
    }
    else {
        Write-Status "Backend" "applying Alembic migrations" "info"
        Push-Location $backendRoot
        try {
            & $backendPython -m alembic upgrade head
            if ($LASTEXITCODE -ne 0) {
                throw "Alembic exited with code $LASTEXITCODE"
            }
        }
        catch {
            Add-Failure "Backend" "migration failed: $($_.Exception.Message)"
        }
        finally {
            Pop-Location
        }
        if (-not ($failures | Where-Object { $_ -like "Backend:*" })) {
            $null = Start-LoggedProcess `
                "backend" `
                $backendPython `
                @(
                    "-m", "uvicorn",
                    "study_space_api.main:app",
                    "--host", "0.0.0.0",
                    "--port", "8000"
                ) `
                $backendRoot
            if (Wait-Http $backendHealthUrl 30) {
                Write-Status "Backend" "started at http://127.0.0.1:8000" "ok"
            }
            else {
                Add-Failure "Backend" "did not become ready; check .runtime\demo logs"
            }
        }
    }
}

# Raspberry Pi edge service. Never restart an already-active service because
# that would discard its in-memory thermal background.
if ($SkipPi) {
    Write-Status "Raspberry Pi" "skipped by option" "warning"
}
else {
    $ssh = Find-Executable "ssh" @("$env:WINDIR\System32\OpenSSH\ssh.exe")
    if (-not $ssh) {
        Add-Failure "Raspberry Pi" "Windows OpenSSH client was not found"
    }
    elseif (-not (Test-Path -LiteralPath $IdentityFile -PathType Leaf)) {
        Add-Failure "Raspberry Pi" "SSH identity does not exist: $IdentityFile"
    }
    else {
        $sshArgs = @(
            "-4",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=8",
            "-o", "IdentitiesOnly=yes",
            "-i", $IdentityFile,
            "$PiUser@$PiHost"
        )
        $state = (& $ssh @sshArgs "systemctl --user is-active pssa-dashboard-bridge.service" 2>$null | Select-Object -Last 1)
        if ($state -eq "active") {
            Write-Status "Raspberry Pi" "sensor service already active; left untouched" "ok"
        }
        elseif ($CheckOnly) {
            Add-Failure "Raspberry Pi" "sensor service is not active or Pi is unreachable"
        }
        else {
            Write-Status "Raspberry Pi" "starting inactive sensor service" "info"
            $null = & $ssh @sshArgs "systemctl --user start pssa-dashboard-bridge.service" 2>$null
            $state = (& $ssh @sshArgs "systemctl --user is-active pssa-dashboard-bridge.service" 2>$null | Select-Object -Last 1)
            if ($state -eq "active") {
                Write-Status "Raspberry Pi" "sensor service started" "ok"
            }
            else {
                Add-Failure "Raspberry Pi" "sensor service could not be started"
            }
        }
    }
}

# Privacy-safe Windows microphone supervisor
if ($SkipMicrophone) {
    Write-Status "Microphone" "skipped by option" "warning"
}
elseif (Test-TcpPort -Port 18766) {
    Write-Status "Microphone" "SSH sound tunnel already ready" "ok"
}
elseif ($CheckOnly) {
    Add-Failure "Microphone" "sound tunnel is not listening on 127.0.0.1:18766"
}
else {
    $taskName = "PSSA-Windows-Remote-Sound"
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($task) {
        Start-ScheduledTask -TaskName $taskName
        Write-Status "Microphone" "scheduled task requested" "info"
    }
    else {
        $soundPython = Join-Path $hardwareRoot ".venv-windows\Scripts\python.exe"
        $soundLauncher = Join-Path $hardwareRoot "scripts\run_windows_remote_sound_supervisor.py"
        $token = [Environment]::GetEnvironmentVariable(
            "PSSA_REMOTE_SOUND_TOKEN",
            "User"
        )
        if ([string]::IsNullOrWhiteSpace($token) -or $token.Length -lt 24) {
            Add-Failure "Microphone" "PSSA_REMOTE_SOUND_TOKEN is not configured"
        }
        elseif (-not (Test-Path -LiteralPath $soundPython -PathType Leaf)) {
            Add-Failure "Microphone" "missing Windows sound environment: $soundPython"
        }
        else {
            $env:PSSA_REMOTE_SOUND_TOKEN = $token
            $null = Start-LoggedProcess `
                "remote-sound" `
                $soundPython `
                @(
                    $soundLauncher,
                    "--ssh-host", $PiHost,
                    "--ssh-user", $PiUser,
                    "--identity-file", $IdentityFile
                ) `
                $hardwareRoot
        }
    }
    if (Wait-TcpPort -Port 18766 -TimeoutSeconds 20) {
        Write-Status "Microphone" "privacy-safe sound summary pipeline ready" "ok"
    }
    else {
        Add-Failure "Microphone" "pipeline did not become ready"
    }
}

# React/Vite frontend
if (Test-Http $dashboardUrl) {
    Write-Status "Frontend" "already running at http://127.0.0.1:5173" "ok"
}
elseif ($CheckOnly) {
    Add-Failure "Frontend" "not reachable at http://127.0.0.1:5173"
}
else {
    $node = Find-Executable "node" @(
        "$env:ProgramFiles\nodejs\node.exe",
        "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
    )
    $vite = Join-Path $frontendRoot "node_modules\vite\bin\vite.js"
    if (-not $node) {
        Add-Failure "Frontend" "node.exe was not found"
    }
    elseif (-not (Test-Path -LiteralPath $vite -PathType Leaf)) {
        Add-Failure "Frontend" "dependencies are missing; run npm install in frontend"
    }
    else {
        $env:VITE_API_MODE = "real"
        $env:VITE_API_BASE_URL = "http://127.0.0.1:8000"
        $null = Start-LoggedProcess `
            "frontend" `
            $node `
            @($vite, "--host", "127.0.0.1", "--port", "5173") `
            $frontendRoot
        if (Wait-Http $dashboardUrl 30) {
            Write-Status "Frontend" "started at http://127.0.0.1:5173" "ok"
        }
        else {
            Add-Failure "Frontend" "did not become ready; check .runtime\demo logs"
        }
    }
}

# Warm the configured local model only after the API services are available.
if ($llmEnabled -and -not $SkipWarmup -and -not $CheckOnly -and (Test-Http $ollamaTagsUrl)) {
    try {
        $warmupBody = @{
            model = $llmModel
            prompt = ""
            stream = $false
            keep_alive = "30m"
            options = @{
                num_predict = 1
                num_ctx = 2048
            }
        } | ConvertTo-Json -Depth 4
        $null = Invoke-RestMethod `
            -Uri "http://127.0.0.1:11434/api/generate" `
            -Method Post `
            -ContentType "application/json" `
            -Body $warmupBody `
            -TimeoutSec 90
        Write-Status "Ollama" "model warmed and kept alive for 30 minutes" "ok"
    }
    catch {
        Add-Failure "Ollama" "model warmup failed: $($_.Exception.Message)"
    }
}

if ($started.Count -gt 0) {
    $started |
        ConvertTo-Json -Depth 4 |
        Set-Content -LiteralPath (Join-Path $runtimeRoot "last-started-processes.json") -Encoding UTF8
}

if (-not $CheckOnly -and -not $NoBrowser -and (Test-Http $dashboardUrl)) {
    Start-Process $dashboardUrl
}

Write-Host ""
Write-Host "Dashboard: $dashboardUrl"
Write-Host "Backend:   http://127.0.0.1:8000/docs"
Write-Host "Logs:      $runtimeRoot"

if ($failures.Count -gt 0) {
    Write-Host ""
    Write-Host "Startup completed with $($failures.Count) problem(s):" -ForegroundColor Red
    foreach ($failure in $failures) {
        Write-Host " - $failure" -ForegroundColor Red
    }
    exit 1
}

Write-Host ""
Write-Host "All requested demo components are ready." -ForegroundColor Green
exit 0
