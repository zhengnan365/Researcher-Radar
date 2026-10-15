from __future__ import annotations

from django.db import models
from django.db.models import Q, QuerySet


def filter_papers(queryset: QuerySet, params) -> QuerySet:
    date = params.get("date")
    keyword = params.get("keyword")
    direction = params.get("direction")
    journal = params.get("journal")
    source = params.get("source")
    favorite = params.get("favorite")
    zotero_imported = params.get("zotero_imported")
    abstract_missing = params.get("abstract_missing")
    min_score = params.get("min_score")
    max_score = params.get("max_score")
    recommend_level = params.get("recommend_level")
    archived = params.get("archived")
    soft_deleted = params.get("soft_deleted")
    order = params.get("order")
    search = params.get("search")

    if date:
        queryset = queryset.filter(created_at__date=date)
    if keyword:
        queryset = queryset.filter(Q(keywords__id=keyword) | Q(keywords__keyword__icontains=keyword))
    if direction:
        queryset = queryset.filter(Q(directions__id=direction) | Q(directions__name__icontains=direction))
    if journal:
        queryset = queryset.filter(journal__icontains=journal)
    if source:
        queryset = queryset.filter(Q(source__id=source) | Q(source_name__icontains=source) | Q(source__name__icontains=source))
    if favorite in {"true", "1", "yes"}:
        queryset = queryset.filter(is_favorite=True)
    elif favorite in {"false", "0", "no"}:
        queryset = queryset.filter(is_favorite=False)
    if zotero_imported in {"true", "1", "yes"}:
        queryset = queryset.filter(zotero_imported=True)
    elif zotero_imported in {"false", "0", "no"}:
        queryset = queryset.filter(zotero_imported=False)
    if abstract_missing in {"true", "1", "yes"}:
        queryset = queryset.filter(Q(abstract="") | Q(abstract__isnull=True))
    elif abstract_missing in {"false", "0", "no"}:
        queryset = queryset.exclude(Q(abstract="") | Q(abstract__isnull=True))
    if min_score not in {None, ""}:
        queryset = queryset.filter(recommend_score__gte=int(min_score))
    if max_score not in {None, ""}:
        queryset = queryset.filter(recommend_score__lte=int(max_score))
    if recommend_level:
        queryset = queryset.filter(recommend_level=recommend_level)
    if archived in {"true", "1", "yes"}:
        queryset = queryset.filter(is_archived=True)
    elif archived in {"false", "0", "no"}:
        queryset = queryset.filter(is_archived=False)
    if soft_deleted in {"true", "1", "yes"}:
        queryset = queryset.filter(is_soft_deleted=True)
    elif soft_deleted in {"false", "0", "no"}:
        queryset = queryset.filter(is_soft_deleted=False)
    if search:
        queryset = queryset.filter(
            Q(title__icontains=search)
            | Q(authors__icontains=search)
            | Q(doi__icontains=search)
            | Q(abstract__icontains=search)
            | Q(journal__icontains=search)
        )
    queryset = queryset.distinct()
    if order == "score":
        return queryset.annotate(direction_priority=models.Max("directions__priority")).order_by("-recommend_score", "-direction_priority", "-published_date", "-created_at", "-id")
    if order == "date":
        return queryset.order_by("-published_date", "-created_at")
    if order == "keyword_count":
        return queryset.annotate(keyword_count=models.Count("keywords")).order_by("-keyword_count", "-recommend_score")
    return queryset


def filter_fetch_logs(queryset: QuerySet, params) -> QuerySet:
    source = params.get("source")
    status = params.get("status")
    date = params.get("date")
    if source:
        queryset = queryset.filter(Q(source__id=source) | Q(source_name__icontains=source))
    if status:
        queryset = queryset.filter(status=status)
    if date:
        queryset = queryset.filter(created_at__date=date)
    return queryset
