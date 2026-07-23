<#
.SYNOPSIS
    Enterprise Hybrid RAG Platform — Development Runner (PowerShell)
.DESCRIPTION
    Detects tools, creates venv, installs deps, starts Docker services, runs
    migrations, launches backend + frontend, and handles graceful cleanup.
    Native PowerShell — no WSL, Git Bash, or Cygwin required.
#>

#Requires -Version 5.1

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Paths
$Script:ProjectRoot = $PSScriptRoot
$Script:FrontendDir  = Join-Path $Script:ProjectRoot "frontend"
$Script:VenvDir      = Join-Path $Script:ProjectRoot ".venv"

# Auto-detect Docker Compose file
$Script:DockerComposeFile = $null
$d1 = Join-Path $Script:ProjectRoot "docker-compose.yml"
$d2 = Join-Path $Script:ProjectRoot "docker-compose.dev.yml"
if (Test-Path $d1 -PathType Leaf) { $Script:DockerComposeFile = $d1 }
elseif (Test-Path $d2 -PathType Leaf) { $Script:DockerComposeFile = $d2 }

$Script:EnvExample     = Join-Path $Script:ProjectRoot ".env.example"
$Script:EnvFile        = Join-Path $Script:ProjectRoot ".env"
$Script:FrontendEnv    = Join-Path $Script:FrontendDir ".env"
$Script:PyprojectFile  = Join-Path $Script:ProjectRoot "pyproject.toml"
$Script:RequirementsTxt= Join-Path $Script:ProjectRoot "requirements.txt"
$Script:NodeReqFile    = Join-Path $Script:FrontendDir "package.json"
$Script:AlembicIni     = Join-Path $Script:ProjectRoot "alembic.ini"

# State
$Script:BackendJob     = $null
$Script:FrontendJob    = $null
$Script:CtrlCPressed   = $false

# Color output functions
function Write-Info  { Write-Host "[INFO]  " -NoNewline -ForegroundColor Cyan;   Write-Host $args }
function Write-Ok    { Write-Host "[ OK ]  " -NoNewline -ForegroundColor Green;  Write-Host $args }
function Write-Warn  { Write-Host "[WARN]  " -NoNewline -ForegroundColor Yellow; Write-Host $args }
function Write-Err   { Write-Host "[ERROR] " -NoNewline -ForegroundColor Red;    Write-Host $args; exit 1 }

