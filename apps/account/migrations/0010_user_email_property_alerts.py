# Adds a per-tenant email opt-out for property alerts.
# Default is True (send) so existing users keep the behavior they had
# before this field existed; tenants can opt out from their account
# settings (see apps/account/forms.py / views.py).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('user_account', '0007_remove_user_user_role_tri_end_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='email_property_alerts',
            field=models.BooleanField(
                default=True,
                help_text=(
                    "If True, the tenant receives an email when a new "
                    "property matches one of their saved PropertyAlert "
                    "rows. The in-app notification is always created "
                    "regardless of this flag — the email is the only "
                    "thing this controls."
                ),
            ),
        ),
    ]
