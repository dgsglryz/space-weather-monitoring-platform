from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def populate_user_field(apps, schema_editor):
    AlertHistory = apps.get_model('telemetry', 'AlertHistory')
    AlertConfig = apps.get_model('telemetry', 'AlertConfig')
    
    for history in AlertHistory.objects.filter(user__isnull=True):
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
        ('telemetry', '0003_geocodecache'),
    ]

    operations = [
        migrations.AddField(
            model_name='alerthistory',
            name='user',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='alert_history', to=settings.AUTH_USER_MODEL),
        ),
        migrations.RunPython(populate_user_field),
    ]
