#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -d frontend ]; then
  echo "No frontend/ directory found. Frontend not scaffolded yet."
  exit 1
fi

if [ ! -f frontend/node_modules/.package-lock.json ] && [ ! -d frontend/node_modules ]; then
  echo "node_modules missing. Run: cd frontend && npm install"
  exit 1
fi

# Resolve backend port: .dev-ports file, then BACKEND_PORT env var, then default
BACKEND_PORT="${BACKEND_PORT:-}"
if [ -z "$BACKEND_PORT" ] && [ -f .dev-ports ]; then
  # shellcheck disable=SC1091
  source .dev-ports
fi
BACKEND_PORT="${BACKEND_PORT:-8700}"

PORT=$(python3 -c "
import socket, random, sys
random.seed()
ports = list(range(5800, 5900))
random.shuffle(ports)
for p in ports:
    try:
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        s.bind(('127.0.0.1', p))
        s.close()
        print(p)
        sys.exit(0)
    except OSError:
        pass
sys.exit(1)
")

echo ""
echo "  Vite dev server"
echo "  ─────────────────────────────────────"
echo "  Frontend: http://localhost:$PORT/"
echo "  Proxying /api -> http://127.0.0.1:$BACKEND_PORT"
echo "  ─────────────────────────────────────"
echo ""

cd frontend
export BACKEND_PORT
exec npx vite --port "$PORT" --strictPort
