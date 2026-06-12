#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -d .venv ]; then
  echo "No .venv found. Run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

PORT=$(python3 -c "
import socket, random, sys
random.seed()
ports = list(range(8700, 8800))
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

echo "BACKEND_PORT=$PORT" > .dev-ports

echo ""
echo "  Django dev server"
echo "  ─────────────────────────────────────"
echo "  App:     http://127.0.0.1:$PORT/"
echo "  Admin:   http://127.0.0.1:$PORT/admin/"
echo "  API:     http://127.0.0.1:$PORT/api/docs"
echo "  ─────────────────────────────────────"
echo ""

exec .venv/bin/python manage.py runserver "127.0.0.1:$PORT"
