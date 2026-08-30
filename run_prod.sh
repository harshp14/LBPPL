#!/usr/bin/env bash
# Runs the app in production mode via Gunicorn.
# Usage: ./run_prod.sh   (override port with PORT=8080 ./run_prod.sh)
set -euo pipefail

cd "$(dirname "$0")"

if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d ".venv" ]; then
    source .venv/bin/activate
fi

export DJANGO_DEBUG=False

python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec gunicorn draftleague.wsgi:application \
    --workers 2 \
    --bind "0.0.0.0:${PORT:-8000}"