# Utility functions
function Test-Command {
    param([string]$Command)
    try {
        $null = Get-Command $Command -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

function Test-PythonPip {
    param([string]$PythonCmd)
    try {
        $ver = & $PythonCmd -m pip --version 2>&1 | Select-Object -First 1
        return ($LASTEXITCODE -eq 0) -and ($null -ne $ver)
    } catch {
        return $false
    }
}

function Get-CommandVersion {
    param([string]$Command)
    try {
        $ver = & $Command --version 2>&1 | Select-Object -First 1
        return $ver.ToString().Trim()
    } catch {
        return "unknown version"
    }
}

function Test-TcpPort {
    param([string]$HostName, [int]$Port, [int]$TimeoutMs = 3000)
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $async = $tcp.BeginConnect($HostName, $Port, $null, $null)
        $wait = $async.AsyncWaitHandle.WaitOne($TimeoutMs, $false)
        if ($wait) {
            $tcp.EndConnect($async)
            $tcp.Close()
            return $true
        }
        $tcp.Close()
        return $false
    } catch {
        return $false
    }
}

function Wait-ForPort {
    param([string]$HostName = "localhost", [int]$Port, [int]$TimeoutSeconds = 60)
    Write-Info "Waiting for ${HostName}:${Port} to be reachable (timeout: ${TimeoutSeconds}s)..."
    $elapsed = 0
    $interval = 2
    while ($elapsed -lt $TimeoutSeconds) {
        if (Test-TcpPort $HostName $Port) { return $true }
        Start-Sleep -Seconds $interval
        $elapsed += $interval
    }
    return $false
}

function Wait-ForHttpOk {
    param([string]$Url, [int]$TimeoutSeconds = 60)
    Write-Info "Waiting for $Url to be ready (timeout: ${TimeoutSeconds}s)..."
    $elapsed = 0
    $interval = 2
    while ($elapsed -lt $TimeoutSeconds) {
        try {
            $response = Invoke-WebRequest -Uri $Url -Method GET -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
            if ($response.StatusCode -eq 200 -or $response.StatusCode -eq 204) { return $true }
        } catch {
            # Service not ready yet
        }
        Start-Sleep -Seconds $interval
        $elapsed += $interval
    }
    return $false
}

function Stop-BackgroundJob {
    param($Job)
    if ($null -ne $Job) {
        try {
            Stop-Job $Job -ErrorAction SilentlyContinue
            Remove-Job $Job -Force -ErrorAction SilentlyContinue
        } catch {
            # Already cleaned up
        }
    }
}

# Ctrl+C handler
$Script:CtrlCHandler = {
    param($sender, $e)
    if (-not $Script:CtrlCPressed) {
        $Script:CtrlCPressed = $true
        Write-Host ""
        Write-Info "Shutting down development environment..."
        Cleanup
    }
}

# Register Ctrl+C handler (may not be available in non-interactive mode)
$Script:HasConsoleEventHandler = $false
try {
    [Console]::CancelKeyPress += $Script:CtrlCHandler
    $Script:HasConsoleEventHandler = $true
} catch {
    Write-Warn "Ctrl+C handler not available in this context."
}

# Cleanup function
function Cleanup {
    # Stop frontend job
    if ($null -ne $Script:FrontendJob) {
        Write-Info "Stopping frontend..."
        Stop-BackgroundJob $Script:FrontendJob
        Write-Ok "Frontend stopped."
    }

    # Kill orphaned vite/node processes
    try {
        $viteProcs = Get-CimInstance Win32_Process -Filter "Name = 'node.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -match "vite" }
        foreach ($proc in $viteProcs) {
            try { Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue } catch {}
        }
        $npmProcs = Get-CimInstance Win32_Process -Filter "Name = 'npm.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -match "vite" }
        foreach ($proc in $npmProcs) {
            try { Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue } catch {}
        }
    } catch {
        # CIM/WMI not available
    }

    # Stop backend job
    if ($null -ne $Script:BackendJob) {
        Write-Info "Stopping backend..."
        Stop-BackgroundJob $Script:BackendJob
        Write-Ok "Backend stopped."
    }

    # Kill orphaned uvicorn/python processes
    try {
        $uvicornProcs = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -match "uvicorn" }
        foreach ($proc in $uvicornProcs) {
            try { Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue } catch {}
        }
        $pythonProcs = Get-CimInstance Win32_Process -Filter "Name = 'python3.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -match "uvicorn" }
        foreach ($proc in $pythonProcs) {
            try { Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue } catch {}
        }
    } catch {
        # CIM/WMI not available
    }

    # Docker cleanup
    if ($null -ne $Script:DockerComposeFile -and (Test-Command "docker")) {
        $stopDocker = $env:STOP_DOCKER
        if ($stopDocker -eq "true") {
            Write-Info "Stopping Docker containers..."
            $null = & docker compose -f $Script:DockerComposeFile down 2>&1
            Write-Ok "Docker containers stopped."
        } else {
            Write-Info "Docker containers left running. Set STOP_DOCKER to true to stop them."
        }
    }

    Write-Ok "Shutdown complete."
    if ($Script:CtrlCPressed -and $Script:HasConsoleEventHandler) {
        try { [Console]::CancelKeyPress.Remove($Script:CtrlCHandler) } catch {}
    }
}

# ===== MAIN EXECUTION =====

Write-Host ""
Write-Host "Enterprise Hybrid RAG Platform - Setup" -ForegroundColor Cyan
Write-Host ""

