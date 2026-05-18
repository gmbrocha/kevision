param(
    [Parameter(Position = 0)]
    [ValidateSet("check", "status", "start", "stop", "restart")]
    [string]$Command = "check",

    [string]$HostName = "127.0.0.1",
    [int]$Port = 5000,
    [switch]$Production,
    [switch]$Cloudflare,
    [switch]$All,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$RepoRoot = $PSScriptRoot
$ProjectName = Split-Path -Leaf $RepoRoot
$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$LogsDir = Join-Path $RepoRoot "logs"
$BackendOutLog = Join-Path $LogsDir "scopeledger_backend.out.log"
$BackendErrLog = Join-Path $LogsDir "scopeledger_backend.err.log"
$CloudflaredExe = "C:\cloudflared\cloudflared.exe"
$CloudflareTunnelName = "nez-dev-projects"

if ($All) {
    $Cloudflare = $true
}

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host "== $Title =="
}

function Get-AllProcesses {
    Get-CimInstance Win32_Process
}

function Get-DescendantProcessIds {
    param(
        [Parameter(Mandatory = $true)] [int[]]$RootIds,
        [Parameter(Mandatory = $true)] $Processes
    )

    $ids = New-Object "System.Collections.Generic.HashSet[int]"
    foreach ($id in $RootIds) {
        [void]$ids.Add([int]$id)
    }

    do {
        $changed = $false
        foreach ($process in $Processes) {
            if ($process.ParentProcessId -and $ids.Contains([int]$process.ParentProcessId) -and -not $ids.Contains([int]$process.ProcessId)) {
                [void]$ids.Add([int]$process.ProcessId)
                $changed = $true
            }
        }
    } while ($changed)

    return [int[]]$ids
}

function Get-BackendProcesses {
    $processes = @(Get-AllProcesses)
    $roots = @(
        $processes | Where-Object {
            $_.ProcessId -ne $PID -and (
                ($_.ExecutablePath -and $_.ExecutablePath.StartsWith($RepoRoot, [System.StringComparison]::OrdinalIgnoreCase)) -or
                ($_.CommandLine -and $_.CommandLine.IndexOf($RepoRoot, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -and $_.CommandLine -match "\s-m\s+backend\s+serve\b") -or
                ($_.CommandLine -and $_.CommandLine -match "\s-m\s+backend\s+serve\b" -and $_.CommandLine -match "--port\s+$Port\b")
            )
        }
    )

    if (-not $roots) {
        return @()
    }

    $ids = Get-DescendantProcessIds -RootIds @($roots | ForEach-Object { [int]$_.ProcessId }) -Processes $processes
    return @($processes | Where-Object { $ids -contains [int]$_.ProcessId } | Sort-Object ProcessId)
}

function Get-ProjectServices {
    Get-CimInstance Win32_Service | Where-Object {
        ($_.PathName -and $_.PathName.IndexOf($RepoRoot, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) -or
        ($_.Name -like "*$ProjectName*") -or
        ($_.DisplayName -like "*$ProjectName*") -or
        ($_.Name -like "*ScopeLedger*") -or
        ($_.DisplayName -like "*ScopeLedger*")
    }
}

function Get-PortListeners {
    Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -eq $Port } |
        Sort-Object LocalAddress, OwningProcess
}

function Get-CloudflareProcesses {
    Get-AllProcesses | Where-Object {
        $_.ProcessId -ne $PID -and
        ($_.Name -like "cloudflared*" -or ($_.ExecutablePath -and $_.ExecutablePath -like "*cloudflared*"))
    } | Sort-Object ProcessId
}

function Show-Status {
    Write-Section "Backend Processes"
    $backend = @(Get-BackendProcesses)
    if ($backend) {
        $backend | Select-Object ProcessId, ParentProcessId, Name, ExecutablePath, CommandLine | Format-Table -Wrap -AutoSize
    } else {
        Write-Host "No ScopeLedger backend processes found."
    }

    Write-Section "Port $Port Listeners"
    $listeners = @(Get-PortListeners)
    if ($listeners) {
        $listenerRows = @()
        foreach ($listener in $listeners) {
            $owner = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)" -ErrorAction SilentlyContinue
            $listenerRows += [pscustomobject]@{
                LocalAddress = $listener.LocalAddress
                LocalPort = $listener.LocalPort
                OwningProcess = $listener.OwningProcess
                ProcessName = $owner.Name
                CommandLine = $owner.CommandLine
            }
        }
        $listenerRows | Format-Table -Wrap -AutoSize
    } else {
        Write-Host "No listener found on port $Port."
    }

    Write-Section "Windows Services"
    $services = @(Get-ProjectServices)
    if ($services) {
        $services | Select-Object Name, DisplayName, State, StartMode, ProcessId, PathName | Format-Table -Wrap -AutoSize
    } else {
        Write-Host "No ScopeLedger-named or repo-rooted Windows services found."
    }

    Write-Section "Cloudflare Tunnel"
    $cloudflare = @(Get-CloudflareProcesses)
    if ($cloudflare) {
        $cloudflare | Select-Object ProcessId, ParentProcessId, Name, ExecutablePath, CommandLine | Format-Table -Wrap -AutoSize
    } else {
        Write-Host "No cloudflared process found."
    }
}

