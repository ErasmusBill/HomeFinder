Development: Clearing migrations

This project includes a helper script to clear all Django migrations (dev-only) and recreate fresh ones.

WARNING: This is destructive. It will delete migration files (except __init__.py) and remove db.sqlite3 if present. Do NOT run in production.

To clear migrations and recreate initial migrations locally:

  # make the script executable
  chmod +x scripts/clear_migrations.sh

  # run the script (ensure you have a Python virtualenv and dependencies installed)
  ./scripts/clear_migrations.sh

After running, check the generated migrations, run tests, and verify the app works.
