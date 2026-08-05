# Changelog for branch improve/settings-templates-20260805

- Fix apps/landlords __init__.py to avoid failing import of non-existent legacy package `apps.landloards`.
- Harden apps.account AppConfig.ready() to catch import errors when loading signals.
- Improve config/settings/base.py:
  - Use BASE_DIR / 'templates' in TEMPLATES['DIRS'].
  - Add SITE_ID and DEFAULT_AUTO_FIELD.
  - Add common template context processors.
  - Add CACHE_TTL default and safer email env defaults.

These changes are intended to make local development more robust and avoid startup crashes when optional legacy packages or environment variables are missing.
