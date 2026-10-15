from django.db import migrations, models


def create_start_lock(apps, schema_editor):
    SystemSetting = apps.get_model("papers", "SystemSetting")
    SystemSetting.objects.using(schema_editor.connection.alias).get_or_create(
        key="__background_task_start_lock__",
        defaults={"value": {}, "description": "后台任务启动锁"},
    )


class Migration(migrations.Migration):
    dependencies = [("papers", "0022_remove_retired_metadata")]

    operations = [
        migrations.AddField(model_name="fetchtask", name="worker_pid", field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name="rescoretask", name="worker_pid", field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name="abstractupdatetask", name="worker_pid", field=models.PositiveIntegerField(default=0)),
        migrations.RunPython(create_start_lock, migrations.RunPython.noop),
    ]