try {

# Step 1: Detect Required Tools
Write-Host "[1/8] Checking required tools..." -ForegroundColor White

Write-Ok "PowerShell $($PSVersionTable.PSVersion) found"

$pythonCmd = $null
if (Test-Command "python") {
    $pythonCmd = "python"
    Write-Ok "python found: $(Get-CommandVersion python)"
} elseif (Test-Command "py") {
    $pythonCmd = "py"
    Write-Ok "py (Python launcher) found"
} else {
    Write-Err "Python not found."
}

if (Test-Command "pip") {
    Write-Ok "pip found: $(Get-CommandVersion pip)"
} elseif (Test-PythonPip $pythonCmd) {
    Write-Ok "pip available via $pythonCmd -m pip"
} else {
    Write-Err "pip not found."
}

if (Test-Command "node") {
    Write-Ok "node found: $(Get-CommandVersion node)"
} else {
    Write-Err "Node.js not found."
}

if (Test-Command "npm") {
    Write-Ok "npm found: $(Get-CommandVersion npm)"
} else {
    Write-Err "npm not found."
}

if (Test-Command "docker") {
    Write-Ok "docker found: $(Get-CommandVersion docker)"
    $null = & docker compose version 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Ok "docker compose available"
    } else {
        Write-Warn "docker compose not found - Docker services cannot be started."
    }
} else {
    Write-Warn "docker not found - install Docker Desktop for Windows."
}

# Step 2: Setup Environment Files
Write-Host ""
Write-Host "[2/8] Setting up environment files..." -ForegroundColor White

if (-not (Test-Path $Script:EnvFile -PathType Leaf)) {
    if (Test-Path $Script:EnvExample -PathType Leaf) {
        Copy-Item $Script:EnvExample $Script:EnvFile
        Write-Ok "Created backend .env from .env.example"
        Write-Warn "Edit .env with your actual credentials before production use."
    } else {
        Write-Warn "No .env.example found - skipping backend .env creation."
    }
} else {
    Write-Ok "Backend .env already exists."
}

if (-not (Test-Path $Script:FrontendEnv -PathType Leaf)) {
    $frontendExample = Join-Path $Script:FrontendDir ".env.example"
    if (Test-Path $frontendExample -PathType Leaf) {
        Copy-Item $frontendExample $Script:FrontendEnv
        Write-Ok "Created frontend .env from .env.example"
    } else {
        $envContent = "# Frontend Environment"
        $envContent = $envContent + "`n" + "VITE_API_BASE_URL=http://localhost:8000/api/v1"
        Set-Content -Path $Script:FrontendEnv -Value $envContent
        Write-Ok "Created minimal frontend .env"
    }
} else {
    Write-Ok "Frontend .env already exists."
}

# Step 3: Python Virtual Environment
Write-Host ""
Write-Host "[3/8] Setting up Python virtual environment..." -ForegroundColor White

$activatePath = Join-Path $Script:VenvDir "Scripts\Activate.ps1"
if (-not (Test-Path $activatePath -PathType Leaf)) {
    Write-Info "Creating virtual environment in $($Script:VenvDir)..."
    if (Test-Path $Script:VenvDir) {
        Remove-Item $Script:VenvDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    $null = & $pythonCmd -m venv $Script:VenvDir
    if ($LASTEXITCODE -ne 0) { Write-Err "Failed to create virtual environment." }
    Write-Ok "Virtual environment created."
} else {
    Write-Ok "Virtual environment already exists."
}

if (Test-Path $activatePath -PathType Leaf) {
    . $activatePath
    $pythonPath = (Get-Command python).Source
    Write-Ok "Virtual environment activated: $pythonPath"
} else {
    Write-Err "Cannot activate virtual environment."
}

# Step 4: Install Backend Dependencies
Write-Host ""
Write-Host "[4/8] Installing backend dependencies..." -ForegroundColor White

if (Test-Path $Script:PyprojectFile -PathType Leaf) {
    Write-Info "Installing dependencies from pyproject.toml..."
    & python -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { Write-Warn "pip upgrade failed, continuing..." }
    & python -m pip install -e ".[dev]"
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "pip install failed. Run 'pip install -e .[dev]' manually. Continuing anyway..."
    } else {
        Write-Ok "Backend dependencies installed."
    }
} elseif (Test-Path $Script:RequirementsTxt -PathType Leaf) {
    Write-Info "Installing dependencies from requirements.txt..."
    & python -m pip install -r $Script:RequirementsTxt
    if ($LASTEXITCODE -ne 0) { Write-Err "Failed to install backend dependencies." }
    Write-Ok "Backend dependencies installed from requirements.txt."
} else {
    Write-Warn "No pyproject.toml or requirements.txt found - skipping backend install."
}

# Step 5: Install Frontend Dependencies
Write-Host ""
Write-Host "[5/8] Installing frontend dependencies..." -ForegroundColor White

