# HomeFinder

Basic instructions to run the HomeFinder Django project locally and in Docker.

Prerequisites:
- Python 3.10+ (3.12 is used in the Dockerfile)
- Docker (optional, for containerized runs)

Quick local setup:

1. Create and activate a virtualenv

   python -m venv .venv
   source .venv/bin/activate

2. Install dependencies

   # If you use the included lock tooling (uv), follow the project's workflow.
   # Otherwise, install with pip:
   pip install -r requirements.txt

3. Provide environment variables (create a .env at the repo root). At minimum set:
   SECRET_KEY (a Django secret)
   DEBUG (True/False)

4. Run migrations and start the dev server

   export DJANGO_SETTINGS_MODULE=config.settings.local
   python manage.py migrate
   python manage.py runserver

Run with Docker:

  docker build -t homefinder .
  docker run -e DJANGO_SETTINGS_MODULE=config.settings.prod -p 8000:8000 homefinder

Notes:
- The Dockerfile expects the project's WSGI module at config.wsgi and the settings modules under config/settings/.
- If you use uv/uv.lock tooling for dependency management, ensure the lockfile is up-to-date before building.
