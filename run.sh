#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# Enterprise Hybrid RAG Platform — Development Runner
# ═══════════════════════════════════════════════════════════════════════════════
# Detects tools, creates venv, installs deps, starts Docker services, runs
# migrations, launches backend + frontend, and handles graceful cleanup.
# ═══════════════════════════════════════════════════════════════════════════════

set -Eeuo pipefail
trap '_cleanup' EXIT SIGINT SIGTERM ERR

# ── Configuration ────────────────────────────────────────────────────────────
# Auto-detect project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"

# Auto-detect subdirectories
BACKEND_DIR="$PROJECT_ROOT"
FRONTEND_DIR="${PROJECT_ROOT}/frontend"
DOCKER_COMPOSE_FILE=""
if [[ -f "${PROJECT_ROOT}/docker-compose.yml" ]]; then
    DOCKER_COMPOSE_FILE="${PROJECT_ROOT}/docker-compose.yml"
elif [[ -f "${PROJECT_ROOT}/docker-compose.dev.yml" ]]; then
    DOCKER_COMPOSE_FILE="${PROJECT_ROOT}/docker-compose.dev.yml"
fi

PYTHON_REQUIREMENTS="${PROJECT_ROOT}/pyproject.toml"
NODE_REQUIREMENTS="${FRONTEND_DIR}/package.json"
ENV_FILE="${PROJECT_ROOT}/.env"
ENV_EXAMPLE="${PROJECT_ROOT}/.env.example"
FRONTEND_ENV_FILE="${FRONTEND_DIR}/.env"
VENV_DIR="${PROJECT_ROOT}/.venv"

# PIDs for background processes
BACKEND_PID=""
FRONTEND_PID=""

# ── Terminal Colors ──────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
    COLOR_RESET="\033[0m"
    COLOR_INFO="\033[36m"    # Cyan
    COLOR_OK="\033[32m"      # Green
    COLOR_WARN="\033[33m"    # Yellow
    COLOR_ERROR="\033[31m"   # Red
    COLOR_BOLD="\033[1m"
    COLOR_DIM="\033[2m"
else
    COLOR_RESET=""
    COLOR_INFO=""
    COLOR_OK=""
    COLOR_WARN=""
    COLOR_ERROR=""
    COLOR_BOLD=""
    COLOR_DIM=""
fi

# ── Logging Functions ─────────────────────────────────────────────────────────
_log() {
    local level="$1"
    local color="$2"
    local msg="$3"
    echo -e "${color}[${level}]${COLOR_RESET} ${msg}"
}

info()  { _log "INFO"  "$COLOR_INFO"  "$*"; }
ok()    { _log " OK "  "$COLOR_OK"    "$*"; }
warn()  { _log "WARN"  "$COLOR_WARN"  "$*"; }
error() { _log "ERROR" "$COLOR_ERROR" "$*"; exit 1; }

# ── Utility Functions ─────────────────────────────────────────────────────────
_command_exists() {
    command -v "$1" &>/dev/null
}

_wait_for_port() {
    local host="$1"
    local port="$2"
    local timeout="${3:-60}"
    local interval="${4:-2}"
    info "Waiting for ${host}:${port} to be reachable (timeout: ${timeout}s)..."
    local elapsed=0
    while [[ $elapsed -lt $timeout ]]; do
        if command -v nc &>/dev/null; then
            nc -z "$host" "$port" &>/dev/null && return 0
        elif command -v curl &>/dev/null; then
            curl -s -o /dev/null "http://${host}:${port}" &>/dev/null && return 0
        else
            # Fallback: use bash /dev/tcp
            timeout 1 bash -c "echo > /dev/tcp/${host}/${port}" &>/dev/null && return 0
        fi
        sleep "$interval"
        ((elapsed += interval))
    done
    return 1
}

_wait_for_http_ok() {
    local url="$1"
    local timeout="${2:-60}"
    local interval="${3:-2}"
    info "Waiting for ${url} to be ready (timeout: ${timeout}s)..."
    local elapsed=0
    while [[ $elapsed -lt $timeout ]]; do
        if curl -s -o /dev/null -w "%{http_code}" "$url" 2>/dev/null | grep -qE "200|204"; then
            return 0
        fi
        sleep "$interval"
        ((elapsed += interval))
    done
    return 1
}



