#!/bin/sh
set -e

echo "==> Running database migrations..."
python manage.py migrate --noinput

# Only collect static files when starting the web server (gunicorn)
# Celery workers don't need static files and don't have write access to the volume
if echo "$@" | grep -q "gunicorn"; then
    echo "==> Collecting static files..."
    python manage.py collectstatic --noinput
fi

echo "==> Starting $@..."
exec "$@"
