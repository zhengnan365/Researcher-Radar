from __future__ import annotations

import logging
import time
from difflib import SequenceMatcher

import requests
from django.conf import settings

from .utils import clean_abstract_text, clean_text, first, join_authors, parse_date

logger = logging.getLogger(__name__)
_crossref_retry_at = 0.0
_CROSSREF_COOLDOWN_SECONDS = 300


def enrich_with_crossref(data: dict) -> dict:
    global _crossref_retry_at
    if time.monotonic() < _crossref_retry_at:
        return data
    doi = data.get("doi")
    msg = None
    if not doi:
        msg = search_crossref_by_title(data.get("title", ""), data.get("journal", ""))
        doi = (msg or {}).get("DOI")
        if not msg:
            return data
    else:
        try:
            resp = requests.get(
                f"https://api.crossref.org/works/{doi}",
                timeout=getattr(settings, "LITERATURE_HTTP_TIMEOUT", 10),
                headers={"User-Agent": "ResearcherRadar/1.0"},
            )
            if resp.status_code == 404:
                return data
            resp.raise_for_status()
            msg = resp.json().get("message", {})
        except requests.RequestException as exc:
            _crossref_retry_at = time.monotonic() + _CROSSREF_COOLDOWN_SECONDS
            logger.warning("Crossref metadata lookup unavailable; retrying later: %s", exc)
            return data
        except Exception:
            logger.exception("Crossref metadata lookup failed for doi=%s", doi)
            return data

    if not msg:
        return data

    enriched = dict(data)
    enriched["doi"] = enriched.get("doi") or doi
    enriched["title"] = enriched.get("title") or first(msg.get("title"))
    enriched["authors"] = enriched.get("authors") or join_authors(msg.get("author"))
    enriched["journal"] = enriched.get("journal") or first(msg.get("container-title"))
    enriched["url"] = enriched.get("url") or msg.get("URL", "")
    enriched["published_date"] = enriched.get("published_date") or crossref_date(msg)
    if not enriched.get("abstract") and msg.get("abstract"):
        enriched["abstract"] = clean_abstract_text(msg.get("abstract"))
    subjects = msg.get("subject") or []
    if subjects and not enriched.get("raw_keywords"):
        enriched["raw_keywords"] = "; ".join(subjects)
    return enriched


def search_crossref_by_title(title: str, journal: str = "") -> dict | None:
    global _crossref_retry_at
    if time.monotonic() < _crossref_retry_at:
        return None
    title = clean_text(title)
    if not title:
        return None
    try:
        resp = requests.get(
            "https://api.crossref.org/works",
            params={"query.title": title, "rows": 3, "select": "DOI,title,author,container-title,URL,published-online,published-print,published,issued,abstract,subject"},
            timeout=getattr(settings, "LITERATURE_HTTP_TIMEOUT", 10),
            headers={"User-Agent": "ResearcherRadar/1.0"},
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        _crossref_retry_at = time.monotonic() + _CROSSREF_COOLDOWN_SECONDS
        logger.warning("Crossref title search unavailable; retrying later: %s", exc)
        return None
    except Exception:
        logger.exception("Crossref title search failed for title=%s", title[:120])
        return None
    items = resp.json().get("message", {}).get("items", [])
    for item in items:
        candidate = first(item.get("title"))
        candidate_journal = first(item.get("container-title"))
        if candidate and title_similarity(title, candidate) >= 0.86 and not journal_name_conflict(journal, candidate_journal):
            return item
    return None


def title_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, clean_text(left).lower(), clean_text(right).lower()).ratio()


def journal_name_conflict(left: str, right: str) -> bool:
    left = clean_text(left).lower().replace("sciencedirect publication:", "").strip()
    right = clean_text(right).lower().strip()
    if not left or not right:
        return False
    return left not in right and right not in left


def crossref_date(msg: dict):
    for key in ("published-online", "published-print", "published", "issued"):
        parts = (((msg.get(key) or {}).get("date-parts") or [[]])[0])
        if parts:
            text = "-".join(f"{int(p):02d}" if i else str(p) for i, p in enumerate(parts))
            return parse_date(text)
    return None
