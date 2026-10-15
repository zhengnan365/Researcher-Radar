from __future__ import annotations

import logging
import os
import re
import traceback
from collections.abc import Callable
from dataclasses import dataclass

import feedparser
import requests
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from papers.models import FetchLog, Paper, RssSource, normalize_doi, normalize_space, normalized_title_hash

from .abstract_enricher import enrich_abstract
from .keyword_matcher import classify_payload_keywords_and_directions
from .metadata_enricher import enrich_with_crossref
from .relevance_scorer import score_paper
from .utils import clean_text, extract_doi, join_authors, parse_date

logger = logging.getLogger(__name__)
@dataclass
class FetchSummary:
    source_total: int = 0
    success_sources: int = 0
    failed_sources: int = 0
    fetched_count: int = 0
    new_count: int = 0
    duplicate_count: int = 0
    skipped_unmatched_count: int = 0


ProgressCallback = Callable[[FetchSummary, RssSource | None, int, str], None]


def fetch_all_enabled_sources(progress_callback: ProgressCallback | None = None) -> FetchSummary:
    sources = list(RssSource.objects.filter(enabled=True).order_by("name"))
    summary = FetchSummary(source_total=len(sources))
    if progress_callback:
        progress_callback(summary, None, 0, "started")

    for index, source in enumerate(sources, start=1):
        if progress_callback:
            progress_callback(summary, source, index, "source_started")
        result = fetch_source(source)
        summary.fetched_count += result["fetched_count"]
        summary.new_count += result["new_count"]
        summary.duplicate_count += result["duplicate_count"]
        summary.skipped_unmatched_count += result.get("skipped_unmatched_count", 0)
        if result["status"] == "success":
            summary.success_sources += 1
        else:
            summary.failed_sources += 1
        if progress_callback:
            progress_callback(summary, source, index, "source_finished")
    from .low_score_retention import prune_low_score_content

    pruned = prune_low_score_content()
    if pruned:
        logger.info("Compacted %s old low relevance papers", pruned)
    return summary


def fetch_source(source: RssSource) -> dict:
    from .crossref_journal_fallback import fetch_crossref_journal, source_issn

    if source.fetch_mode == "rss":
        results = [("RSS", _fetch_rss_source(source), source.last_fetch_message)]
    else:
        from .openalex_fetcher import fetch_openalex_source

        if source.fetch_mode == "openalex":
            results = [("OpenAlex", fetch_openalex_source(source), source.last_fetch_message)]
        else:
            rss_result = _fetch_rss_source(source)
            rss_message = source.last_fetch_message
            openalex_result = fetch_openalex_source(source)
            results = [("RSS", rss_result, rss_message), ("OpenAlex", openalex_result, source.last_fetch_message)]

    primary_needs_backup = any(
        result["status"] != "success" and result.get("backup_eligible", True)
        for _, result, _ in results
    )
    if all(result["status"] == "success" for _, result, _ in results):
        if len(results) == 1:
            return results[0][1]
    elif primary_needs_backup and os.getenv("CROSSREF_JOURNAL_FALLBACK_ENABLED", "true").lower() in {"1", "true", "yes", "on"}:
        if source_issn(source):
            fallback = fetch_crossref_journal(source)
            results.append(("Crossref", fallback, source.last_fetch_message))
        else:
            results.append(("Crossref", {"status": "failed"}, "备用未运行：缺少 ISSN"))

    crossref_result = next((result for name, result, _ in results if name == "Crossref"), None)
    if (
        primary_needs_backup
        and os.getenv("ELSEVIER_API_KEY", "").strip()
        and (crossref_result is None or crossref_result["status"] != "success" or crossref_result.get("fetched_count", 0) == 0)
    ):
        from .elsevier_journal_fallback import fetch_elsevier_journal

        fallback = fetch_elsevier_journal(source)
        results.append(("Elsevier", fallback, source.last_fetch_message))

    statuses = {result["status"] for _, result, _ in results}
    recovered = any(
        result["status"] in {"success", "partial"} and (
            name in {"RSS", "OpenAlex"} or result.get("fetched_count", 0) > 0
        )
        for name, result, _ in results
    )
    combined = {
        key: sum(result.get(key, 0) for _, result, _ in results)
        for key in ("fetched_count", "new_count", "duplicate_count", "skipped_unmatched_count")
    }
    combined["status"] = "success" if statuses == {"success"} else "partial" if recovered else "failed"
    source.last_fetch_status = combined["status"]
    source.last_fetch_message = "; ".join(f"{name} ({result['status']}): {message}" for name, result, message in results)
    source.save(update_fields=["last_fetch_status", "last_fetch_message", "updated_at"])
    return combined


