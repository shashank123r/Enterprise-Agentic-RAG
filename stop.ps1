<#
.SYNOPSIS
    Enterprise Hybrid RAG Platform — Development Environment Stopper
.DESCRIPTION
    Gracefully stops frontend, backend, ARQ workers, and optionally Docker
    containers. Native PowerShell — no WSL, Git Bash, or Cygwin required.
    Compatible with Windows PowerShell 5.1 and PowerShell 7+.
#>

#Requires -Version 5.1

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ── Paths ───────────────────────────────────────────────────────────────────
$Script:ProjectRoot = $PSScriptRoot

$Script:DockerComposeFile = $null
$composeCandidates = @(
    (Join-Path $Script:ProjectRoot "docker-compose.yml"),
    (Join-Path $Script:ProjectRoot "docker-compose.dev.yml")
)
foreach ($candidate in $composeCandidates) {
    if (Test-Path $candidate -PathType Leaf) {
        $Script:DockerComposeFile = $candidate
        break
    }
}

# ── Color Output Functions ──────────────────────────────────────────────────
function Write-Info  { Write-Host "[INFO]  " -NoNewline -ForegroundColor Cyan;   Write-Host $args }
function Write-Ok    { Write-Host "[ OK ]  " -NoNewline -ForegroundColor Green;  Write-Host $args }
function Write-Warn  { Write-Host "[WARN]  " -NoNewline -ForegroundColor Yellow; Write-Host $args }
function Write-Error { Write-Host "[ERROR] " -NoNewline -ForegroundColor Red;    Write-Host $args; exit 1 }

# ── Utility ─────────────────────────────────────────────────────────────────
function Test-Command {
    param([string]$Command)
    try {
        $null = Get-Command $Command -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

<#
.SYNOPSIS
    Find and kill processes by name and command-line pattern.
    Uses Get-CimInstance Win32_Process for PowerShell 5.1 compatibility
    (Get-Process does not expose CommandLine property on PS 5.1).
#>
function Stop-ProcessByName {
    param(
        [string]$ProcessName,       # e.g. "node.exe" or "python.exe"
        [string]$CommandLineMatch,  # regex pattern to match against command line
        [string]$Label              # human-readable label for logging
    )
    Write-Info "Looking for $Label processes..."

    try {
        $procs = Get-CimInstance Win32_Process -Filter "Name = '$ProcessName'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -match $CommandLineMatch }

        if ($null -eq $procs -or @($procs).Count -eq 0) {
            return $false
        }

        foreach ($proc in $procs) {
            try {
                Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
                Write-Ok "Stopped $Label (PID: $($proc.ProcessId))"
            } catch {
                Write-Warn "Failed to stop $Label (PID: $($proc.ProcessId)): $_"
            }
        }
        return $true
    } catch {
        # CIM/WMI might not be available in some constrained environments
        Write-Warn "Could not query processes for $Label: $_"
        return $false
    }
}

# ── Main ────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "═══════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Enterprise Hybrid RAG Platform — Shutdown" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

$stoppedSomething = $false

# ── 1. Stop Frontend (Vite) ─────────────────────────────────────────────────
$frontendStopped = Stop-ProcessByName -ProcessName "node.exe" -CommandLineMatch "vite" -Label "frontend (vite)"
if ($frontendStopped) { $stoppedSomething = $true }

# Also check for npm processes running vite
$npmStopped = Stop-ProcessByName -ProcessName "npm.exe" -CommandLineMatch "vite|run dev" -Label "npm (vite)"
if ($npmStopped) { $stoppedSomething = $true }

if (-not $frontendStopped -and -not $npmStopped) {
    Write-Info "No frontend processes found."
}

# ── 2. Stop Backend (Uvicorn) ───────────────────────────────────────────────
$backendStopped = Stop-ProcessByName -ProcessName "python.exe" -CommandLineMatch "uvicorn" -Label "backend (uvicorn)"
if (-not $backendStopped) {
    # Also check for python3.exe on some Windows Python installs
    $backendStopped = Stop-ProcessByName -ProcessName "python3.exe" -CommandLineMatch "uvicorn" -Label "backend (uvicorn)"
}
if ($backendStopped) {
    $stoppedSomething = $true
} else {
    Write-Info "No backend processes found."
}

# ── 3. Stop ARQ Workers (if any) ────────────────────────────────────────────
$workerStopped = Stop-ProcessByName -ProcessName "python.exe" -CommandLineMatch "arq" -Label "worker (arq)"
if (-not $workerStopped) {
    $workerStopped = Stop-ProcessByName -ProcessName "python3.exe" -CommandLineMatch "arq" -Label "worker (arq)"
}
if ($workerStopped) {
    $stoppedSomething = $true
} else {
    Write-Info "No worker processes found."
}

# ── 4. Brief pause to let processes fully terminate ─────────────────────────
if ($stoppedSomething) {
    Start-Sleep -Seconds 2
}

# ── 5. Stop Docker Services (optional, interactive) ─────────────────────────
if ($null -ne $Script:DockerComposeFile -and (Test-Command "docker")) {
    Write-Host ""
    Write-Info "Docker Compose file found: $(Split-Path $Script:DockerComposeFile -Leaf)"

    $stopDocker = $env:STOP_DOCKER
    if (-not $stopDocker) {
        Write-Host ""
        Write-Host "Stop Docker containers as well?" -ForegroundColor Yellow
        Write-Host "  (PostgreSQL, Redis, Milvus data will be preserved)" -ForegroundColor DarkGray
        $response = Read-Host "  [y/N]"
        if ($response -match '^[Yy]') {
            $stopDocker = "true"
        } else {
            $stopDocker = "false"
        }
    }

    if ($stopDocker -eq "true") {
        Write-Info "Stopping Docker containers..."
        $output = & docker compose -f $Script:DockerComposeFile down 2>&1
        $output | Select-Object -Last 3 | ForEach-Object { Write-Host "  $_" }
        Write-Ok "Docker containers stopped."
        $stoppedSomething = $true
    } else {
        Write-Info "Leaving Docker containers running."
    }
}

# ── 6. Port Verification ───────────────────────────────────────────────────
Write-Host ""
foreach ($port in @(8000, 5173)) {
    try {
        # Get-NetTCPConnection is available on Windows 8+/2012 R2+ (covers Win10/11)
        $connections = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
        if ($connections.Count -gt 0) {
            $ownerProcs = @()
            foreach ($conn in $connections) {
                try {
                    $owner = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
                    if ($owner) {
                        $ownerProcs += "$($owner.ProcessName) (PID: $($owner.Id))"
                    }
                } catch {}
            }
            if ($ownerProcs.Count -gt 0) {
                Write-Warn "Port $port still in use by: $($ownerProcs -join ', ')"
            }
        }
    } catch {
        # Get-NetTCPConnection not available (e.g., constrained environment)
        Write-Info "Cannot check port $port — Get-NetTCPConnection not available."
    }
}

# ── 7. Summary ──────────────────────────────────────────────────────────────
Write-Host ""
if ($stoppedSomething) {
    Write-Host "═══════════════════════════════════════════════════" -ForegroundColor Green
    Write-Host "  All services stopped successfully." -ForegroundColor Green
    Write-Host "═══════════════════════════════════════════════════" -ForegroundColor Green
} else {
    Write-Host "═══════════════════════════════════════════════════" -ForegroundColor Yellow
    Write-Host "  No running services found." -ForegroundColor Yellow
    Write-Host "═══════════════════════════════════════════════════" -ForegroundColor Yellow
}
Write-Host ""
Write-Ok "Shutdown complete."
