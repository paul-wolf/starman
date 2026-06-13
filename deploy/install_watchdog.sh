#!/usr/bin/env bash
# Install the Starman watchdog on a Raspberry Pi.
# Non-interactive — safe to run from the Starvic agent or any automation.
# Only installs the watchdog service; the web UI is not started.
#
# Usage:
#   sudo bash install_watchdog.sh [--repo <github-url>] [--dir <install-dir>] [--user <user>]
#
# Defaults:
#   --repo  https://github.com/paul-wolf/starman
#   --dir   /opt/starman
#   --user  root (runs as the invoking user)

set -euo pipefail

REPO_URL="https://github.com/paul-wolf/starman"
INSTALL_DIR="/opt/starman"
DB_DIR="/var/lib/starman"
DEPLOY_USER="${SUDO_USER:-root}"
SYSTEMD_DIR="/etc/systemd/system"

log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) [starman-install] $*"; }

# ── Parse args ────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --repo)  REPO_URL="$2";    shift 2 ;;
        --dir)   INSTALL_DIR="$2"; shift 2 ;;
        --user)  DEPLOY_USER="$2"; shift 2 ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
done

log "Installing Starman watchdog"
log "  repo:    $REPO_URL"
log "  dir:     $INSTALL_DIR"
log "  user:    $DEPLOY_USER"
log "  db:      $DB_DIR/db.sqlite3"

# ── 1. Clone or update ────────────────────────────────────────────────────────
if [ -d "$INSTALL_DIR/.git" ]; then
    log "Updating existing clone..."
    git -C "$INSTALL_DIR" pull --ff-only
else
    log "Cloning repository..."
    git clone --depth=1 "$REPO_URL" "$INSTALL_DIR"
fi
chown -R "$DEPLOY_USER:$DEPLOY_USER" "$INSTALL_DIR"

# ── 2. Python venv + dependencies ─────────────────────────────────────────────
log "Installing Python dependencies..."
sudo -u "$DEPLOY_USER" python3 -m venv "$INSTALL_DIR/.venv"
sudo -u "$DEPLOY_USER" "$INSTALL_DIR/.venv/bin/pip" install --quiet --upgrade pip
sudo -u "$DEPLOY_USER" "$INSTALL_DIR/.venv/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"

# ── 3. DB directory ───────────────────────────────────────────────────────────
mkdir -p "$DB_DIR"
chown "$DEPLOY_USER:$DEPLOY_USER" "$DB_DIR"

# ── 4. Env file ───────────────────────────────────────────────────────────────
ENV_FILE="$INSTALL_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
    log "Creating .env..."
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(50))")
    cat > "$ENV_FILE" <<EOF
SECRET_KEY=$SECRET_KEY
DEBUG=False
ALLOWED_HOSTS=127.0.0.1,localhost
DB_PATH=$DB_DIR/db.sqlite3
DISH_GRPC_TARGET=192.168.100.1:9200
WATCHDOG_MANUAL_OVERRIDE_GRACE_S=1800
EOF
    chown "$DEPLOY_USER:$DEPLOY_USER" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    log ".env created with generated SECRET_KEY"
else
    # Ensure DB_PATH is set correctly even in existing .env
    if ! grep -q "^DB_PATH=" "$ENV_FILE"; then
        echo "DB_PATH=$DB_DIR/db.sqlite3" >> "$ENV_FILE"
        log "DB_PATH added to existing .env"
    fi
fi

# ── 5. Django setup ───────────────────────────────────────────────────────────
log "Running migrations..."
sudo -u "$DEPLOY_USER" "$INSTALL_DIR/.venv/bin/python" "$INSTALL_DIR/manage.py" migrate --noinput

# ── 6. Systemd watchdog unit ──────────────────────────────────────────────────
log "Installing systemd watchdog unit..."
sed "s|/home/pi/starman|$INSTALL_DIR|g; s|User=pi|User=$DEPLOY_USER|g; s|Group=pi|Group=$DEPLOY_USER|g" \
    "$INSTALL_DIR/deploy/starman-watchdog.service" > "$SYSTEMD_DIR/starman-watchdog.service"

systemctl daemon-reload
systemctl enable --now starman-watchdog.service

log ""
log "Starman watchdog installed and started."
log "  Status:  systemctl status starman-watchdog"
log "  Logs:    journalctl -u starman-watchdog -f"
log "  DB:      $DB_DIR/db.sqlite3"
log ""
log "Watchdog starts in LOG_ONLY mode — it observes but does not touch GPS."
log "To enable active GPS management, change mode via the Starman web UI or admin."
