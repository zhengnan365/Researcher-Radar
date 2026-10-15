"""Optional ScienceDirect journal fallback for entitled API keys."""

from __future__ import annotations

import logging
import os
import time
import traceback
from datetime import timedelta

import requests
from django.conf import settings
from django.utils import timezone

from papers.models import FetchLog, RssSource, normalize_doi

from .keyword_matcher import classify_payload_keywords_and_directions
from .relevance_scorer import score_paper
from .rss_fetcher import apply_prefetched_matches, should_skip_unmatched_article, upsert_paper
from .utils import clean_text, join_authors, parse_date

logger = logging.getLogger(__name__)
_retry_at = 0.0
API_URL = "https://api.elsevier.com/content/search/sciencedirect"


def parse_elsevier_work(work: dict, source: RssSource) -> dict | None:
    journal = clean_text(work.get("sourceTitle"))
    expected = clean_text(source.journal or source.name)
    if not journal or journal.casefold() != expected.casefold():
        return None
    doi = normalize_doi(work.get("doi"))
    title = clean_text(work.get("title"))
    if not doi or not title:
        return None
    return {
        "title": title,
        "authors": join_authors(work.get("authors")),
        "journal": expected,
        "published_date": parse_date(work.get("publicationDate")),
        "doi": doi,
        "url": work.get("uri") or f"https://doi.org/{doi}",
        "abstract": "",
        "source_name": source.name,
        "source_url": source.url or API_URL,
        "raw_keywords": "",
    }


def fetch_elsevier_journal(source: RssSource) -> dict:
    global _retry_at
    counters = {"fetched_count": 0, "new_count": 0, "duplicate_count": 0, "skipped_unmatched_count": 0}
    try:
        key = os.getenv("ELSEVIER_API_KEY", "").strip()
        if not key:
            raise ValueError("未配置 Elsevier API Key")
        if time.monotonic() < _retry_at:
            raise RuntimeError("Elsevier API 暂时不可用，请稍后重试")
        lookback = max(1, min(90, int(os.getenv("ELSEVIER_FALLBACK_LOOKBACK_DAYS", "21"))))
        max_pages = max(1, min(5, int(os.getenv("ELSEVIER_FALLBACK_MAX_PAGES", "2"))))
        loaded_after = (timezone.now() - timedelta(days=lookback)).strftime("%Y-%m-%dT%H:%M:%SZ")
        truncated = False
        for page in range(max_pages):
            try:
                response = requests.put(
                    API_URL,
                    json={
                        "pub": source.journal or source.name,
                        "loadedAfter": loaded_after,
                        "display": {"offset": page * 100, "show": 100, "sortBy": "date"},
                    },
                    headers={"X-ELS-APIKey": key, "Accept": "application/json", "Content-Type": "application/json"},
                    timeout=getattr(settings, "LITERATURE_HTTP_TIMEOUT", 10),
                )
            except requests.RequestException:
                _retry_at = time.monotonic() + 300
                raise
            if response.status_code in {401, 403}:
                _retry_at = time.monotonic() + 86400
                raise RuntimeError("Elsevier Key 未获得 ScienceDirect API 权限")
            if response.status_code == 429:
                try:
                    wait = max(1, min(86400, int(float(response.headers.get("Retry-After", "300")))))
                except (TypeError, ValueError):
                    wait = 300
                _retry_at = time.monotonic() + wait
                raise RuntimeError(f"Elsevier 返回 429，约 {max(1, round(wait / 60))} 分钟后重试")
            try:
                response.raise_for_status()
            except requests.RequestException:
                _retry_at = time.monotonic() + 300
                raise
            payload = response.json()
            rows = payload.get("results") or []
            for work in rows:
                data = parse_elsevier_work(work, source)
                if not data:
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
            if page == max_pages - 1 and int(payload.get("resultsFound") or 0) > max_pages * 100:
                truncated = True
        status = "partial" if truncated else "success"
        message = f"Elsevier 备用检查 {counters['fetched_count']} 条，新入库 {counters['new_count']} 条"
        if truncated:
            message += "；结果超过页数上限"
        error_detail = ""
    except Exception as exc:
        status = "partial" if counters["fetched_count"] else "failed"
        message = f"Elsevier 备用抓取失败：{exc}"
        error_detail = traceback.format_exc()
        logger.warning("Elsevier journal fallback failed for %s: %s", source.name, exc)
    source.last_fetch_time = timezone.now()
    source.last_fetch_status = status
    source.last_fetch_message = message
    source.total_fetched_count += counters["fetched_count"]
    source.save(update_fields=["last_fetch_time", "last_fetch_status", "last_fetch_message", "total_fetched_count", "updated_at"])
    FetchLog.objects.create(source=source, source_name=source.name, status=status, message=message, error_detail=error_detail, **{key: counters[key] for key in ("fetched_count", "new_count", "duplicate_count")})
    return {"status": status, **counters}
