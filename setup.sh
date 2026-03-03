#!/usr/bin/env bash
# =============================================================================
# Clawdbot — One-Command Setup
# Usage:
#   ./setup.sh            — full setup (installs deps, copies .env, prints next steps)
#   ./setup.sh --wizard   — full setup + interactive credential wizard
#   ./setup.sh --check    — dry run: verify prerequisites only, no changes
# =============================================================================
set -euo pipefail

# ---- colour helpers ---------------------------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BOLD='\033[1m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[ok]${NC}  $*"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*"; }
err()  { echo -e "${RED}[error]${NC} $*" >&2; }
step() { echo -e "\n${BOLD}==> $*${NC}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRY_RUN=false
WIZARD=false

for arg in "$@"; do
  case "$arg" in
    --check)  DRY_RUN=true ;;
    --wizard) WIZARD=true  ;;
    --help|-h)
      echo "Usage: ./setup.sh [--wizard] [--check]"
      echo "  --wizard  Interactive credential wizard (fills in .env)"
      echo "  --check   Dry run — verify prerequisites only, make no changes"
      exit 0
      ;;
  esac
done

# ---- Step 1: prerequisites --------------------------------------------------
step "Checking prerequisites"

check_python() {
  if ! command -v python3 &>/dev/null; then
    err "python3 not found. Install Python 3.11+ from https://python.org"
    exit 1
  fi
  PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
  PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
  PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
  if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 11 ]; }; then
    err "Python 3.11+ required (found $PY_VERSION). Install from https://python.org"
    exit 1
  fi
  ok "Python $PY_VERSION"
}

check_docker() {
  if ! command -v docker &>/dev/null; then
    warn "Docker not found — Postgres will NOT be started automatically."
    warn "Install Docker from https://docs.docker.com/get-docker/ or run Postgres manually."
    DOCKER_AVAILABLE=false
  else
    ok "Docker $(docker --version | awk '{print $3}' | tr -d ',')"
    DOCKER_AVAILABLE=true
  fi
}

check_pip() {
  if ! python3 -m pip --version &>/dev/null; then
    err "pip not found. Run: python3 -m ensurepip --upgrade"
    exit 1
  fi
  ok "pip $(python3 -m pip --version | awk '{print $2}')"
}

check_python
check_docker
check_pip

if $DRY_RUN; then
  echo ""
  ok "Dry run complete — all prerequisites satisfied."
  exit 0
fi

# ---- Step 2: install packages -----------------------------------------------
step "Installing Python packages (editable)"
cd "$SCRIPT_DIR"

python3 -m pip install --quiet -e packages/core \
                                 -e packages/connectors \
                                 -e packages/cli \
                                 -e apps/worker \
                                 -e apps/bot
ok "All packages installed"

# ---- Step 3: copy .env.example → .env --------------------------------------
step "Configuring .env"
if [ -f "$SCRIPT_DIR/.env" ]; then
  ok ".env already exists — skipping copy (edit it manually if needed)"
else
  cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
  ok "Copied .env.example → .env"
fi

# ---- Step 4: optional wizard ------------------------------------------------
if $WIZARD; then
  step "Running interactive setup wizard"
  python3 "$SCRIPT_DIR/setup_wizard.py"
fi

# ---- Step 5: start Postgres via Docker Compose ------------------------------
if $DOCKER_AVAILABLE; then
  step "Starting Postgres"
  cd "$SCRIPT_DIR/infra"
  docker compose up -d db
  # wait up to 30s for Postgres to be ready
  echo -n "  Waiting for Postgres"
  for i in $(seq 1 30); do
    if docker compose exec -T db pg_isready -U clawdbot &>/dev/null; then
      echo ""
      ok "Postgres ready"
      break
    fi
    echo -n "."
    sleep 1
  done
  cd "$SCRIPT_DIR"
else
  warn "Skipping Postgres start — Docker not available."
  warn "Make sure Postgres is running and DATABASE_URL in .env is correct."
fi

# ---- Step 6: run migrations -------------------------------------------------
step "Running database migrations"
cd "$SCRIPT_DIR/infra"
python3 -m alembic upgrade head
ok "Migrations complete"
cd "$SCRIPT_DIR"

# ---- Step 7: create default user --------------------------------------------
step "Initialising default user"
claw init || warn "claw init failed — user may already exist, continuing."
ok "Default user ready"

# ---- Step 8: verify system --------------------------------------------------
step "Verifying setup"
claw status || warn "claw status returned non-zero — check .env credentials."

# ---- Done -------------------------------------------------------------------
echo ""
echo -e "${GREEN}${BOLD}================================================================${NC}"
echo -e "${GREEN}${BOLD}  Setup complete!${NC}"
echo -e "${GREEN}${BOLD}================================================================${NC}"
echo ""
echo "  Next steps:"
echo "  1. Edit .env — fill in GEMINI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID"
echo "  2. Connect your accounts:"
echo "       claw connect gmail       # opens browser OAuth"
echo "       claw connect gcal        # optional: Google Calendar"
echo "       claw connect outlook     # optional: NUS/Outlook"
echo "  3. Start the bot and worker:"
echo "       claw worker start"
echo ""
echo "  Tip: run './setup.sh --wizard' to fill in credentials interactively."
echo ""