if (Test-Path $Script:NodeReqFile -PathType Leaf) {
    $nodeModulesPath = Join-Path $Script:FrontendDir "node_modules"
    if (-not (Test-Path $nodeModulesPath)) {
        Write-Info "Installing frontend dependencies..."
        Push-Location $Script:FrontendDir
        try {
            & npm install 2>&1 | Select-Object -Last 5
            if ($LASTEXITCODE -ne 0) { Write-Err "npm install failed." }
        } finally {
            Pop-Location
        }
        Write-Ok "Frontend dependencies installed."
    } else {
        Write-Ok "Frontend node_modules already exists."
    }
} else {
    Write-Warn "No package.json found in frontend - skipping frontend install."
}

# Step 6: Start Docker Services
Write-Host ""
Write-Host "[6/8] Starting infrastructure services..." -ForegroundColor White

if ($null -ne $Script:DockerComposeFile -and (Test-Command "docker")) {
    $composeName = Split-Path $Script:DockerComposeFile -Leaf
    Write-Info "Starting Docker Compose services from $composeName..."

    # Capture docker output — convert stderr ErrorRecords to plain strings.
    # PS 5.1 treats native command stderr via 2>&1 as ErrorRecord objects.
    # With $ErrorActionPreference='Stop', Docker warnings (e.g. obsolete 'version')
    # would otherwise become terminating errors. Converting to strings prevents this.
    $rawOutput = & docker compose -f $Script:DockerComposeFile up -d 2>&1
    $dockerExitCode = $LASTEXITCODE
    $dockerOutput = $rawOutput | ForEach-Object { "$_" }

    if ($dockerExitCode -ne 0) {
        Write-Warn "Docker Compose failed to start (exit code: $dockerExitCode). Check Docker Desktop is running."
    } else {
        if ($dockerOutput) {
            $dockerOutput | Select-Object -Last 3 | ForEach-Object { Write-Host "  $_" }
        }
        $pgHost = if ($env:POSTGRES_HOST) { $env:POSTGRES_HOST } else { "localhost" }
        $pgPort = if ($env:POSTGRES_PORT) { [int]$env:POSTGRES_PORT } else { 5432 }
        if (Wait-ForPort $pgHost $pgPort 30) {
            Write-Ok "PostgreSQL is ready on ${pgHost}:${pgPort}"
        } else {
            Write-Warn "PostgreSQL did not become ready within 30s."
        }
        $redisHost = if ($env:REDIS_HOST) { $env:REDIS_HOST } else { "localhost" }
        $redisPort = if ($env:REDIS_PORT) { [int]$env:REDIS_PORT } else { 6379 }
        if (Wait-ForPort $redisHost $redisPort 15) {
            Write-Ok "Redis is ready on ${redisHost}:${redisPort}"
        } else {
            Write-Warn "Redis did not become ready within 15s."
        }
        $composeContent = Get-Content $Script:DockerComposeFile -Raw -ErrorAction SilentlyContinue
        if ($composeContent -match "milvus") {
            if (Wait-ForPort "localhost" 19530 60) {
                Write-Ok "Milvus is ready on localhost:19530"
            } else {
                Write-Warn "Milvus did not become ready within 60s."
            }
        }
    }
} else {
    Write-Warn "Docker Compose file not found or Docker not available."
    Write-Warn "Ensure PostgreSQL and Redis are running manually."
}

# Step 7: Run Database Migrations
Write-Host ""
Write-Host "[7/8] Running database migrations..." -ForegroundColor White

if (Test-Path $Script:AlembicIni -PathType Leaf) {
    if (Test-Command "alembic") {
        Push-Location $Script:ProjectRoot
        try {
            & alembic upgrade head 2>&1 | Select-Object -Last 5 | ForEach-Object { Write-Host "  $_" }
            if ($LASTEXITCODE -ne 0) {
                Write-Warn "Alembic migration may have failed (check PostgreSQL is running)."
            } else {
                Write-Ok "Database migrations applied."
            }
        } catch {
            Write-Warn "Alembic migration error: $_"
        } finally {
            Pop-Location
        }
    } else {
        $venvAlembic = Join-Path $Script:VenvDir "Scripts\alembic.exe"
        if (Test-Path $venvAlembic) {
            Push-Location $Script:ProjectRoot
            try {
                & $venvAlembic upgrade head 2>&1 | Select-Object -Last 5 | ForEach-Object { Write-Host "  $_" }
                if ($LASTEXITCODE -ne 0) {
                    Write-Warn "Alembic migration may have failed (check PostgreSQL is running)."
                } else {
                    Write-Ok "Database migrations applied."
                }
            } catch {
                Write-Warn "Alembic migration error: $_"
            } finally {
                Pop-Location
            }
        } else {
            Write-Warn "alembic not found in venv - skipping migrations."
        }
    }
} else {
    Write-Warn "No alembic.ini found - skipping migrations."
}

