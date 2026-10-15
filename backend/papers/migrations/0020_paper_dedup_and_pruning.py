import hashlib

from django.db import migrations, models


def backfill_dedup_keys(apps, schema_editor):
    Paper = apps.get_model("papers", "Paper")
    batch = []
    for paper in Paper.objects.all().only("id", "doi", "title").iterator(chunk_size=500):
        doi = str(paper.doi or "").strip()
        doi = doi.removeprefix("https://doi.org/").removeprefix("http://doi.org/").removeprefix("doi:").strip().lower()
        title = " ".join(str(paper.title or "").split()).lower()
        paper.normalized_doi = doi
        paper.normalized_title_hash = hashlib.sha256(title.encode("utf-8")).hexdigest() if title else ""
        batch.append(paper)
        if len(batch) == 500:
            Paper.objects.bulk_update(batch, ["normalized_doi", "normalized_title_hash"])
            batch.clear()
    if batch:
        Paper.objects.bulk_update(batch, ["normalized_doi", "normalized_title_hash"])


class Migration(migrations.Migration):
    dependencies = [("papers", "0019_rescoretask")]

    operations = [
        migrations.AddField(model_name="paper", name="normalized_doi", field=models.CharField(blank=True, max_length=255, db_index=True, verbose_name="规范化 DOI")),
        migrations.AddField(model_name="paper", name="normalized_title_hash", field=models.CharField(blank=True, max_length=64, db_index=True, verbose_name="规范化标题检索键")),
        migrations.AddField(model_name="paper", name="content_pruned_at", field=models.DateTimeField(blank=True, null=True, db_index=True, verbose_name="低相关内容清理时间")),
        migrations.RunPython(backfill_dedup_keys, migrations.RunPython.noop),
    ]
