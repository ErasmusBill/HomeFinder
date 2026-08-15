"""
Add free-trial window columns to the User model.

Two new nullable DateTimeFields:
  - trial_start_date: when the landlord's free trial started
  - trial_end_date:   when it ends (start + 30 days, set by the post_save
                      signal in apps.account.signals on landlord creation)

Both columns are nullable so existing rows (tenants, admins, and any
landlords already created) keep working without backfill. Going forward
every new landlord gets a trial populated automatically by the signal.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('user_account', '0001_initial'),
        ('user_account', '0002_promote_existing_admins_to_superusers'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='trial_start_date',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='user',
            name='trial_end_date',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
