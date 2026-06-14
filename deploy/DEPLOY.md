# Deploying Starman on a Raspberry Pi

## Prerequisites

- Raspberry Pi (3B+ or later) running Raspberry Pi OS (Bookworm recommended)
- Python 3.11+ on the Pi (`python3 --version`)
- Node.js on your **dev machine** to build the frontend (not needed on the Pi)
- The Pi must be able to reach `192.168.100.1` — verify with `ping 192.168.100.1` from the Pi before proceeding (see [Dish Routing](#dish-routing) below)

---

## 1. Build the frontend (on your dev machine)

The Pi does not need Node.js. Build the static bundle once before deploying:

```bash
cd frontend
npm install
npm run build
cd ..
```

This produces `frontend/dist/` which `install.sh` will sync to the Pi and `collectstatic` will pick up.

---

## 2. Deploy to the Pi

`frontend/dist/` is gitignored, so **do not clone on the Pi** — the built frontend won't be there. The only supported path is rsync from your dev machine after building.

```bash
# On your dev machine (after step 1)
rsync -avz --exclude='.git' --exclude='.venv' --exclude='frontend/node_modules' --exclude='db.sqlite3' \
    ./ pi@<pi-ip>:/home/pi/starman/
ssh pi@<pi-ip> "cd /home/pi/starman && sudo bash deploy/install.sh"
```

`install.sh` defaults to `DEPLOY_USER=pi` and `INSTALL_DIR=/home/pi/starman`. Override if needed:

```bash
ssh pi@<pi-ip> "cd /home/pi/starman && sudo DEPLOY_USER=myuser INSTALL_DIR=/opt/starman bash deploy/install.sh"
```

---

## 3. Configure the environment

The install script creates `.env` from `.env.example` if it doesn't exist. Edit it before starting the services:

```bash
nano /home/pi/starman/.env
```

Minimum changes for production:

```bash
SECRET_KEY=<a long random string>
DEBUG=False
ALLOWED_HOSTS=<pi-hostname-or-ip>,localhost
DISH_GRPC_TARGET=192.168.100.1:9200
```

Generate a secret key:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

---

## 4. Create a superuser

```bash
sudo -u pi /home/pi/starman/.venv/bin/python /home/pi/starman/manage.py createsuperuser
```

---

## 5. Start the services

`install.sh` enables and starts everything automatically. To verify:

```bash
systemctl status starman-web starman-watchdog
```

To check live logs:

```bash
journalctl -u starman-watchdog -f
journalctl -u starman-web -f
```

The web console will be available at `http://<pi-ip>:8000`.

---

## Watchdog-only install

If you only need the GPS watchdog (no web UI), use `install_watchdog.sh`. This is the script the Starvic agent runs when you click **Queue Starman install** from the Nodes page.

```bash
curl -fsSL https://raw.githubusercontent.com/paul-wolf/starman/main/deploy/install_watchdog.sh | sudo bash
```

Or clone first and run locally:

```bash
git clone --depth=1 https://github.com/paul-wolf/starman.git /tmp/starman
sudo bash /tmp/starman/deploy/install_watchdog.sh
```

### Options

| Flag | Default | Description |
|---|---|---|
| `--repo <url>` | `https://github.com/paul-wolf/starman` | Git repo to clone |
| `--dir <path>` | `/opt/starman` | Install directory |
| `--user <name>` | `$SUDO_USER` or `root` | OS user to own files and run the service |

Example with overrides:

```bash
sudo bash install_watchdog.sh --dir /srv/starman --user myuser
```

### What it does

1. Clones (or `git pull`s) the repo to `--dir`
2. Creates a Python venv and installs `requirements.txt`
3. Creates `/var/lib/starman/` and writes the SQLite DB there
4. Generates a `.env` with a random `SECRET_KEY` and sane defaults (only if `.env` doesn't exist):
   ```
   SECRET_KEY=<generated>
   DEBUG=False
   ALLOWED_HOSTS=127.0.0.1,localhost
   DB_PATH=/var/lib/starman/db.sqlite3
   DISH_GRPC_TARGET=192.168.100.1:9200
   WATCHDOG_MANUAL_OVERRIDE_GRACE_S=1800
   ```
5. Runs `manage.py migrate`
6. Installs, enables, and starts `starman-watchdog.service`

After install, the watchdog runs in `LOG_ONLY` mode — see [Watchdog modes](#watchdog-modes).

```bash
systemctl status starman-watchdog
journalctl -u starman-watchdog -f
```

### Remote install via Starvic

If the Pi is already running the Starvic agent, you can trigger the watchdog install remotely from the Starvic web UI:

1. Open **Nodes** in the Starvic UI.
2. Find the Pi and click **Queue Starman install** (staff only).
3. On the next agent poll the Pi downloads `install_watchdog.sh` from GitHub and runs it as root.
4. Watch progress in the agent logs: `journalctl -u starvic-agent -f` on the Pi.

---

## Dish routing

The Pi must have a route to `192.168.100.1` (the Starlink dish's local IP). Verify with:

```bash
ping 192.168.100.1
```

If it fails, two options:

**Option A — Static route (simpler):** The Pi reaches the dish via the same router your Mac uses. Add a persistent static route:

```bash
# Test it first (non-persistent)
sudo ip route add 192.168.100.0/24 via <router-ip>

# Make it persistent via /etc/network/interfaces or systemd-networkd:
# In /etc/network/interfaces, add under your interface:
#   up ip route add 192.168.100.0/24 via <router-ip>
```

**Option B — Direct connection (more reliable):** Connect the Pi directly to the Starlink dish's LAN port (or a switch on that subnet) using a second network interface. Assign the Pi a static address in `192.168.100.x/24`.

---

## Service management

| Task | Command |
|---|---|
| Start all | `systemctl start starman-web starman-watchdog` |
| Stop all | `systemctl stop starman-web starman-watchdog` |
| Restart web | `systemctl restart starman-web` |
| Restart watchdog | `systemctl restart starman-watchdog` |
| Web logs | `journalctl -u starman-web -f` |
| Watchdog logs | `journalctl -u starman-watchdog -f` |
| Retention logs | `journalctl -u starman-retain` |
| Run retention now | `systemctl start starman-retain` |

---

## Telemetry retention

A systemd timer runs `manage.py retain_telemetry` daily at 03:00 UTC. Default tiers:

| Age | Kept |
|---|---|
| < 7 days | Every poll (raw) |
| 7 – 30 days | 1 row per minute |
| 30 days – 1 year | 1 row per hour |
| > 1 year | Deleted |

Run manually with a dry run to check what would be removed:

```bash
sudo -u pi /home/pi/starman/.venv/bin/python /home/pi/starman/manage.py retain_telemetry --dry-run
```

Adjust tiers:

```bash
manage.py retain_telemetry --raw-days 14 --minute-days 60 --hour-days 730
```

---

## Updating

Because `frontend/dist/` is gitignored, updates always go via rsync from your dev machine:

```bash
# On your dev machine
cd frontend && npm run build && cd ..
rsync -avz --exclude='.git' --exclude='.venv' --exclude='frontend/node_modules' --exclude='db.sqlite3' \
    ./ pi@<pi-ip>:/home/pi/starman/

# Then on the Pi
ssh pi@<pi-ip> "
  cd /home/pi/starman
  .venv/bin/pip install -r requirements.txt
  .venv/bin/python manage.py migrate --noinput
  .venv/bin/python manage.py collectstatic --noinput
  sudo systemctl restart starman-web starman-watchdog
"
```

If only Python code changed (no frontend, no new dependencies, no migrations), you can skip the build and rsync just the Python files.

---

## Watchdog modes

The watchdog starts in `LOG_ONLY` mode — it records what it *would* do but never touches the GPS inhibit flag. Switch modes from the web console Controls panel or via the admin.

| Mode | Behaviour |
|---|---|
| `LOG_ONLY` | Observe only. Run here first for a few days to learn the jamming pattern. |
| `MONITOR` | Same as LOG_ONLY (reserved for future alerting). |
| `ENFORCE` | Actively inhibits/clears GPS based on debounce thresholds. |
