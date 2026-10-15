from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("papers", "0016_paper_relevance_override_and_more"),
    ]

    operations = [
        migrations.RemoveField(model_name="researchdirection", name="profile_collection_key"),
        migrations.RemoveField(model_name="researchdirection", name="profile_item_count"),
        migrations.RemoveField(model_name="researchdirection", name="profile_terms"),
        migrations.RemoveField(model_name="researchdirection", name="profile_updated_at"),
    ]
