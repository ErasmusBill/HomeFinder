"""
Settings package entry point.

We auto-pick between `base` and `prod` based on the `DJANGO_ENV`
environment variable (defaults to "base" for local development).

Set `DJANGO_ENV=production` on your hosting provider (Railway, Heroku,
Render, etc.) so the stricter security settings in `prod.py` take effect.

Why this exists:
  - `base.py` reads `DEBUG` from `.env`, which is fine for local dev but
    dangerous in production (the `.env` shipped to production had DEBUG=True).
  - `prod.py` forces `DEBUG=False`, enables HTTPS headers, sets
    `SECURE_SSL_REDIRECT`, and tightens `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS`.
  - Without this switch, `prod.py` was dead code and production was
    actually running `base.py` settings.
"""
import os

_env = os.environ.get("DJANGO_ENV", "base").lower()

if _env in ("production", "prod"):
    from .prod import *  # noqa: F401,F403
else:
    from .base import *  # noqa: F401,F403
