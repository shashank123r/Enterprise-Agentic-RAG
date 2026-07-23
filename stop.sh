#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# Enterprise Hybrid RAG Platform — Development Environment Stopper
# ═══════════════════════════════════════════════════════════════════════════════
# Gracefully stops frontend, backend, and optionally Docker containers.
# ═══════════════════════════════════════════════════════════════════════════════

set -Eeuo pipefail

# ── Configuration ────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"

DOCKER_COMPOSE_FILE=""
if [[ -f "${PROJECT_ROOT}/docker-compose.yml" ]]; then
    DOCKER_COMPOSE_FILE="${PROJECT_ROOT}/docker-compose.yml"
elif [[ -f "${PROJECT_ROOT}/docker-compose.dev.yml" ]]; then
    DOCKER_COMPOSE_FILE="${PROJECT_ROOT}/docker-compose.dev.yml"
fi

# ── Colors ───────────────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
    COLOR_RESET="\033[0m"
    COLOR_INFO="\033[36m"
    COLOR_OK="\033[32m"
    COLOR_WARN="\033[33m"
    COLOR_ERROR="\033[31m"
    COLOR_BOLD="\033[1m"
else
    COLOR_RESET=""
    COLOR_INFO=""
    COLOR_OK=""
    COLOR_WARN=""
    COLOR_ERROR=""
    COLOR_BOLD=""
fi

# ── Logging ──────────────────────────────────────────────────────────────────
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

# ── Utility ──────────────────────────────────────────────────────────────────
_command_exists() {
    command -v "$1" &>/dev/null
}

# ── Main ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${COLOR_BOLD}${COLOR_INFO}═══════════════════════════════════════════════════${COLOR_RESET}"
echo -e "${COLOR_BOLD}${COLOR_INFO}  Enterprise Hybrid RAG Platform — Shutdown${COLOR_RESET}"
echo -e "${COLOR_BOLD}${COLOR_INFO}═══════════════════════════════════════════════════${COLOR_RESET}"
echo ""

STOPPED_SOMETHING=false

# ── 1. Stop Frontend (Vite) ─────────────────────────────────────────────────
info "Looking for frontend processes..."
FRONTEND_PIDS=$(pgrep -f "node.*vite" 2>/dev/null || true)
if [[ -n "$FRONTEND_PIDS" ]]; then
    echo "$FRONTEND_PIDS" | while read -r pid; do
        kill "$pid" 2>/dev/null && ok "Stopped frontend (PID: $pid)" || true
    done
    STOPPED_SOMETHING=true
else
    info "No frontend processes found."
fi

# ── 2. Stop Backend (Uvicorn) ───────────────────────────────────────────────
info "Looking for backend processes..."
BACKEND_PIDS=$(pgrep -f "uvicorn" 2>/dev/null || true)
if [[ -n "$BACKEND_PIDS" ]]; then
    echo "$BACKEND_PIDS" | while read -r pid; do
        kill "$pid" 2>/dev/null && ok "Stopped backend (PID: $pid)" || true
    done
    STOPPED_SOMETHING=true
else
    info "No backend processes found."
fi

# ── 3. Stop ARQ Workers (if any) ────────────────────────────────────────────
info "Looking for worker processes..."
WORKER_PIDS=$(pgrep -f "arq" 2>/dev/null || true)
if [[ -n "$WORKER_PIDS" ]]; then
    echo "$WORKER_PIDS" | while read -r pid; do
        kill "$pid" 2>/dev/null && ok "Stopped worker (PID: $pid)" || true
    done
    STOPPED_SOMETHING=true
else
    info "No worker processes found."
fi

# ── 4. Stop Other Common Development Processes ──────────────────────────────
for proc_pattern in "celery" "redis-server"; do
    PIDS=$(pgrep -f "$proc_pattern" 2>/dev/null || true)
    if [[ -n "$PIDS" ]]; then
        echo "$PIDS" | while read -r pid; do
            kill "$pid" 2>/dev/null || true
        done
        STOPPED_SOMETHING=true
    fi
done

# ── 5. Stop Docker Services (optional, default: ask) ────────────────────────
if [[ -n "$DOCKER_COMPOSE_FILE" ]] && _command_exists "docker"; then
    echo ""
    info "Docker Compose file found: $(basename "$DOCKER_COMPOSE_FILE")"

    # Check if user wants to stop Docker
    STOP_DOCKER="${STOP_DOCKER:-}"
    if [[ -z "$STOP_DOCKER" ]]; then
        echo ""
        echo -e "${COLOR_WARN}Stop Docker containers as well?${COLOR_RESET}"
        echo -e "  ${COLOR_DIM}(PostgreSQL, Redis, Milvus data will be preserved)${COLOR_RESET}"
        echo -n "  [y/N]: "
        read -r response
        if [[ "$response" =~ ^[Yy]$ ]]; then
            STOP_DOCKER="true"
        else
            STOP_DOCKER="false"
        fi
    fi

    if [[ "$STOP_DOCKER" == "true" ]]; then
        info "Stopping Docker containers..."
        docker compose -f "$DOCKER_COMPOSE_FILE" down 2>&1 | tail -3
        ok "Docker containers stopped."
        STOPPED_SOMETHING=true
    else
        info "Leaving Docker containers running."
    fi
fi

# ── 6. Summary ──────────────────────────────────────────────────────────────
echo ""
if [[ "$STOPPED_SOMETHING" == true ]]; then
    echo -e "${COLOR_BOLD}${COLOR_OK}═══════════════════════════════════════════════════${COLOR_RESET}"
    echo -e "${COLOR_BOLD}${COLOR_OK}  All services stopped successfully.${COLOR_RESET}"
    echo -e "${COLOR_BOLD}${COLOR_OK}═══════════════════════════════════════════════════${COLOR_RESET}"
else
    echo -e "${COLOR_BOLD}${COLOR_WARN}═══════════════════════════════════════════════════${COLOR_RESET}"
    echo -e "${COLOR_BOLD}${COLOR_WARN}  No running services found.${COLOR_RESET}"
    echo -e "${COLOR_BOLD}${COLOR_WARN}═══════════════════════════════════════════════════${COLOR_RESET}"
fi
echo ""

# ── Verify nothing is left on our ports ──────────────────────────────────────
for port in 8000 5173; do
    if _command_exists "lsof"; then
        PID_ON_PORT=$(lsof -ti ":$port" 2>/dev/null || true)
        if [[ -n "$PID_ON_PORT" ]]; then
            warn "Port $port still in use by PID $PID_ON_PORT"
        fi
    fi
done

ok "Shutdown complete."
