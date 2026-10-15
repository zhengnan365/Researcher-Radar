from django.core.management.base import BaseCommand
from django.utils import timezone

from papers.models import Paper
from papers.services.abstract_enricher import enrich_abstract
from papers.services.relevance_scorer import score_paper
from papers.services.report_generator import generate_daily_report


class Command(BaseCommand):
    help = "Update missing abstracts of high-scoring papers first, then rescore them."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=10)
        parser.add_argument("--min-score", type=int, default=30)

    def handle(self, *args, **options):
        limit = options["limit"]
        if not 1 <= limit <= 100:
            raise ValueError("--limit must be between 1 and 100")
        papers = list(Paper.objects.filter(
            content_pruned_at__isnull=True, abstract="",
            recommend_score__gte=options["min_score"],
        ).order_by("-recommend_score", "-created_at")[:limit])
        updated = 0
        report_dates = set()
        for paper in papers:
            data = enrich_abstract({"title": paper.title, "doi": paper.doi or "", "abstract": ""})
            abstract = str(data.get("abstract") or "").strip()
            if not abstract:
                self.stdout.write(f"No abstract: paper {paper.pk}")
                continue
            paper.abstract = abstract
            paper.save(update_fields=["abstract", "updated_at"])
            score_paper(paper)
            report_dates.add(timezone.localtime(paper.created_at).date())
            updated += 1
            self.stdout.write(f"Updated abstract: paper {paper.pk}")
        for report_date in sorted(report_dates):
            generate_daily_report(report_date)
        self.stdout.write(self.style.SUCCESS(f"Updated {updated}/{len(papers)} priority abstracts."))
