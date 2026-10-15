from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from papers.models import Paper
from papers.services.relevance_scorer import score_paper


def rescore_papers_queryset(days: int = 0, paper_ids: list[int] | None = None):
    queryset = Paper.objects.select_related("source").prefetch_related("keywords", "directions").filter(content_pruned_at__isnull=True).order_by("id")
    if days:
        queryset = queryset.filter(created_at__gte=timezone.now() - timedelta(days=days))
    if paper_ids:
        queryset = queryset.filter(id__in=paper_ids)
    count = queryset.count()
    for paper in queryset.iterator(chunk_size=100):
        score_paper(paper)
    return count
