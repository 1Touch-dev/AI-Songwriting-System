#!/bin/bash
# ============================================================
# EC2 Full Deploy Script — AI Songwriting System
# Run once after SSH: bash ec2_deploy.sh
# ============================================================
set -e

PROJECT_DIR="$HOME/AI-Songwriting-System"
BACKEND_DIR="$PROJECT_DIR/backend"
VENV_DIR="$PROJECT_DIR/venv"
BRANCH="feature/remove-supabase-add-jwt-auth"
SERVICE_NAME="ai-songwriting"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠ $1${NC}"; }
fail() { echo -e "${RED}✗ $1${NC}"; exit 1; }

echo "=================================================="
echo " AI Songwriting System — EC2 Deploy"
echo "=================================================="

# ── 1. Pull latest code ───────────────────────────────
echo ""
echo "[1/7] Pulling latest code..."
cd "$PROJECT_DIR" || fail "Project dir not found: $PROJECT_DIR"
git fetch origin
git checkout "$BRANCH"
git pull origin "$BRANCH"
ok "Code up to date on branch: $BRANCH"

# ── 2. Ensure venv exists ─────────────────────────────
echo ""
echo "[2/7] Checking virtual environment..."
if [ ! -d "$VENV_DIR" ]; then
    warn "venv not found — creating one..."
    python3 -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"
ok "venv active: $VENV_DIR"

# ── 3. Install all dependencies ───────────────────────
echo ""
echo "[3/7] Installing dependencies..."
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
# Install project requirements if they exist
if [ -f "$PROJECT_DIR/requirements.txt" ]; then
    pip install --quiet -r "$PROJECT_DIR/requirements.txt"
fi
ok "All dependencies installed"

# ── 4. Ensure .env has JWT_SECRET_KEY ─────────────────
echo ""
echo "[4/7] Checking .env configuration..."
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

# ── 5. Validate imports don't crash ───────────────────
echo ""
echo "[5/7] Validating backend imports..."
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

# ── 6. Create and enable systemd service ──────────────
echo ""
echo "[6/7] Installing systemd service..."
sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null << EOF
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
SyslogIdentifier=${SERVICE_NAME}

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"

# Stop old instance if running
sudo systemctl stop "$SERVICE_NAME" 2>/dev/null || true

sudo systemctl start "$SERVICE_NAME"
sleep 3

if sudo systemctl is-active --quiet "$SERVICE_NAME"; then
    ok "systemd service is RUNNING"
else
    fail "Service failed to start — run: sudo journalctl -u $SERVICE_NAME -n 50"
fi

# ── 7. Verify port and connectivity ───────────────────
echo ""
echo "[7/7] Verifying connectivity..."
sleep 2

if ss -tlnp | grep -q ':8000'; then
    ok "Port 8000 is OPEN and listening"
else
    warn "Port 8000 not detected yet — checking logs..."
    sudo journalctl -u "$SERVICE_NAME" -n 30 --no-pager
    fail "Port 8000 not listening — see logs above"
fi

HEALTH=$(curl -s --max-time 5 http://localhost:8000/health || echo "FAILED")
if echo "$HEALTH" | grep -q "online"; then
    ok "Health check passed: $HEALTH"
else
    warn "Health endpoint response: $HEALTH"
    warn "App may still be loading the pipeline — check logs with:"
    echo "  sudo journalctl -u $SERVICE_NAME -f"
fi

echo ""
echo "=================================================="
echo -e "${GREEN} Deploy complete!${NC}"
echo "=================================================="
echo ""
echo "Useful commands:"
echo "  Live logs:    sudo journalctl -u $SERVICE_NAME -f"
echo "  Status:       sudo systemctl status $SERVICE_NAME"
echo "  Restart:      sudo systemctl restart $SERVICE_NAME"
echo "  Health check: curl http://localhost:8000/health"
echo ""
echo -e "${YELLOW}IMPORTANT: If external access (http://3.239.91.199:8000) is still blocked,${NC}"
echo -e "${YELLOW}open port 8000 in your AWS Security Group (EC2 Console → Security Groups → Inbound Rules).${NC}"
echo ""
