#!/usr/bin/env bash
# Deploy starman on a Raspberry Pi.
# Run as root (sudo ./install.sh) from the project directory.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DEPLOY_USER="${DEPLOY_USER:-pi}"
INSTALL_DIR="${INSTALL_DIR:-/home/${DEPLOY_USER}/starman}"
SYSTEMD_DIR="/etc/systemd/system"

echo "Project source : $PROJECT_DIR"
echo "Install target : $INSTALL_DIR"
echo "Service user   : $DEPLOY_USER"
echo ""
read -rp "Continue? [y/N] " confirm
[[ "$confirm" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 1; }

# ── 1. Copy project files ─────────────────────────────────────────────────────
echo ""
echo "Syncing project files..."
rsync -a --exclude='.git' --exclude='.venv' --exclude='db.sqlite3' \
      --exclude='frontend/node_modules' --exclude='staticfiles' \
      "$PROJECT_DIR/" "$INSTALL_DIR/"
chown -R "$DEPLOY_USER:$DEPLOY_USER" "$INSTALL_DIR"

# ── 2. Python venv + dependencies ─────────────────────────────────────────────
echo "Installing Python dependencies..."
sudo -u "$DEPLOY_USER" python3 -m venv "$INSTALL_DIR/.venv"
sudo -u "$DEPLOY_USER" "$INSTALL_DIR/.venv/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"

# ── 3. DB directory ───────────────────────────────────────────────────────────
mkdir -p /var/lib/starman
chown "$DEPLOY_USER:$DEPLOY_USER" /var/lib/starman

# ── 4. Env file ──────────────────────────────────────────────────────────────
if [ ! -f "$INSTALL_DIR/.env" ]; then
    echo "Creating .env from .env.example — edit it before starting services."
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
    chown "$DEPLOY_USER:$DEPLOY_USER" "$INSTALL_DIR/.env"
    chmod 600 "$INSTALL_DIR/.env"
fi

# ── 5. Django setup ───────────────────────────────────────────────────────────
echo "Running migrations..."
sudo -u "$DEPLOY_USER" "$INSTALL_DIR/.venv/bin/python" "$INSTALL_DIR/manage.py" migrate --noinput

echo "Collecting static files..."
sudo -u "$DEPLOY_USER" "$INSTALL_DIR/.venv/bin/python" "$INSTALL_DIR/manage.py" collectstatic --noinput

# ── 6. Systemd units ──────────────────────────────────────────────────────────
echo "Installing systemd units..."

for unit in starman-web.service starman-watchdog.service starman-retain.service starman-retain.timer; do
    src="$INSTALL_DIR/deploy/$unit"
    dest="$SYSTEMD_DIR/$unit"
    # Substitute DEPLOY_USER and INSTALL_DIR placeholders
    sed "s|/home/pi/starman|$INSTALL_DIR|g; s|User=pi|User=$DEPLOY_USER|g; s|Group=pi|Group=$DEPLOY_USER|g" \
        "$src" > "$dest"
    echo "  Installed $dest"
done

systemctl daemon-reload

systemctl enable --now starman-watchdog.service
systemctl enable --now starman-web.service
systemctl enable --now starman-retain.timer

echo ""
echo "Done. Check status with:"
echo "  systemctl status starman-web starman-watchdog"
echo "  journalctl -u starman-watchdog -f"
echo ""
echo "Remember to:"
echo "  1. Edit $INSTALL_DIR/.env (set SECRET_KEY, ALLOWED_HOSTS, DEBUG=False)"
echo "  2. Create a superuser: sudo -u $DEPLOY_USER $INSTALL_DIR/.venv/bin/python $INSTALL_DIR/manage.py createsuperuser"
echo "  3. Verify dish routing: ping 192.168.100.1 from the Pi"
