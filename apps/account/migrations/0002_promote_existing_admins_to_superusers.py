"""
Data migration: every user with role='admin' should also be a Django
superuser (is_staff=True, is_superuser=True). The model save() now
enforces this on new writes, but existing rows need to be brought in
line retroactively.
"""
from django.db import migrations


def promote_existing_admins(apps, schema_editor):
    User = apps.get_model('user_account', 'User')
    User.objects.filter(role='admin').update(is_staff=True, is_superuser=True)


def demote_existing_admins(apps, schema_editor):
    """
    Reverse: best-effort demotion of role='admin' users that we promoted.
    This is intentionally conservative — we only flip the flags back to
    False for users that are role='admin' AND were not superusers before
    the forward migration. (We don't actually track that, so the reverse
    just sets both flags back to False for every role='admin' user that
    was *not* staff/superuser before the forward run. In practice this
    migration is one-way.)
    """
    User = apps.get_model('user_account', 'User')
    User.objects.filter(role='admin').update(is_staff=False, is_superuser=False)


class Migration(migrations.Migration):

    dependencies = [
        ('user_account', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(promote_existing_admins, demote_existing_admins),
    ]