function Stop-Backend {
    $backend = @(Get-BackendProcesses)
    if (-not $backend) {
        Write-Host "Backend: nothing to stop."
        return
    }
    foreach ($process in ($backend | Sort-Object ProcessId -Descending)) {
        if ($DryRun) {
            Write-Host "Would stop backend process $($process.ProcessId) $($process.Name)"
        } else {
            Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
            Write-Host "Stopped backend process $($process.ProcessId) $($process.Name)"
        }
    }
}

function Stop-ProjectServices {
    $services = @(Get-ProjectServices | Where-Object { $_.State -eq "Running" })
    if (-not $services) {
        Write-Host "Services: nothing to stop."
        return
    }
    foreach ($service in $services) {
        if ($DryRun) {
            Write-Host "Would stop service $($service.Name)"
        } else {
            Stop-Service -Name $service.Name -Force -ErrorAction SilentlyContinue
            Write-Host "Stopped service $($service.Name)"
        }
    }
}

function Stop-Cloudflare {
    $processes = @(Get-CloudflareProcesses)
    if (-not $processes) {
        Write-Host "Cloudflare: nothing to stop."
        return
    }
    foreach ($process in $processes) {
        if ($DryRun) {
            Write-Host "Would stop cloudflared process $($process.ProcessId)"
        } else {
            Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
            Write-Host "Stopped cloudflared process $($process.ProcessId)"
        }
    }
}

function Start-Backend {
    $backend = @(Get-BackendProcesses)
    if ($backend) {
        Write-Host "Backend already appears to be running."
        return
    }
    if (-not (Test-Path $PythonExe)) {
        throw "Python virtualenv not found at $PythonExe"
    }

    if (-not (Test-Path $LogsDir)) {
        New-Item -ItemType Directory -Path $LogsDir | Out-Null
    }

    $args = @("-m", "backend", "serve", "--host", $HostName, "--port", "$Port")
    if ($Production) {
        $args += "--production"
    }

    if ($DryRun) {
        Write-Host "Would start backend: $PythonExe $($args -join ' ')"
        return
    }

    $process = Start-Process -FilePath $PythonExe -ArgumentList $args -WorkingDirectory $RepoRoot -WindowStyle Hidden -RedirectStandardOutput $BackendOutLog -RedirectStandardError $BackendErrLog -PassThru
    Write-Host "Started backend process $($process.Id) at http://$HostName`:$Port"
    Write-Host "stdout: $BackendOutLog"
    Write-Host "stderr: $BackendErrLog"
}

function Start-ProjectServices {
    $services = @(Get-ProjectServices | Where-Object { $_.State -ne "Running" -and $_.StartMode -ne "Disabled" })
    if (-not $services) {
        Write-Host "Services: no stopped enabled ScopeLedger services found."
        return
    }
    foreach ($service in $services) {
        if ($DryRun) {
            Write-Host "Would start service $($service.Name)"
        } else {
            Start-Service -Name $service.Name -ErrorAction SilentlyContinue
            Write-Host "Started service $($service.Name)"
        }
    }
}

function Start-Cloudflare {
    $processes = @(Get-CloudflareProcesses)
    if ($processes) {
        Write-Host "Cloudflare tunnel already appears to be running."
        return
    }
    if (-not (Test-Path $CloudflaredExe)) {
        Write-Host "Cloudflare: $CloudflaredExe not found; cannot start tunnel."
        return
    }
    if ($DryRun) {
        Write-Host "Would start Cloudflare tunnel: $CloudflaredExe tunnel run $CloudflareTunnelName"
        return
    }

    $process = Start-Process -FilePath $CloudflaredExe -ArgumentList @("tunnel", "run", $CloudflareTunnelName) -WindowStyle Hidden -PassThru
    Write-Host "Started Cloudflare tunnel process $($process.Id) for $CloudflareTunnelName"
}

function Invoke-Stop {
    Write-Section "Stopping"
    Stop-Backend
    Stop-ProjectServices
    if ($Cloudflare) {
        Stop-Cloudflare
    } else {
        Write-Host "Cloudflare: skipped. Use -Cloudflare or -All to include the tunnel."
    }
}

function Invoke-Start {
    Write-Section "Starting"
    Start-ProjectServices
    Start-Backend
    if ($Cloudflare) {
        Start-Cloudflare
    } else {
        Write-Host "Cloudflare: skipped. Use -Cloudflare or -All to include the tunnel."
    }
}

switch ($Command) {
    "check" { Show-Status }
    "status" { Show-Status }
    "stop" { Invoke-Stop; Show-Status }
    "start" { Invoke-Start; Show-Status }
    "restart" { Invoke-Stop; Start-Sleep -Seconds 2; Invoke-Start; Show-Status }
}
