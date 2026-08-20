# Generated for property-alert pipeline.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenant', '0002_propertyalert_last_notified_at'),
        ('home_finder', '0006_propertyinterest'),
    ]

    operations = [
        migrations.AddField(
            model_name='propertyalert',
            name='notified_properties',
            field=models.ManyToManyField(
                blank=True,
                help_text='Properties this alert has already been notified about. '
                          'Used for per-(alert, property) dedup so the same '
                          'property is never emailed to the same tenant twice.',
                related_name='notifying_property_alerts',
                to='home_finder.property',
            ),
        ),
    ]
