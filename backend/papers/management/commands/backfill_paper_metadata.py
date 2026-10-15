from __future__ import annotations

from django.core.management.base import BaseCommand

from papers.models import Paper
from papers.services.abstract_enricher import enrich_abstract
from papers.services.metadata_enricher import enrich_with_crossref
from papers.services.rss_fetcher import extract_real_abstract


class Command(BaseCommand):
    help = "Backfill DOI, metadata and abstracts for existing papers."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0, help="Maximum papers to process. 0 means all.")
        parser.add_argument(
            "--only-empty-abstract",
            action="store_true",
            help="Only process papers whose abstract is empty or RSS metadata-like.",
        )

    def handle(self, *args, **options):
        limit = int(options["limit"] or 0)
        only_empty = bool(options["only_empty_abstract"])
        queryset = Paper.objects.filter(content_pruned_at__isnull=True).order_by("-published_date", "-created_at")
        if only_empty:
            queryset = queryset.filter(abstract="")
        if limit:
            queryset = queryset[:limit]

        processed = 0
        updated = 0
        abstract_updated = 0
        doi_updated = 0

        for paper in queryset:
            processed += 1
            data = {
                "title": paper.title,
                "authors": paper.authors,
                "journal": paper.journal,
                "published_date": paper.published_date,
                "doi": paper.doi or "",
                "url": paper.url,
                "abstract": extract_real_abstract(paper.abstract or ""),
                "raw_keywords": paper.raw_keywords,
            }
            data = enrich_with_crossref(data)
            data = enrich_abstract(data)

            fields = []
            for field in ("doi", "authors", "journal", "published_date", "url", "abstract", "raw_keywords"):
                value = data.get(field)
                if value and value != getattr(paper, field):
                    if field == "abstract" and not value.strip():
                        continue
                    setattr(paper, field, value)
                    fields.append(field)

            if fields:
                paper.save(update_fields=fields + ["updated_at"])
                updated += 1
                if "abstract" in fields:
                    abstract_updated += 1
                if "doi" in fields:
                    doi_updated += 1

            if processed % 20 == 0:
                self.stdout.write(f"processed={processed}, updated={updated}, abstracts={abstract_updated}, dois={doi_updated}")

        self.stdout.write(self.style.SUCCESS("元数据回填完成"))
        self.stdout.write(f"处理文献数: {processed}")
        self.stdout.write(f"更新文献数: {updated}")
        self.stdout.write(f"补充摘要数: {abstract_updated}")
        self.stdout.write(f"补充 DOI 数: {doi_updated}")
