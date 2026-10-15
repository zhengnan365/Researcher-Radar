from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("papers", "0010_systemsetting"),
    ]

    operations = [
        migrations.AddField(
            model_name="zoterosyncstate",
            name="sync_error",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="zoterosyncstate",
            name="sync_finished_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="zoterosyncstate",
            name="sync_mode",
            field=models.CharField(
                choices=[("quick", "快速同步"), ("full", "全量校准")],
                default="quick",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="zoterosyncstate",
            name="sync_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="zoterosyncstate",
            name="sync_status",
            field=models.CharField(
                choices=[("idle", "未运行"), ("running", "运行中"), ("success", "成功"), ("failed", "失败")],
                db_index=True,
                default="idle",
                max_length=20,
            ),
        ),
    ]
