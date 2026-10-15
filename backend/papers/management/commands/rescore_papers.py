from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from papers.models import Paper


class Command(BaseCommand):
    help = "Recalculate recommendation scores for existing papers."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=0, help="Only rescore papers created in the last N days.")
        parser.add_argument("--source", type=str, default="", help="RSS source id or source name keyword.")
        parser.add_argument("--journal", type=str, default="", help="Journal name keyword.")
        parser.add_argument("--paper-id", type=int, default=0, help="Only rescore one paper id.")

    def handle(self, *args, **options):
        queryset = Paper.objects.select_related("source").prefetch_related("keywords", "directions").filter(content_pruned_at__isnull=True).order_by("id")
        if options["days"]:
            queryset = queryset.filter(created_at__gte=timezone.now() - timedelta(days=options["days"]))
        if options["source"]:
            source = options["source"]
            if source.isdigit():
                queryset = queryset.filter(source_id=int(source))
            else:
                queryset = queryset.filter(source_name__icontains=source)
        if options["journal"]:
            queryset = queryset.filter(journal__icontains=options["journal"])
        if options["paper_id"]:
            queryset = queryset.filter(id=options["paper_id"])

        total = queryset.count()
        count = 0
        for paper in queryset.iterator(chunk_size=100):
            from papers.services.relevance_scorer import score_paper

            score_paper(paper)
            count += 1
            if count % 100 == 0:
                self.stdout.write(f"Rescored {count}/{total}")
        self.stdout.write(self.style.SUCCESS(f"Rescored {total} papers."))