def _fetch_rss_source(source: RssSource) -> dict:
    fetched_count = 0
    new_count = 0
    duplicate_count = 0
    skipped_unmatched_count = 0
    checked_count = 0
    feed_loaded = False
    try:
        resp = requests.get(
            source.url,
            timeout=getattr(settings, "LITERATURE_HTTP_TIMEOUT", 10),
            headers={"User-Agent": "ResearcherRadar/1.0"},
        )
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        if feed.bozo:
            logger.warning("Feed parser warning for %s: %s", source.name, feed.bozo_exception)
        entries = feed.entries or []
        if feed.bozo and not entries:
            raise ValueError("RSS 内容无法解析")
        feed_loaded = True
        fetched_count = len(entries)
        for entry in entries:
            data = parse_entry(entry, source)
            existing = find_existing_paper(data)
            if existing:
                if existing.content_pruned_at is None:
                    merge_paper_defaults(existing, rss_defaults_for_existing(data, source))
                    score_paper(existing)
                duplicate_count += 1
                checked_count += 1
                continue

            data = enrich_with_crossref(data)
            data = enrich_abstract(data, quick=True)
            matched_keywords, matched_directions = classify_payload_keywords_and_directions(data, source)
            if should_skip_unmatched_article(matched_keywords, matched_directions):
                skipped_unmatched_count += 1
                checked_count += 1
                continue

            paper, created = upsert_paper(data, source)
            if paper.content_pruned_at is None:
                apply_prefetched_matches(paper, matched_keywords, matched_directions)
                score_paper(paper)
            checked_count += 1
            if created:
                new_count += 1
            else:
                duplicate_count += 1
        source.last_fetch_time = timezone.now()
        source.last_fetch_status = "success"
        source.last_fetch_message = f"RSS 返回 {fetched_count} 条，检查 {checked_count} 条，新入库 {new_count} 条，已存在 {duplicate_count} 条"
        if skipped_unmatched_count:
            source.last_fetch_message = f"{source.last_fetch_message}, skipped unmatched {skipped_unmatched_count}"
        source.total_fetched_count += fetched_count
        source.save(update_fields=["last_fetch_time", "last_fetch_status", "last_fetch_message", "total_fetched_count", "updated_at"])
        FetchLog.objects.create(
            source=source,
            source_name=source.name,
            status="success",
            message=source.last_fetch_message,
            fetched_count=fetched_count,
            new_count=new_count,
            duplicate_count=duplicate_count,
        )
        return {
            "status": "success",
            "fetched_count": fetched_count,
            "new_count": new_count,
            "duplicate_count": duplicate_count,
            "skipped_unmatched_count": skipped_unmatched_count,
        }
    except Exception as exc:
        error = traceback.format_exc()
        source.last_fetch_time = timezone.now()
        source.last_fetch_status = "failed"
        source.last_fetch_message = str(exc)
        source.save(update_fields=["last_fetch_time", "last_fetch_status", "last_fetch_message", "updated_at"])
        FetchLog.objects.create(
            source=source,
            source_name=source.name,
            status="failed",
            message=str(exc),
            error_detail=error,
            fetched_count=fetched_count,
            new_count=new_count,
            duplicate_count=duplicate_count,
        )
        logger.exception("RSS source failed: %s", source.name)
        return {
            "status": "failed",
            "fetched_count": fetched_count,
            "new_count": new_count,
            "duplicate_count": duplicate_count,
            "skipped_unmatched_count": skipped_unmatched_count,
            "backup_eligible": not feed_loaded,
        }


def should_skip_unmatched_article(matched_keywords: list, matched_directions: list) -> bool:
    if not getattr(settings, "RSS_INGEST_ONLY_MATCHED", True):
        return False
    return not matched_keywords and not matched_directions


def apply_prefetched_matches(paper: Paper, matched_keywords: list, matched_directions: list) -> None:
    if matched_keywords:
        paper.keywords.set(matched_keywords)
    if matched_directions:
        paper.directions.set(set(matched_directions))


def parse_entry(entry, source: RssSource) -> dict:
    title = clean_text(entry.get("title", ""))
    link = entry.get("link", "")
    summary = clean_text(entry.get("summary", "") or entry.get("description", ""))
    summary_meta = parse_sciencedirect_summary(summary)
    published = entry.get("published") or entry.get("updated") or ""
    authors = join_authors(entry.get("authors") or entry.get("author_detail") or entry.get("author")) or summary_meta.get("authors", "")
    doi = extract_doi(link, summary, title, entry.get("id", ""))
    raw_keywords = "; ".join(tag.get("term", "") for tag in entry.get("tags", []) if tag.get("term"))
    journal = source.journal or summary_meta.get("journal", "") or clean_text(entry.get("publisher", "")) or source.name
    return {
        "title": title,
        "authors": authors,
        "journal": journal,
        "published_date": parse_date(published) or summary_meta.get("published_date"),
        "doi": doi,
        "url": link,
        "abstract": extract_real_abstract(summary),
        "source_name": source.name,
        "source_url": source.url,
        "raw_keywords": raw_keywords,
    }


