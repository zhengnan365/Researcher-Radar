# Generated manually for Zotero collection display metadata.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("papers", "0003_zoteroconfig"),
    ]

    operations = [
        migrations.AddField(
            model_name="paper",
            name="zotero_collection_key",
            field=models.CharField(blank=True, max_length=120, verbose_name="Zotero Collection Key"),
        ),
        migrations.AddField(
            model_name="paper",
            name="zotero_collection_name",
            field=models.CharField(blank=True, max_length=255, verbose_name="Zotero Collection Name"),
        ),
    ]
