#!/bin/bash
# ============================================================
# EC2 Full Deploy Script — AI Songwriting System
# Run once after SSH: bash ec2_deploy.sh
# ============================================================
set -e

PROJECT_DIR="$HOME/AI-Songwriting-System"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend-nextjs"
VENV_DIR="$PROJECT_DIR/venv"
BRANCH="feature/remove-supabase-add-jwt-auth"
BACKEND_SERVICE="ai-songwriting"
FRONTEND_SERVICE="ai-songwriting-frontend"
EC2_IP="3.239.91.199"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠ $1${NC}"; }
fail() { echo -e "${RED}✗ $1${NC}"; exit 1; }

echo "=================================================="
echo " AI Songwriting System — EC2 Deploy"
echo "=================================================="

# ── 1. Pull latest code ───────────────────────────────
echo ""
echo "[1/9] Pulling latest code..."
cd "$PROJECT_DIR" || fail "Project dir not found: $PROJECT_DIR"
git fetch origin
git checkout "$BRANCH"
git pull origin "$BRANCH"
ok "Code up to date on branch: $BRANCH"

# ── 2. Ensure venv exists ─────────────────────────────
echo ""
echo "[2/9] Checking virtual environment..."
if [ ! -d "$VENV_DIR" ]; then
    warn "venv not found — creating one..."
    python3 -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"
ok "venv active: $VENV_DIR"

# ── 3. Install Python dependencies ───────────────────
echo ""
echo "[3/9] Installing Python dependencies..."
pip install --quiet --upgrade pip
pip install --quiet \
    fastapi uvicorn[standard] \
    sqlalchemy \
    python-jose[cryptography] \
    passlib[bcrypt] \
    python-dotenv \
    pydantic[email] \
    email-validator \
    python-multipart
if [ -f "$PROJECT_DIR/requirements.txt" ]; then
    pip install --quiet -r "$PROJECT_DIR/requirements.txt"
fi
ok "All Python dependencies installed"

# ── 4. Ensure .env has JWT_SECRET_KEY ─────────────────
echo ""
echo "[4/9] Checking .env configuration..."
ENV_FILE="$BACKEND_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
    warn ".env not found — creating at $ENV_FILE"
    touch "$ENV_FILE"
fi
if ! grep -q "JWT_SECRET_KEY" "$ENV_FILE"; then
    warn "JWT_SECRET_KEY missing — generating one..."
    JWT_KEY=$(openssl rand -hex 32)
    echo "JWT_SECRET_KEY=$JWT_KEY" >> "$ENV_FILE"
    ok "JWT_SECRET_KEY generated and saved to .env"
else
    ok "JWT_SECRET_KEY already present in .env"
fi

# ── 5. Validate backend imports ───────────────────────
echo ""
echo "[5/9] Validating backend imports..."
cd "$BACKEND_DIR"
python -c "
import sys, os
sys.path.insert(0, os.getcwd())
from database import init_db, get_db
from models import User, Song
from auth import get_password_hash, verify_password, create_access_token
print('Core imports OK')
" || fail "Import validation failed — check the error above before continuing"
ok "All core imports validated"

# ── 6. Start backend via systemd ──────────────────────
echo ""
echo "[6/9] Installing backend systemd service..."
sudo tee /etc/systemd/system/${BACKEND_SERVICE}.service > /dev/null << EOF
[Unit]
Description=AI Songwriting FastAPI Backend
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=${BACKEND_DIR}
Environment="PATH=${VENV_DIR}/bin"
EnvironmentFile=${ENV_FILE}
ExecStart=${VENV_DIR}/bin/uvicorn api:app --host 0.0.0.0 --port 8000 --workers 1
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${BACKEND_SERVICE}

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "$BACKEND_SERVICE"
sudo systemctl stop "$BACKEND_SERVICE" 2>/dev/null || true
sudo systemctl start "$BACKEND_SERVICE"
sleep 3

if sudo systemctl is-active --quiet "$BACKEND_SERVICE"; then
    ok "Backend service is RUNNING on port 8000"
else
    fail "Backend failed to start — run: sudo journalctl -u $BACKEND_SERVICE -n 50"
fi

# ── 7. Install Node.js and build frontend ─────────────
echo ""
echo "[7/9] Setting up frontend (Next.js)..."

# Install Node.js 20 if not present
if ! command -v node &>/dev/null || [[ $(node -v | cut -d. -f1 | tr -d 'v') -lt 18 ]]; then
    warn "Node.js not found or outdated — installing Node.js 20..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt-get install -y nodejs --quiet
fi
ok "Node.js $(node -v) ready"

cd "$FRONTEND_DIR"

# Write .env.local pointing to EC2 backend
cat > .env.local << EOF
NEXT_PUBLIC_API_URL=http://${EC2_IP}:8000
EOF
ok "Frontend .env.local set to http://${EC2_IP}:8000"

# Install npm deps and build
npm install --silent
npm run build
ok "Next.js build complete"

# ── 8. Start frontend via systemd ─────────────────────
echo ""
echo "[8/9] Installing frontend systemd service..."
sudo tee /etc/systemd/system/${FRONTEND_SERVICE}.service > /dev/null << EOF
[Unit]
Description=AI Songwriting Next.js Frontend
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=${FRONTEND_DIR}
Environment="NODE_ENV=production"
Environment="PORT=3000"
ExecStart=$(which npm) start
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${FRONTEND_SERVICE}

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "$FRONTEND_SERVICE"
sudo systemctl stop "$FRONTEND_SERVICE" 2>/dev/null || true
sudo systemctl start "$FRONTEND_SERVICE"
sleep 5

if sudo systemctl is-active --quiet "$FRONTEND_SERVICE"; then
    ok "Frontend service is RUNNING on port 3000"
else
    fail "Frontend failed to start — run: sudo journalctl -u $FRONTEND_SERVICE -n 50"
fi

# ── 9. Final connectivity check ───────────────────────
echo ""
echo "[9/9] Verifying connectivity..."
sleep 2

ss -tlnp | grep -q ':8000' && ok "Backend port 8000 listening" || warn "Backend port 8000 NOT detected"
ss -tlnp | grep -q ':3000' && ok "Frontend port 3000 listening" || warn "Frontend port 3000 NOT detected"

HEALTH=$(curl -s --max-time 5 http://localhost:8000/health || echo "FAILED")
echo "$HEALTH" | grep -q "online" && ok "Backend health: $HEALTH" || warn "Backend health: $HEALTH"

FRONTEND_STATUS=$(curl -s --max-time 5 -o /dev/null -w "%{http_code}" http://localhost:3000 || echo "000")
[ "$FRONTEND_STATUS" = "200" ] && ok "Frontend responding (HTTP $FRONTEND_STATUS)" || warn "Frontend HTTP status: $FRONTEND_STATUS"

echo ""
echo "=================================================="
echo -e "${GREEN} Deploy complete!${NC}"
echo "=================================================="
echo ""
echo "  Backend API:  http://${EC2_IP}:8000"
echo "  API Docs:     http://${EC2_IP}:8000/docs"
echo "  Frontend:     http://${EC2_IP}:3000"
echo ""
echo "Logs:"
echo "  sudo journalctl -u $BACKEND_SERVICE -f"
echo "  sudo journalctl -u $FRONTEND_SERVICE -f"
echo ""
echo -e "${YELLOW}IMPORTANT: Open port 3000 in your AWS Security Group if frontend is unreachable externally.${NC}"
echo -e "${YELLOW}EC2 Console → Security Groups → Inbound Rules → Add TCP 3000 from 0.0.0.0/0${NC}"
echo ""
