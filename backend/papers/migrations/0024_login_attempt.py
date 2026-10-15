from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [("papers", "0023_task_worker_identity")]

    operations = [
        migrations.CreateModel(
            name="LoginAttempt",
            fields=[
                ("identity_hash", models.CharField(max_length=64, primary_key=True, serialize=False)),
                ("failures", models.PositiveSmallIntegerField(default=0)),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("updated_at", models.DateTimeField(default=django.utils.timezone.now)),
            ],
        ),
    ]
