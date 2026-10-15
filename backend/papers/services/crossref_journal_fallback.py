"""Bounded Crossref journal fallback when a configured source fails."""

from __future__ import annotations

import logging
import os
import re
import time
import traceback
from datetime import timedelta
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.utils import timezone

from papers.models import FetchLog, RssSource, normalize_doi

from .keyword_matcher import classify_payload_keywords_and_directions
from .metadata_enricher import crossref_date
from .relevance_scorer import score_paper
from .rss_fetcher import apply_prefetched_matches, should_skip_unmatched_article, upsert_paper
from .utils import clean_abstract_text, first, join_authors

logger = logging.getLogger(__name__)
_retry_at = 0.0
_ISSN = re.compile(r"\d{4}-?\d{3}[\dXx]")


def source_issn(source: RssSource) -> str:
    """Use the configured ISSN, or the ISSN embedded in ScienceDirect RSS URLs."""
    configured = str(source.openalex_issn or "").strip()
    parsed = urlparse(source.url or "")
    candidate = configured or (
        parsed.path.rstrip("/").rsplit("/", 1)[-1]
        if parsed.hostname == "rss.sciencedirect.com" and parsed.path.startswith("/publication/science/")
        else ""
    )
    if not _ISSN.fullmatch(candidate):
        return ""
    digits = candidate.replace("-", "").upper()
    return f"{digits[:4]}-{digits[4:]}"


def parse_crossref_work(work: dict, source: RssSource) -> dict:
    doi = normalize_doi(work.get("DOI"))
    return {
        "title": first(work.get("title")).strip(),
        "authors": join_authors(work.get("author")),
        "journal": source.journal or first(work.get("container-title")) or source.name,
        "published_date": crossref_date(work),
        "doi": doi,
        "url": work.get("URL") or (f"https://doi.org/{doi}" if doi else ""),
        "abstract": clean_abstract_text(work.get("abstract")),
        "source_name": source.name,
        "source_url": source.url or f"https://api.crossref.org/journals/{source_issn(source)}/works",
        # Crossref subject is a journal-level classification, not article keywords.
        "raw_keywords": "",
    }


def fetch_crossref_journal(source: RssSource) -> dict:
    global _retry_at
    counters = {"fetched_count": 0, "new_count": 0, "duplicate_count": 0, "skipped_unmatched_count": 0}
    issn = source_issn(source)
    try:
        if not issn:
            raise ValueError("缺少有效期刊 ISSN")
        if time.monotonic() < _retry_at:
            raise RuntimeError("Crossref 暂时限流，请稍后重试")
        lookback = max(1, min(90, int(os.getenv("CROSSREF_FALLBACK_LOOKBACK_DAYS", "21"))))
        publication_lookback = max(lookback, min(180, int(os.getenv("CROSSREF_FALLBACK_PUBLICATION_DAYS", "60"))))
        max_pages = max(1, min(5, int(os.getenv("CROSSREF_FALLBACK_MAX_PAGES", "3"))))
        start = timezone.localdate() - timedelta(days=lookback)
        published_since = timezone.localdate() - timedelta(days=publication_lookback)
        mailto = os.getenv("CROSSREF_MAILTO", "").strip()
        headers = {"User-Agent": f"ResearcherRadar/1.0 (mailto:{mailto})" if mailto else "ResearcherRadar/1.0"}
        truncated = False
        for page in range(max_pages):
            response = requests.get(
                f"https://api.crossref.org/journals/{issn}/works",
                params={
                    "filter": f"from-index-date:{start.isoformat()},from-pub-date:{published_since.isoformat()},type:journal-article",
                    "sort": "indexed", "order": "desc", "rows": 100, "offset": page * 100,
                    "select": "DOI,title,author,container-title,URL,published-online,published-print,published,issued,abstract",
                    **({"mailto": mailto} if mailto else {}),
                },
                headers=headers,
                timeout=getattr(settings, "LITERATURE_HTTP_TIMEOUT", 10),
            )
            if response.status_code == 429:
                try:
                    wait = max(1, min(86400, int(float(response.headers.get("Retry-After", "300")))))
                except (TypeError, ValueError):
                    wait = 300
                _retry_at = time.monotonic() + wait
                raise RuntimeError(f"Crossref 返回 429，约 {max(1, round(wait / 60))} 分钟后重试")
            response.raise_for_status()
            payload = response.json().get("message", {})
            rows = payload.get("items") or []
            for work in rows:
                data = parse_crossref_work(work, source)
                if not data["title"] or not data["doi"]:
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
            if page == max_pages - 1 and int(payload.get("total-results") or 0) > max_pages * 100:
                truncated = True
        status = "partial" if truncated else "success"
        message = f"Crossref 备用检查 {counters['fetched_count']} 条，新入库 {counters['new_count']} 条"
        if truncated:
            message += "；结果超过页数上限，请扩大回看或页数后再补抓"
        error_detail = ""
    except Exception as exc:
        status = "partial" if counters["fetched_count"] else "failed"
        message = f"Crossref 备用抓取失败：{exc}"
        error_detail = traceback.format_exc()
        logger.warning("Crossref journal fallback failed for %s: %s", source.name, exc)
    source.last_fetch_time = timezone.now()
    source.last_fetch_status = status
    source.last_fetch_message = message
    source.total_fetched_count += counters["fetched_count"]
    source.save(update_fields=["last_fetch_time", "last_fetch_status", "last_fetch_message", "total_fetched_count", "updated_at"])
    FetchLog.objects.create(source=source, source_name=source.name, status=status, message=message, error_detail=error_detail, **{key: counters[key] for key in ("fetched_count", "new_count", "duplicate_count")})
    return {"status": status, **counters}
