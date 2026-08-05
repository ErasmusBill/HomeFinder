# Compatibility shim: re-export the legacy package so both dotted paths work.
# This allows leaving existing files under apps/landloards in place while
# making the app available as apps.landlords to match INSTALLED_APPS.
from apps.landloards import *  # noqa: F401,F403
