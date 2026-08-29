#!/usr/bin/env bash
# Runs the app in dev mode via Django's dev server (mirrors dev.bat).
# Usage: ./run_dev.sh   (override port with PORT=8080 ./run_dev.sh)
set -euo pipefail

cd "$(dirname "$0")"

if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d ".venv" ]; then
    source .venv/bin/activate
fi

exec python manage.py runserver "${PORT:-8001}"
