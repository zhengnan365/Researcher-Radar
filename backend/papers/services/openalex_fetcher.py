from __future__ import annotations

import logging
import os
import re
import traceback
from datetime import timedelta

import requests
from django.conf import settings
from django.utils import timezone

from papers.models import FetchLog, RssSource, normalize_doi

from .abstract_enricher import restore_inverted_abstract
from .openalex_client import OpenAlexRateLimitError, request_openalex
from .keyword_matcher import classify_payload_keywords_and_directions
from .relevance_scorer import score_paper
from .rss_fetcher import apply_prefetched_matches, should_skip_unmatched_article, upsert_paper


logger = logging.getLogger(__name__)
OPENALEX_BASE = "https://api.openalex.org"
def resolve_source_id(issn: str) -> str:
    issn = str(issn or "").strip()
    if not re.fullmatch(r"\d{4}-\d{3}[\dXx]", issn):
        raise ValueError("ISSN 格式应为 1234-5678。")
    response = request_openalex(f"{OPENALEX_BASE}/sources/issn:{issn}")
    response.raise_for_status()
    source_id = str(response.json().get("id") or "").rsplit("/", 1)[-1]
    if not re.fullmatch(r"S\d+", source_id):
        raise ValueError("OpenAlex 未返回有效的期刊 ID。")
    return source_id


def test_openalex_issn(issn: str) -> dict:
    try:
        source_id = resolve_source_id(issn)
        return {"ok": True, "title": f"OpenAlex {source_id}", "entry_count": 0, "message": "ISSN 可识别"}
    except (ValueError, requests.RequestException) as exc:
        return {"ok": False, "title": "", "entry_count": 0, "message": str(exc)}


def parse_work(work: dict, source: RssSource) -> dict:
    from .utils import parse_date

    location = work.get("primary_location") or {}
    title = str(work.get("title") or "").strip()
    doi = normalize_doi(work.get("doi"))
    authors = ", ".join(
        str((row.get("author") or {}).get("display_name") or "").strip()
        for row in (work.get("authorships") or [])[:30]
        if (row.get("author") or {}).get("display_name")
    )
    abstract = restore_inverted_abstract(work.get("abstract_inverted_index"))
    return {
        "title": title,
        "authors": authors,
        "journal": source.journal or (location.get("source") or {}).get("display_name") or source.name,
        "published_date": parse_date(work.get("publication_date") or ""),
        "doi": doi,
        "url": location.get("landing_page_url") or work.get("id") or (f"https://doi.org/{doi}" if doi else ""),
        "abstract": abstract,
        "source_name": source.name,
        "source_url": source.url or f"{OPENALEX_BASE}/sources/issn:{source.openalex_issn}",
        "raw_keywords": "; ".join(str(row.get("display_name") or "") for row in (work.get("keywords") or [])[:10] if row.get("display_name")),
    }


def fetch_openalex_source(source: RssSource) -> dict:
    counters = {"fetched_count": 0, "new_count": 0, "duplicate_count": 0, "skipped_unmatched_count": 0}
    try:
        source_id = resolve_source_id(source.openalex_issn)
        start = timezone.localdate() - timedelta(days=max(1, int(os.getenv("OPENALEX_LOOKBACK_DAYS", "14"))))
        max_pages = max(1, min(10, int(os.getenv("OPENALEX_MAX_PAGES", "3"))))
        for page in range(1, max_pages + 1):
            response = request_openalex(
                f"{OPENALEX_BASE}/works",
                params={
                    "filter": f"primary_location.source.id:{source_id},from_publication_date:{start.isoformat()}",
                    "sort": "publication_date:desc",
                    "per_page": 100,
                    "page": page,
                },
            )
            response.raise_for_status()
            rows = response.json().get("results") or []
            for work in rows:
                data = parse_work(work, source)
                if not data["title"]:
                    continue
                counters["fetched_count"] += 1
                keywords, directions = classify_payload_keywords_and_directions(data, source)
                if should_skip_unmatched_article(keywords, directions):
                    counters["skipped_unmatched_count"] += 1
                    continue
                paper, created = upsert_paper(data, source)
                if paper.content_pruned_at is None:
                    apply_prefetched_matches(paper, keywords, directions)
                    score_paper(paper)
                counters["new_count" if created else "duplicate_count"] += 1
            if len(rows) < 100:
                break
        status = "success"
        message = f"OpenAlex 检查 {counters['fetched_count']} 条，新入库 {counters['new_count']} 条，已存在 {counters['duplicate_count']} 条"
        error_detail = ""
    except OpenAlexRateLimitError as exc:
        status = "partial" if counters["fetched_count"] else "failed"
        reset_minutes = max(1, round(exc.retry_after / 60))
        message = f"OpenAlex 暂时限流，已暂停请求，建议约 {reset_minutes} 分钟后重试"
        error_detail = str(exc)
        logger.warning("OpenAlex source rate limited: %s", source.name)
    except Exception as exc:
        status = "failed"
        message = f"OpenAlex 抓取失败：{exc}"
        error_detail = traceback.format_exc()
        logger.exception("OpenAlex source failed: %s", source.name)
    source.last_fetch_time = timezone.now()
    source.last_fetch_status = status
    source.last_fetch_message = message
    source.total_fetched_count += counters["fetched_count"]
    source.save(update_fields=["last_fetch_time", "last_fetch_status", "last_fetch_message", "total_fetched_count", "updated_at"])
    FetchLog.objects.create(source=source, source_name=source.name, status=status, message=message, error_detail=error_detail, **{key: counters[key] for key in ("fetched_count", "new_count", "duplicate_count")})
    return {"status": status, **counters}
