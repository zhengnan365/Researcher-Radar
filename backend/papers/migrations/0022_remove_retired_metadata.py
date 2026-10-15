from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("papers", "0021_paper_recent_low_index")]

    operations = [
        migrations.RemoveField(model_name="researchdirection", name="description"),
        migrations.RemoveField(model_name="keyword", name="category"),
        migrations.RemoveField(model_name="rsssource", name="publisher"),
        migrations.RemoveField(model_name="rsssource", name="category"),
        migrations.RemoveField(model_name="rsssource", name="direction"),
    ]
