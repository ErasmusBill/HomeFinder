# Compatibility shim: re-export the legacy package if present (typo 'landloards').
# Keep imports guarded so Django startup doesn't fail if the legacy package isn't present.
try:
    from apps.landloards import *  # noqa: F401,F403
except Exception:  # pragma: no cover - defensive: don't raise on import problems
    # Legacy misspelled package not present or failed to import. Nothing to re-export.
    __all__ = []
