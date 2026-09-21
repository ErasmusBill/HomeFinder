from django.db import migrations, models


def clean_empty_phone_numbers(apps, schema_editor):
    User = apps.get_model('user_account', 'User')
    User.objects.filter(phone_number='').update(phone_number=None)


class Migration(migrations.Migration):

    dependencies = [
        ('user_account', '0010_user_email_property_alerts'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='phone_number',
            field=models.CharField(blank=True, max_length=30, null=True, unique=True),
        ),
        migrations.RunPython(clean_empty_phone_numbers, reverse_code=migrations.RunPython.noop),
    ]
