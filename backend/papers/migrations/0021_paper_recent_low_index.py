from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("papers", "0020_paper_dedup_and_pruning")]

    operations = [
        migrations.AddIndex(
            model_name="paper",
            index=models.Index(fields=["content_pruned_at", "created_at", "recommend_score"], name="paper_recent_low_idx2"),
        ),
    ]
