from __future__ import annotations

import re

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from papers.models import Keyword


# This command repairs the legacy paste format "keyword | weight" that was
# accidentally stored in Keyword.keyword instead of the weight column.
SUFFIX = re.compile(r"^(?P<term>.+?)\s*\|\s*(?P<weight>[1-5])\s*$")
WEIGHT_OVERRIDES = {
    # Strong evidence for the user's system-level research topics.
    "integrated energy system": 5,
    "multi-energy system": 5,
    "cchp": 5,
    "combined cooling heating and power": 5,
    "sofc-gt": 5,
    "soec": 5,
    "solid oxide electrolysis cell": 5,
    "hydrogen energy system": 5,
    "optimal scheduling": 5,
    "multi-objective optimization": 5,
    "robust optimization": 5,
    "sco2": 5,
    "supercritical co2": 5,
    # Important technical concepts.
    "fuel cell": 4,
    "sofc": 4,
    "electrolyzer": 4,
    "hydrogen production": 4,
    "hydrogen storage": 4,
    "energy hub": 4,
    "orc": 4,
    "organic rankine cycle": 4,
    "exergy analysis": 4,
    "thermal energy storage": 4,
    "pareto optimization": 4,
    # Broad topic words must not dominate a recommendation.
    "hydrogen": 3,
    "energy storage": 3,
    "microgrid": 3,
    "renewable energy": 3,
    "solar thermal": 3,
    "carbon capture": 3,
    "energy efficiency": 2,
    "decarbonization": 2,
    "low carbon": 2,
    "sustainability": 2,
    "energy": 2,
    "storage": 2,
    "optimization": 2,
}


def repair_plan(keywords: list[Keyword]) -> list[tuple[Keyword, str, int]]:
    occupied = {item.keyword.casefold(): item.pk for item in keywords}
    plan = []
    for item in keywords:
        match = SUFFIX.fullmatch(item.keyword)
        if not match:
            continue
        term = match.group("term").strip()
        existing = occupied.get(term.casefold())
        if existing is not None and existing != item.pk:
            raise ValueError(f"关键词 {item.keyword!r} 与现有关键词 {term!r} 冲突，未修改任何数据")
        occupied[term.casefold()] = item.pk
        pasted_weight = int(match.group("weight"))
        weight = WEIGHT_OVERRIDES.get(term.casefold(), min(pasted_weight, 4))
        plan.append((item, term, weight))
    return plan


class Command(BaseCommand):
    help = "Preview or repair legacy 'keyword | weight' entries; preserves directions and other metadata."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Apply the displayed changes. Default is dry run.")

    def handle(self, *args, **options):
        with transaction.atomic():
            keywords = list(Keyword.objects.select_for_update().order_by("pk"))
            try:
                plan = repair_plan(keywords)
            except ValueError as exc:
                raise CommandError(str(exc)) from exc
            for item, term, weight in plan:
                self.stdout.write(f"{item.pk}: {item.keyword!r} (weight={item.weight}) -> {term!r} (weight={weight})")
            if options["apply"]:
                for item, term, weight in plan:
                    item.keyword = term
                    item.weight = weight
                    item.save(update_fields=["keyword", "weight", "updated_at"])
        self.stdout.write(f"{'Applied' if options['apply'] else 'Previewed'} {len(plan)} keyword repairs.")
