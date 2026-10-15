"""Compact old low relevance papers while retaining indexed dedup identities."""

from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from papers.models import Paper
from papers.services.runtime_settings import get_runtime_rules


def prune_low_score_content(*, now=None, batch_size: int = 500) -> int:
    rules = get_runtime_rules()
    now = now or timezone.now()
    cutoff = now - timedelta(days=rules["low_score_retention_days"])
    candidates = Paper.objects.filter(
        content_pruned_at__isnull=True,
        created_at__lt=cutoff,
        is_favorite=False,
        zotero_imported=False,
    ).filter(Q(recommend_score__lt=rules["low_score_threshold"]) | Q(relevance_override="irrelevant"))
    total = 0
    while True:
        ids = list(candidates.order_by("id").values_list("id", flat=True)[:batch_size])
        if not ids:
            break
        with transaction.atomic():
            Paper.keywords.through.objects.filter(paper_id__in=ids).delete()
            Paper.directions.through.objects.filter(paper_id__in=ids).delete()
            total += Paper.objects.filter(id__in=ids, content_pruned_at__isnull=True).update(
                authors="", journal="", published_date=None, abstract="", raw_keywords="",
                ai_summary="", ai_summary_model="", ai_summary_input_hash="", ai_summarized_at=None,
                source=None, source_name="", source_url="", matched_fields={}, score_detail={}, scored_at=None,
                system_recommend_score=None, recommend_score=0, recommend_level="low",
                is_archived=False, is_soft_deleted=True, content_pruned_at=now, updated_at=now,
            )
    return total
