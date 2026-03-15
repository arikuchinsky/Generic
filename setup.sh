#!/bin/bash
set -e

# ─── Colors ───────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info()  { echo -e "${BLUE}[info]${NC}  $1"; }
ok()    { echo -e "${GREEN}[ok]${NC}    $1"; }
warn()  { echo -e "${YELLOW}[warn]${NC}  $1"; }
fail()  { echo -e "${RED}[error]${NC} $1"; exit 1; }

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo -e "${BLUE}══════════════════════════════════════════${NC}"
echo -e "${BLUE}  Claude Code Web Wrapper — Setup & Launch${NC}"
echo -e "${BLUE}══════════════════════════════════════════${NC}"
echo ""

# ─── 1. Homebrew ──────────────────────────────────────────────────────
if command -v brew &>/dev/null; then
    ok "Homebrew found"
else
    info "Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    # Add brew to PATH for the rest of this script
    if [[ -f /opt/homebrew/bin/brew ]]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    elif [[ -f /usr/local/bin/brew ]]; then
        eval "$(/usr/local/bin/brew shellenv)"
    fi
    ok "Homebrew installed"
fi

# ─── 2. Python 3.10+ ─────────────────────────────────────────────────
check_python() {
    local py="$1"
    if command -v "$py" &>/dev/null; then
        local ver
        ver=$("$py" -c 'import sys; print(sys.version_info.minor)' 2>/dev/null)
        local major
        major=$("$py" -c 'import sys; print(sys.version_info.major)' 2>/dev/null)
        if [[ "$major" == "3" && "$ver" -ge 10 ]]; then
            echo "$py"
            return 0
        fi
    fi
    return 1
}

PYTHON=""
for candidate in python3.12 python3.11 python3.10 python3; do
    if PYTHON=$(check_python "$candidate"); then
        break
    fi
    PYTHON=""
done

if [[ -n "$PYTHON" ]]; then
    ok "Python found: $($PYTHON --version)"
else
    info "Installing Python 3.12 via Homebrew..."
    brew install python@3.12
    PYTHON=$(check_python python3.12) || PYTHON=$(check_python python3)
    [[ -n "$PYTHON" ]] || fail "Python installation failed. Please install Python 3.10+ manually."
    ok "Python installed: $($PYTHON --version)"
fi

# ─── 3. Node.js 18+ ──────────────────────────────────────────────────
if command -v node &>/dev/null; then
    NODE_VER=$(node -e 'console.log(process.versions.node.split(".")[0])')
    if [[ "$NODE_VER" -ge 18 ]]; then
        ok "Node.js found: v$(node --version | tr -d 'v')"
    else
        info "Node.js $NODE_VER is too old (need 18+). Upgrading via Homebrew..."
        brew install node
        ok "Node.js upgraded: v$(node --version | tr -d 'v')"
    fi
else
    info "Installing Node.js via Homebrew..."
    brew install node
    ok "Node.js installed: v$(node --version | tr -d 'v')"
fi

# ─── 4. Claude Code CLI ──────────────────────────────────────────────
if command -v claude &>/dev/null; then
    ok "Claude Code CLI found"
else
    info "Installing Claude Code CLI..."
    npm install -g @anthropic-ai/claude-code
    command -v claude &>/dev/null || fail "Claude CLI installation failed. Run: npm install -g @anthropic-ai/claude-code"
    ok "Claude Code CLI installed"
fi

# ─── 5. Verify Claude is authenticated ───────────────────────────────
info "Checking Claude CLI authentication..."
if claude --version &>/dev/null; then
    ok "Claude CLI is responsive"
    warn "Make sure you have authenticated: run 'claude' in your terminal if you haven't already."
else
    warn "Could not verify Claude CLI. You may need to run 'claude' once to authenticate."
fi

# ─── 6. Python virtual environment ───────────────────────────────────
VENV_DIR="$ROOT_DIR/backend/.venv"
if [[ -d "$VENV_DIR" ]]; then
    ok "Python venv exists"
else
    info "Creating Python virtual environment..."
    $PYTHON -m venv "$VENV_DIR"
    ok "Python venv created"
fi
source "$VENV_DIR/bin/activate"
ok "Python venv activated"

# ─── 7. Install Python dependencies ──────────────────────────────────
info "Installing Python dependencies..."
pip install -q -r "$ROOT_DIR/backend/requirements.txt"
ok "Python dependencies installed"

# ─── 8. Install Node dependencies ────────────────────────────────────
info "Installing Node dependencies..."
cd "$ROOT_DIR/frontend"
npm install --silent 2>/dev/null
ok "Node dependencies installed"

# ─── 9. Launch servers ───────────────────────────────────────────────
echo ""
echo -e "${GREEN}══════════════════════════════════════════${NC}"
echo -e "${GREEN}  Starting servers...${NC}"
echo -e "${GREEN}══════════════════════════════════════════${NC}"
echo ""
echo -e "  Backend:  ${BLUE}http://localhost:8000${NC}"
echo -e "  Frontend: ${BLUE}http://localhost:5173${NC}"
echo ""
echo -e "  Press ${YELLOW}Ctrl+C${NC} to stop both servers."
echo ""

cd "$ROOT_DIR/backend"
uvicorn main:app --reload --port 8000 &
BACKEND_PID=$!

cd "$ROOT_DIR/frontend"
npm run dev &
FRONTEND_PID=$!

# ─── 10. Open browser after a short delay ────────────────────────────
(
    sleep 3
    if command -v open &>/dev/null; then
        open "http://localhost:5173"
    fi
) &

# ─── 11. Clean shutdown ──────────────────────────────────────────────
cleanup() {
    echo ""
    info "Shutting down servers..."
    kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null
    wait "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null
    ok "Servers stopped. Goodbye!"
}
trap cleanup EXIT INT TERM

wait
