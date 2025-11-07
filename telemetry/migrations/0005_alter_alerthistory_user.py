from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def ensure_all_users_set(apps, schema_editor):
    """Ensure all AlertHistory records have a user before making field non-null.
    
    Note: This duplicates logic from 0004 but is necessary because 0004 added
    the field as nullable, and 0005 needs to ensure all records are populated
    before making it non-null. Safe to run multiple times.
    """
    AlertHistory = apps.get_model('telemetry', 'AlertHistory')
    AlertConfig = apps.get_model('telemetry', 'AlertConfig')
    
    for history in AlertHistory.objects.filter(user__isnull=True):
        # Safety check: ensure location exists
        if not history.location:
            continue
            
        config = AlertConfig.objects.filter(
            location=history.location,
            threshold_type=history.condition
        ).first()
        if config:
            history.user = config.user
            history.save()
        elif history.location.added_by_user:
            history.user = history.location.added_by_user
            history.save()


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('telemetry', '0004_alerthistory_user'),
    ]

    operations = [
        migrations.RunPython(ensure_all_users_set),
        migrations.AlterField(
            model_name='alerthistory',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='alert_history', to=settings.AUTH_USER_MODEL),
        ),
    ]