# Step 8: Start Services
Write-Host ""
Write-Host "[8/8] Starting application servers..." -ForegroundColor White

# Start backend
Write-Info "Starting FastAPI backend..."
$backendJob = Start-Job -Name "rag-backend" -ScriptBlock {
    param($rootDir, $envPath)
    $env:PYTHONPATH = $rootDir
    Set-Location $rootDir
    . (Join-Path $envPath "Scripts\Activate.ps1")
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --log-level info
} -ArgumentList $Script:ProjectRoot, $Script:VenvDir
$Script:BackendJob = $backendJob
Write-Ok "Backend starting (Job ID: $($backendJob.Id))..."

$backendUrl = "http://localhost:8000/api/v1/health/live"
if (Wait-ForHttpOk $backendUrl 45) {
    Write-Ok "Backend is healthy!"
} else {
    Write-Warn "Backend health check did not return 200/204 within 45s."
}

# Start frontend
if (Test-Path $Script:NodeReqFile -PathType Leaf) {
    Write-Info "Starting Vite frontend..."
    $frontendJob = Start-Job -Name "rag-frontend" -ScriptBlock {
        param($frontendDir)
        Set-Location $frontendDir
        npm run dev
    } -ArgumentList $Script:FrontendDir
    $Script:FrontendJob = $frontendJob
    Write-Ok "Frontend starting (Job ID: $($frontendJob.Id))..."
}

# Print Summary
Write-Host ""
Write-Host "Enterprise Hybrid RAG Platform" -ForegroundColor Green
Write-Host "Development Environment - READY" -ForegroundColor Green
Write-Host ""
Write-Host "  Backend:" -ForegroundColor White
Write-Host "    http://localhost:8000" -ForegroundColor Cyan
Write-Host ""
Write-Host "  API Docs:" -ForegroundColor White
Write-Host "    http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host "    http://localhost:8000/redoc" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Frontend:" -ForegroundColor White
Write-Host "    http://localhost:5173" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Press Ctrl+C to stop all services." -ForegroundColor DarkGray
Write-Host "  Set STOP_DOCKER=true to also stop Docker containers on exit." -ForegroundColor DarkGray
Write-Host ""

# Wait for background jobs
$runningJobs = @()
if ($null -ne $Script:BackendJob)  { $runningJobs += $Script:BackendJob }
if ($null -ne $Script:FrontendJob) { $runningJobs += $Script:FrontendJob }

while ($runningJobs.Count -gt 0 -and -not $Script:CtrlCPressed) {
    $completed = @()
    foreach ($job in $runningJobs) {
        $jobState = $job.State
        if ($jobState -eq 'Completed' -or $jobState -eq 'Failed' -or $jobState -eq 'Stopped') {
            $completed += $job
            $output = Receive-Job $job -ErrorAction SilentlyContinue
            if ($jobState -eq 'Failed') {
                Write-Warn "Job $($job.Name) exited with state: $jobState"
            }
        }
    }
    foreach ($job in $completed) {
        $runningJobs = $runningJobs | Where-Object { $_.Id -ne $job.Id }
        Remove-Job $job -Force -ErrorAction SilentlyContinue
    }
    if ($runningJobs.Count -gt 0) {
        Start-Sleep -Seconds 1
    }
}

} catch {
    $errMsg = "An unexpected error occurred: $_"
    Write-Host ""
    Write-Host "[ERROR] $errMsg" -ForegroundColor Red
    Write-Host "Stack trace: $($_.ScriptStackTrace)" -ForegroundColor DarkGray
    exit 1
}

# Normal exit cleanup
Cleanup
