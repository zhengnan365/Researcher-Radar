# Generated manually for the background RSS fetch task state.

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("papers", "0006_zoteroitem_identity_key"),
    ]

    operations = [
        migrations.CreateModel(
            name="FetchTask",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="鍒涘缓鏃堕棿")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="鏇存柊鏃堕棿")),
                ("task_id", models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "pending"),
                            ("running", "running"),
                            ("success", "success"),
                            ("failed", "failed"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("message", models.TextField(blank=True)),
                ("error_detail", models.TextField(blank=True)),
                ("source_total", models.IntegerField(default=0)),
                ("success_sources", models.IntegerField(default=0)),
                ("failed_sources", models.IntegerField(default=0)),
                ("fetched_count", models.IntegerField(default=0)),
                ("new_count", models.IntegerField(default=0)),
                ("duplicate_count", models.IntegerField(default=0)),
                ("report_date", models.DateField(blank=True, null=True)),
                ("report_title", models.CharField(blank=True, max_length=255)),
                ("paper_count", models.IntegerField(default=0)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "verbose_name": "Fetch Task",
                "verbose_name_plural": "Fetch Tasks",
                "ordering": ["-created_at"],
            },
        ),
    ]