def extract_real_abstract(summary: str) -> str:
    text = clean_text(summary)
    if not text:
        return ""
    abstract_match = re.search(r"(?:abstract|summary)\s*[:：]\s*(.+)$", text, flags=re.I)
    if abstract_match:
        return clean_text(abstract_match.group(1))
    if looks_like_metadata_summary(text) or looks_like_keyword_list(text):
        return ""
    return text if len(text) >= 120 else ""


def parse_sciencedirect_summary(summary: str) -> dict:
    text = clean_text(summary)
    if not text:
        return {}
    result = {}
    date_match = re.search(r"Publication date:\s*(.*?)(?:\s+Source:|\s+Author\(s\):|$)", text, flags=re.I)
    if date_match:
        result["published_date"] = parse_date(date_match.group(1))
    source_match = re.search(r"Source:\s*(.*?)(?:\s+Author\(s\):|$)", text, flags=re.I)
    if source_match:
        result["journal"] = clean_text(source_match.group(1).split(",")[0])
    authors_match = re.search(r"Author\(s\):\s*(.*)$", text, flags=re.I)
    if authors_match:
        result["authors"] = clean_text(authors_match.group(1))
    return result


def looks_like_metadata_summary(text: str) -> bool:
    lowered = text.lower()
    return (
        lowered.startswith("publication date:")
        or ("source:" in lowered and "author(s):" in lowered)
        or lowered.startswith("source:")
    )


def looks_like_keyword_list(text: str) -> bool:
    if len(text) > 220:
        return False
    separators = text.count(";") + text.count(",")
    return separators >= 3 and not any(mark in text for mark in ".:!?")


def upsert_paper(data: dict, source: RssSource) -> tuple[Paper, bool]:
    existing = find_existing_paper(data)
    dedup_key = Paper.build_dedup_key(
        title=data.get("title", ""),
        journal=data.get("journal", ""),
        published_date=str(data.get("published_date") or ""),
        doi=data.get("doi", ""),
        url=data.get("url", ""),
    )
    defaults = {
        "title": data.get("title", ""),
        "authors": data.get("authors", ""),
        "journal": data.get("journal", ""),
        "published_date": data.get("published_date"),
        "doi": data.get("doi") or None,
        "url": data.get("url", ""),
        "abstract": data.get("abstract", ""),
        "source": source,
        "source_name": data.get("source_name", source.name),
        "source_url": data.get("source_url", source.url),
        "raw_keywords": data.get("raw_keywords", ""),
        "dedup_key": dedup_key,
    }
    if existing:
        if existing.content_pruned_at is None:
            merge_paper_defaults(existing, defaults)
        return existing, False
    try:
        with transaction.atomic():
            paper, created = Paper.objects.get_or_create(dedup_key=dedup_key, defaults=defaults)
            if not created and paper.content_pruned_at is None:
                merge_paper_defaults(paper, defaults)
            return paper, created
    except IntegrityError:
        paper = Paper.objects.get(dedup_key=dedup_key)
        return paper, False


def rss_defaults_for_existing(data: dict, source: RssSource) -> dict:
    return {
        "authors": data.get("authors", ""),
        "journal": data.get("journal", ""),
        "published_date": data.get("published_date"),
        "doi": data.get("doi") or None,
        "url": data.get("url", ""),
        "abstract": data.get("abstract", ""),
        "source": source,
        "source_name": data.get("source_name", source.name),
        "source_url": data.get("source_url", source.url),
        "raw_keywords": data.get("raw_keywords", ""),
    }


def find_existing_paper(data: dict) -> Paper | None:
    """Find duplicates by DOI first, then normalized title.

    RSS URLs can contain changing tracking parameters, and DOI may be enriched
    after the first import. Looking beyond the generated dedup_key prevents the
    same article from entering the literature list twice.
    """
    doi = normalize_doi(data.get("doi", ""))
    title = normalize_space(data.get("title", ""))

    if doi:
        paper = Paper.objects.filter(normalized_doi=doi).order_by("id").first()
        if paper:
            return paper

    if title:
        for paper in Paper.objects.filter(normalized_title_hash=normalized_title_hash(title)).order_by("id"):
            if normalize_space(paper.title).lower() == title.lower():
                return paper
    return None


def merge_paper_defaults(paper: Paper, defaults: dict) -> None:
    if paper.content_pruned_at is not None:
        return
    changed = []
    for key, value in defaults.items():
        if key == "dedup_key":
            continue
        current = getattr(paper, key)
        if value and not current:
            setattr(paper, key, value)
            changed.append(key)
    if changed:
        paper.save(update_fields=changed + ["updated_at"])


def test_feed_url(url: str) -> dict:
    feed = feedparser.parse(url)
    if feed.bozo:
        return {"ok": False, "title": "", "entry_count": 0, "message": str(feed.bozo_exception)}
    return {
        "ok": True,
        "title": feed.feed.get("title", ""),
        "entry_count": len(feed.entries or []),
        "message": "RSS 可访问",
    }