# ── Cleanup ───────────────────────────────────────────────────────────────────
_cleanup() {
    local exit_code=$?
    echo ""
    info "Shutting down development environment..."

    # Stop frontend
    if [[ -n "$FRONTEND_PID" ]] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
        info "Stopping frontend (PID: $FRONTEND_PID)..."
        kill "$FRONTEND_PID" 2>/dev/null || true
        wait "$FRONTEND_PID" 2>/dev/null || true
        ok "Frontend stopped."
    fi

    # Stop backend
    if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
        info "Stopping backend (PID: $BACKEND_PID)..."
        kill "$BACKEND_PID" 2>/dev/null || true
        wait "$BACKEND_PID" 2>/dev/null || true
        ok "Backend stopped."
    fi

    # Deactivate venv if active
    if [[ -n "${VIRTUAL_ENV:-}" ]]; then
        deactivate 2>/dev/null || true
    fi

    # Stop Docker containers unless STOP_DOCKER=false
    if [[ -n "$DOCKER_COMPOSE_FILE" && "${STOP_DOCKER:-false}" != "true" ]]; then
        info "Docker containers left running. Set STOP_DOCKER=true to stop them."
    elif [[ -n "$DOCKER_COMPOSE_FILE" && "${STOP_DOCKER:-false}" == "true" ]]; then
        info "Stopping Docker containers..."
        docker compose -f "$DOCKER_COMPOSE_FILE" down 2>/dev/null || true
        ok "Docker containers stopped."
    fi

    if [[ $exit_code -eq 0 ]]; then
        ok "Shutdown complete."
    else
        warn "Shutdown complete (exit code: $exit_code)."
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN EXECUTION
# ═══════════════════════════════════════════════════════════════════════════════

echo ""
echo -e "${COLOR_BOLD}${COLOR_INFO}═══════════════════════════════════════════════════${COLOR_RESET}"
echo -e "${COLOR_BOLD}${COLOR_INFO}  Enterprise Hybrid RAG Platform — Setup${COLOR_RESET}"
echo -e "${COLOR_BOLD}${COLOR_INFO}═══════════════════════════════════════════════════${COLOR_RESET}"
echo ""

# ── Step 1: Detect Required Tools ─────────────────────────────────────────────
echo -e "${COLOR_BOLD}[1/8] Checking required tools...${COLOR_RESET}"

TOOLS=("python3" "pip3" "node" "npm")
MISSING=()

for tool in "${TOOLS[@]}"; do
    if _command_exists "$tool"; then
        ok "$tool found: $($tool --version 2>&1 | head -1)"
    else
        # Fallback: check common aliases
        if [[ "$tool" == "python3" ]] && _command_exists "python"; then
            ok "python found: $(python --version 2>&1)"
        elif [[ "$tool" == "pip3" ]] && _command_exists "pip"; then
            ok "pip found: $(pip --version 2>&1 | head -1)"
        else
            MISSING+=("$tool")
        fi
    fi
done

# Detect Docker (optional but recommended)
if _command_exists "docker"; then
    ok "docker found: $(docker --version 2>&1)"
    if _command_exists "docker-compose" || docker compose version &>/dev/null; then
        ok "docker compose available"
    else
        warn "docker-compose not found — Docker services cannot be started."
    fi
else
    warn "docker not found — install Docker to run database services."
    warn "See: https://docs.docker.com/engine/install/"
fi

if [[ ${#MISSING[@]} -gt 0 ]]; then
    echo ""
    error "Missing required tools: ${MISSING[*]}. Please install them first."
fi

# ── Step 2: Setup Environment Files ───────────────────────────────────────────
echo ""
echo -e "${COLOR_BOLD}[2/8] Setting up environment files...${COLOR_RESET}"

# Backend .env
if [[ ! -f "$ENV_FILE" ]]; then
    if [[ -f "$ENV_EXAMPLE" ]]; then
        cp "$ENV_EXAMPLE" "$ENV_FILE"
        ok "Created $ENV_FILE from .env.example"
        warn "Edit $ENV_FILE with your actual credentials before production use."
    else
        warn "No .env.example found — skipping backend .env creation."
    fi
else
    ok "Backend .env already exists."
fi

# Frontend .env
if [[ ! -f "$FRONTEND_ENV_FILE" ]]; then
    if [[ -f "${FRONTEND_DIR}/.env.example" ]]; then
        cp "${FRONTEND_DIR}/.env.example" "$FRONTEND_ENV_FILE"
        ok "Created $FRONTEND_ENV_FILE from .env.example"
    else
        # Create a minimal frontend .env
        cat > "$FRONTEND_ENV_FILE" <<- 'EOF'
# Frontend Environment
VITE_API_BASE_URL=http://localhost:8000/api/v1
EOF
        ok "Created minimal $FRONTEND_ENV_FILE"
    fi
else
    ok "Frontend .env already exists."
fi

# ── Step 3: Python Virtual Environment ────────────────────────────────────────
echo ""
echo -e "${COLOR_BOLD}[3/8] Setting up Python virtual environment...${COLOR_RESET}"

PYTHON_BIN="python3"
_command_exists "python3" || PYTHON_BIN="python"

if [[ ! -d "$VENV_DIR" ]]; then
    info "Creating virtual environment in $VENV_DIR..."
    $PYTHON_BIN -m venv "$VENV_DIR"
    ok "Virtual environment created."
else
    ok "Virtual environment already exists."
fi

# Activate venv
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"
ok "Virtual environment activated: $(which python)"

# ── Step 4: Install Backend Dependencies ──────────────────────────────────────
echo ""
echo -e "${COLOR_BOLD}[4/8] Installing backend dependencies...${COLOR_RESET}"

if [[ -f "$PYTHON_REQUIREMENTS" ]]; then
    info "Installing dependencies from pyproject.toml..."
    pip install --upgrade pip -q
    pip install -e ".[dev]"
    ok "Backend dependencies installed."
else
    # Fallback: check for requirements.txt
    if [[ -f "${PROJECT_ROOT}/requirements.txt" ]]; then
        pip install -r "${PROJECT_ROOT}/requirements.txt" -q
        ok "Backend dependencies installed from requirements.txt."
    else
        warn "No pyproject.toml or requirements.txt found — skipping backend install."
    fi
fi

# ── Step 5: Install Frontend Dependencies ─────────────────────────────────────
echo ""
echo -e "${COLOR_BOLD}[5/8] Installing frontend dependencies...${COLOR_RESET}"

if [[ -f "$NODE_REQUIREMENTS" ]]; then
    if [[ ! -d "${FRONTEND_DIR}/node_modules" ]]; then
        info "Installing frontend dependencies..."
        (cd "$FRONTEND_DIR" && npm install 2>&1 | tail -5)
        ok "Frontend dependencies installed."
    else
        ok "Frontend node_modules already exists."
    fi
else
    warn "No package.json found — skipping frontend install."
fi

# ── Step 6: Start Docker Services ─────────────────────────────────────────────
echo ""
echo -e "${COLOR_BOLD}[6/8] Starting infrastructure services...${COLOR_RESET}"

if [[ -n "$DOCKER_COMPOSE_FILE" ]] && _command_exists "docker"; then
    info "Starting Docker Compose services from $(basename "$DOCKER_COMPOSE_FILE")..."
    docker compose -f "$DOCKER_COMPOSE_FILE" up -d 2>&1 | tail -3 || {
        warn "Docker Compose failed to start. Check Docker is running."
    }

    # Wait for PostgreSQL
    POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
    POSTGRES_PORT="${POSTGRES_PORT:-5432}"
    if _wait_for_port "$POSTGRES_HOST" "$POSTGRES_PORT" 30; then
        ok "PostgreSQL is ready on ${POSTGRES_HOST}:${POSTGRES_PORT}"
    else
        warn "PostgreSQL did not become ready within 30s — continuing anyway."
    fi

    # Wait for Redis
    REDIS_HOST="${REDIS_HOST:-localhost}"
    REDIS_PORT="${REDIS_PORT:-6379}"
    if _wait_for_port "$REDIS_HOST" "$REDIS_PORT" 15; then
        ok "Redis is ready on ${REDIS_HOST}:${REDIS_PORT}"
    else
        warn "Redis did not become ready within 15s — continuing anyway."
    fi

    # Wait for Milvus (if present in docker-compose)
    if grep -q "milvus" "$DOCKER_COMPOSE_FILE" 2>/dev/null; then
        if _wait_for_port "localhost" "19530" 60; then
            ok "Milvus is ready on localhost:19530"
        else
            warn "Milvus did not become ready within 60s — continuing anyway."
        fi
    fi
else
    warn "Docker Compose file not found or Docker not available."
    warn "Ensure PostgreSQL and Redis are running manually."
fi

# ── Step 7: Run Database Migrations ───────────────────────────────────────────
echo ""
echo -e "${COLOR_BOLD}[7/8] Running database migrations...${COLOR_RESET}"

if _command_exists "alembic" || [[ -f "${VENV_DIR}/bin/alembic" ]]; then
    if [[ -f "${PROJECT_ROOT}/alembic.ini" ]]; then
        cd "$PROJECT_ROOT"
        alembic upgrade head 2>&1 | tail -5
        cd "$PROJECT_ROOT"
        ok "Database migrations applied."
    else
        warn "No alembic.ini found — skipping migrations."
    fi
else
    # Try using the venv-installed alembic
    if [[ -f "${VENV_DIR}/bin/alembic" ]]; then
        cd "$PROJECT_ROOT"
        "${VENV_DIR}/bin/alembic" upgrade head 2>&1 | tail -5
        cd "$PROJECT_ROOT"
        ok "Database migrations applied."
    else
        warn "alembic not found — skipping migrations."
    fi
fi

# ── Step 8: Start Services ────────────────────────────────────────────────────
echo ""
echo -e "${COLOR_BOLD}[8/8] Starting application servers...${COLOR_RESET}"

# Start backend
info "Starting FastAPI backend..."
PYTHONPATH="$PROJECT_ROOT" uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload \
    --log-level info \
    &
BACKEND_PID=$!
ok "Backend starting (PID: $BACKEND_PID)..."

# Wait for backend health
BACKEND_URL="http://localhost:8000/api/v1/health/live"
if _wait_for_http_ok "$BACKEND_URL" 45; then
    ok "Backend is healthy!"
else
    warn "Backend health check did not return 200 within 45s."
    warn "Check logs for errors. Backend may still be starting."
fi

# Start frontend
if [[ -f "$NODE_REQUIREMENTS" ]]; then
    info "Starting Vite frontend..."
    cd "$FRONTEND_DIR"
    npm run dev &
    FRONTEND_PID=$!
    cd "$PROJECT_ROOT"
    ok "Frontend starting (PID: $FRONTEND_PID)..."
fi

# ═══════════════════════════════════════════════════════════════════════════════
# Print Summary
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${COLOR_BOLD}${COLOR_OK}═══════════════════════════════════════════════════${COLOR_RESET}"
echo -e "${COLOR_BOLD}${COLOR_OK}  Enterprise Hybrid RAG Platform${COLOR_RESET}"
echo -e "${COLOR_BOLD}${COLOR_OK}  Development Environment — READY${COLOR_RESET}"
echo -e "${COLOR_BOLD}${COLOR_OK}═══════════════════════════════════════════════════${COLOR_RESET}"
echo ""
echo -e "  ${COLOR_BOLD}Backend:${COLOR_RESET}"
echo -e "    ${COLOR_INFO}http://localhost:8000${COLOR_RESET}"
echo ""
echo -e "  ${COLOR_BOLD}API Docs:${COLOR_RESET}"
echo -e "    ${COLOR_INFO}http://localhost:8000/docs${COLOR_RESET}"
echo -e "    ${COLOR_INFO}http://localhost:8000/redoc${COLOR_RESET}"
echo ""
echo -e "  ${COLOR_BOLD}Frontend:${COLOR_RESET}"
echo -e "    ${COLOR_INFO}http://localhost:5173${COLOR_RESET}"
echo ""
echo -e "  ${COLOR_DIM}Press Ctrl+C to stop all services.${COLOR_RESET}"
echo -e "  ${COLOR_DIM}Set STOP_DOCKER=true to also stop Docker containers on exit.${COLOR_RESET}"
echo ""
echo -e "${COLOR_BOLD}${COLOR_OK}═══════════════════════════════════════════════════${COLOR_RESET}"
echo ""

# ── Wait for background processes ─────────────────────────────────────────────
# Don't use 'wait' with set -e — it will exit if any background process exits non-zero
set +e
if [[ -n "$FRONTEND_PID" ]]; then
    wait "$FRONTEND_PID" 2>/dev/null
fi
if [[ -n "$BACKEND_PID" ]]; then
    wait "$BACKEND_PID" 2>/dev/null
fi
set -Eeuo pipefail
