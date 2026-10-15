from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from papers.management.commands.repair_keyword_weights import repair_plan
from papers.models import Keyword, ResearchDirection


class KeywordWeightRepairTests(TestCase):
    def test_preview_then_apply_preserves_direction_and_is_idempotent(self):
        direction = ResearchDirection.objects.create(name="Hydrogen systems")
        generic = Keyword.objects.create(keyword="hydrogen | 5", weight=1, direction=direction, aliases="H2")
        strong = Keyword.objects.create(keyword="SOEC | 5", weight=1, direction=direction)
        technical = Keyword.objects.create(keyword="hydrogen storage | 5", weight=1, direction=direction)

        call_command("repair_keyword_weights", verbosity=0)
        generic.refresh_from_db()
        self.assertEqual(generic.keyword, "hydrogen | 5")

        call_command("repair_keyword_weights", "--apply", verbosity=0)
        generic.refresh_from_db()
        strong.refresh_from_db()
        technical.refresh_from_db()
        self.assertEqual((generic.keyword, generic.weight, generic.aliases, generic.direction), ("hydrogen", 3, "H2", direction))
        self.assertEqual((strong.keyword, strong.weight), ("SOEC", 5))
        self.assertEqual((technical.keyword, technical.weight), ("hydrogen storage", 4))
        self.assertEqual(repair_plan(list(Keyword.objects.all())), [])

    def test_collision_aborts_before_any_change(self):
        Keyword.objects.create(keyword="hydrogen")
        malformed = Keyword.objects.create(keyword="hydrogen | 5")
        with self.assertRaises(CommandError):
            call_command("repair_keyword_weights", "--apply", verbosity=0)
        malformed.refresh_from_db()
        self.assertEqual(malformed.keyword, "hydrogen | 5")
