from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


def backfill_name_cn(apps, schema_editor):
    ResearchDirection = apps.get_model("papers", "ResearchDirection")
    for direction in ResearchDirection.objects.all().iterator():
        direction.name_cn = direction.name
        direction.save(update_fields=["name_cn"])


class Migration(migrations.Migration):
    dependencies = [("papers", "0017_remove_research_direction_profile")]

    operations = [
        migrations.AddField(
            model_name="researchdirection",
            name="name_cn",
            field=models.CharField(max_length=120, null=True, verbose_name="中文名称"),
        ),
        migrations.AddField(
            model_name="researchdirection",
            name="name_en",
            field=models.CharField(blank=True, max_length=240, null=True, verbose_name="英文名称"),
        ),
        migrations.AddField(
            model_name="researchdirection",
            name="direction_weight",
            field=models.PositiveSmallIntegerField(default=3, validators=[MinValueValidator(1), MaxValueValidator(5)], verbose_name="方向权重"),
        ),
        migrations.AddField(
            model_name="researchdirection",
            name="priority",
            field=models.PositiveSmallIntegerField(default=3, validators=[MinValueValidator(1), MaxValueValidator(5)], verbose_name="优先级"),
        ),
        migrations.RunPython(backfill_name_cn, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="researchdirection",
            name="name_cn",
            field=models.CharField(max_length=120, unique=True, verbose_name="中文名称"),
        ),
        migrations.AlterField(
            model_name="keyword",
            name="weight",
            field=models.IntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(5)], verbose_name="权重"),
        ),
        migrations.AddConstraint(
            model_name="researchdirection",
            constraint=models.CheckConstraint(condition=models.Q(direction_weight__gte=1, direction_weight__lte=5), name="direction_weight_1_5"),
        ),
        migrations.AddConstraint(
            model_name="researchdirection",
            constraint=models.CheckConstraint(condition=models.Q(priority__gte=1, priority__lte=5), name="direction_priority_1_5"),
        ),
        migrations.AddConstraint(
            model_name="keyword",
            constraint=models.CheckConstraint(condition=models.Q(weight__gte=1, weight__lte=5), name="keyword_weight_1_5"),
        ),
    ]
