#!/usr/bin/env bash
set -euo pipefail

# clear_migrations.sh
# DANGER: This deletes migration files and the local SQLite DB (if present).
# Use only in development. Backup any data you need before running.

ROOT_DIR=$(dirname "$0")/..
cd "$ROOT_DIR"

echo "=> Removing migration files (keeps __init__.py)"
find . -path "*/migrations/*.py" ! -name "__init__.py" -print -exec rm -v {} \;
find . -path "*/migrations/*.pyc" -print -exec rm -v {} \;

echo "=> Removing migration folders' __pycache__"
find . -path "*/migrations/__pycache__" -print -exec rm -rf {} \;

# Remove sqlite db if exists
if [ -f db.sqlite3 ]; then
  echo "=> Removing local SQLite database db.sqlite3"
  rm -v db.sqlite3
fi

# Optional: remove Django's compiled files
find . -name "*.pyc" -print -exec rm -v {} \;
find . -name "__pycache__" -print -exec rm -rf {} \;

echo "=> Recreating initial migrations (run in virtualenv with deps installed)"
python -m venv .venv || true
source .venv/bin/activate || true
pip install -U pip || true
# You should install project dependencies here (pip install -r requirements.txt) before running manage.py
# Run makemigrations to create fresh initial migrations
python manage.py makemigrations --noinput || true
python manage.py migrate --noinput || true

echo "=> Done. Please run tests and verify everything locally." 
