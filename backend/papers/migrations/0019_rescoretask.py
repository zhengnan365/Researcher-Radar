import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("papers", "0018_research_interest_fields")]

    operations = [
        migrations.CreateModel(
            name="RescoreTask",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
                ("task_id", models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True)),
                ("status", models.CharField(choices=[("pending", "等待中"), ("running", "运行中"), ("success", "完成"), ("partial", "部分失败"), ("failed", "失败")], db_index=True, default="pending", max_length=20)),
                ("scope", models.CharField(choices=[("7", "最近 7 天"), ("30", "最近 30 天"), ("all", "全部")], default="all", max_length=8)),
                ("target_count", models.PositiveIntegerField(default=0)),
                ("processed_count", models.PositiveIntegerField(default=0)),
                ("failed_count", models.PositiveIntegerField(default=0)),
                ("message", models.TextField(blank=True)),
                ("error_detail", models.TextField(blank=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={"ordering": ["-created_at"], "verbose_name": "重新评分任务", "verbose_name_plural": "重新评分任务"},
        ),
    ]
