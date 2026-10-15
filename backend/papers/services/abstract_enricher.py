from __future__ import annotations

import logging
import os
import time
from difflib import SequenceMatcher
from xml.etree import ElementTree

import requests
from django.conf import settings

from .openalex_client import OpenAlexRateLimitError, request_openalex
from .utils import clean_abstract_text, clean_text

logger = logging.getLogger(__name__)
_quick_openalex_retry_at = 0.0
_QUICK_OPENALEX_COOLDOWN_SECONDS = 300
_semantic_retry_at = 0.0
_elsevier_retry_at = 0.0
_crossref_abstract_retry_at = 0.0


def _cooldown_seconds(response, default: int = 300) -> int:
    try:
        return max(1, min(86400, int(float(response.headers.get("Retry-After", default)))))
    except (TypeError, ValueError):
        return default


def _semantic_headers() -> dict[str, str]:
    key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "").strip()
    return {"x-api-key": key} if key else {}


def enrich_abstract(data: dict, *, quick: bool = False) -> dict:
    if data.get("abstract"):
        return data
    if quick:
        return enrich_abstract_quickly(data)
    if not data.get("doi"):
        return enrich_abstract_by_title(data)
    for fetcher in (fetch_crossref_abstract, fetch_elsevier_abstract, fetch_openalex_abstract, fetch_semantic_scholar_abstract, fetch_pubmed_abstract):
        try:
            abstract = fetcher(data["doi"])
        except Exception:
            logger.exception("Abstract lookup failed via %s for doi=%s", fetcher.__name__, data.get("doi"))
            continue
        if abstract:
            enriched = dict(data)
            enriched["abstract"] = abstract
            return enriched
    return enrich_abstract_by_title(data)


def enrich_abstract_quickly(data: dict) -> dict:
    global _quick_openalex_retry_at
    doi = data.get("doi")
    if not doi or time.monotonic() < _quick_openalex_retry_at:
        return data
    try:
        abstract = fetch_openalex_abstract(doi, timeout=3)
    except requests.RequestException as exc:
        _quick_openalex_retry_at = time.monotonic() + _QUICK_OPENALEX_COOLDOWN_SECONDS
        logger.warning("OpenAlex quick abstract lookup unavailable; retrying later: %s", exc)
        return data
    if not abstract:
        return data
    enriched = dict(data)
    enriched["abstract"] = abstract
    return enriched


def enrich_abstract_by_title(data: dict) -> dict:
    for fetcher in (fetch_openalex_title_abstract, fetch_semantic_scholar_title_abstract):
        try:
            abstract = fetcher(data.get("title", ""))
        except Exception:
            logger.exception("Abstract title lookup failed via %s for title=%s", fetcher.__name__, data.get("title", "")[:120])
            continue
        if abstract:
            enriched = dict(data)
            enriched["abstract"] = abstract
            return enriched
    return data


def fetch_openalex_title_abstract(title: str) -> str:
    title = clean_text(title)
    if not title:
        return ""
    try:
        resp = request_openalex("https://api.openalex.org/works", params={"search": title, "per-page": 1})
    except OpenAlexRateLimitError:
        return ""
    resp.raise_for_status()
    results = resp.json().get("results") or []
    if not results:
        return ""
    result = results[0]
    if title_similarity(title, result.get("title", "")) < 0.82:
        return ""
    return restore_inverted_abstract(result.get("abstract_inverted_index"))


def fetch_semantic_scholar_title_abstract(title: str) -> str:
    global _semantic_retry_at
    title = clean_text(title)
    if not title or time.monotonic() < _semantic_retry_at:
        return ""
    try:
        resp = requests.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={"query": title, "limit": 1, "fields": "title,abstract"},
            headers=_semantic_headers(),
            timeout=getattr(settings, "LITERATURE_HTTP_TIMEOUT", 10),
        )
    except requests.RequestException as exc:
        _semantic_retry_at = time.monotonic() + 300
        logger.warning("Semantic Scholar title lookup unavailable: %s", exc)
        return ""
    if resp.status_code == 429:
        _semantic_retry_at = time.monotonic() + _cooldown_seconds(resp)
        return ""
    try:
        resp.raise_for_status()
    except requests.RequestException as exc:
        _semantic_retry_at = time.monotonic() + 300
        logger.warning("Semantic Scholar title lookup unavailable: %s", exc)
        return ""
    data = resp.json().get("data") or []
    if not data:
        return ""
    if title_similarity(title, data[0].get("title", "")) < 0.82:
        return ""
    return clean_abstract_text(data[0].get("abstract"))


def fetch_openalex_abstract(doi: str, *, timeout: int | None = None) -> str:
    try:
        resp = request_openalex(f"https://api.openalex.org/works/https://doi.org/{doi}", timeout=timeout)
    except OpenAlexRateLimitError:
        return ""
    if resp.status_code == 404:
        return ""
    resp.raise_for_status()
    return restore_inverted_abstract(resp.json().get("abstract_inverted_index"))


def fetch_semantic_scholar_abstract(doi: str) -> str:
    global _semantic_retry_at
    if time.monotonic() < _semantic_retry_at:
        return ""
    try:
        resp = requests.get(
            f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}",
            params={"fields": "abstract"},
            headers=_semantic_headers(),
            timeout=getattr(settings, "LITERATURE_HTTP_TIMEOUT", 10),
        )
    except requests.RequestException as exc:
        _semantic_retry_at = time.monotonic() + 300
        logger.warning("Semantic Scholar abstract lookup unavailable: %s", exc)
        return ""
    if resp.status_code == 429:
        _semantic_retry_at = time.monotonic() + _cooldown_seconds(resp)
        return ""
    if resp.status_code == 404:
        return ""
    try:
        resp.raise_for_status()
    except requests.RequestException as exc:
        _semantic_retry_at = time.monotonic() + 300
        logger.warning("Semantic Scholar abstract lookup unavailable: %s", exc)
        return ""
    return clean_abstract_text(resp.json().get("abstract"))


def fetch_pubmed_abstract(doi: str) -> str:
    search = requests.get(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
        params={"db": "pubmed", "term": f"{doi}[doi]", "retmode": "json"},
        timeout=getattr(settings, "LITERATURE_HTTP_TIMEOUT", 10),
    )
    search.raise_for_status()
    ids = search.json().get("esearchresult", {}).get("idlist", [])
    if not ids:
        return ""
    fetch = requests.get(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
        params={"db": "pubmed", "id": ids[0], "retmode": "xml"},
        timeout=getattr(settings, "LITERATURE_HTTP_TIMEOUT", 10),
    )
    fetch.raise_for_status()
    root = ElementTree.fromstring(fetch.content)
    parts = [" ".join(node.itertext()) for node in root.findall(".//AbstractText")]
    return clean_abstract_text(" ".join(parts))


def fetch_crossref_abstract(doi: str) -> str:
    global _crossref_abstract_retry_at
    if time.monotonic() < _crossref_abstract_retry_at:
        return ""
    mailto = os.getenv("CROSSREF_MAILTO", "").strip()
    try:
        resp = requests.get(
            f"https://api.crossref.org/works/{doi}",
            params={"mailto": mailto} if mailto else None,
            headers={"User-Agent": f"ResearcherRadar/1.0 (mailto:{mailto})" if mailto else "ResearcherRadar/1.0"},
            timeout=getattr(settings, "LITERATURE_HTTP_TIMEOUT", 10),
        )
    except requests.RequestException as exc:
        _crossref_abstract_retry_at = time.monotonic() + 300
        logger.warning("Crossref abstract lookup unavailable: %s", exc)
        return ""
    if resp.status_code == 429:
        _crossref_abstract_retry_at = time.monotonic() + _cooldown_seconds(resp)
        return ""
    if resp.status_code == 404:
        return ""
    try:
        resp.raise_for_status()
    except requests.RequestException as exc:
        _crossref_abstract_retry_at = time.monotonic() + 300
        logger.warning("Crossref abstract lookup unavailable: %s", exc)
        return ""
    return clean_abstract_text(resp.json().get("message", {}).get("abstract"))


def fetch_elsevier_abstract(doi: str) -> str:
    """Optional DOI fallback; the key must have ScienceDirect API entitlement."""
    global _elsevier_retry_at
    key = os.getenv("ELSEVIER_API_KEY", "").strip()
    if not key or not doi.lower().startswith("10.1016/") or time.monotonic() < _elsevier_retry_at:
        return ""
    try:
        resp = requests.get(
            f"https://api.elsevier.com/content/article/doi/{doi}",
            params={"view": "META_ABS"},
            headers={"X-ELS-APIKey": key, "Accept": "application/json"},
            timeout=getattr(settings, "LITERATURE_HTTP_TIMEOUT", 10),
        )
    except requests.RequestException as exc:
        _elsevier_retry_at = time.monotonic() + 300
        logger.warning("Elsevier abstract lookup unavailable: %s", exc)
        return ""
    if resp.status_code in {401, 403, 429}:
        # Invalid credentials, missing entitlement, and quota exhaustion should
        # not cause one failed request per paper in a batch update.
        _elsevier_retry_at = time.monotonic() + (86400 if resp.status_code in {401, 403} else _cooldown_seconds(resp))
        logger.warning("Elsevier abstract lookup unavailable (HTTP %s)", resp.status_code)
        return ""
    if resp.status_code == 404:
        return ""
    try:
        resp.raise_for_status()
    except requests.RequestException as exc:
        _elsevier_retry_at = time.monotonic() + 300
        logger.warning("Elsevier abstract lookup unavailable: %s", exc)
        return ""
    payload = resp.json()
    content = payload.get("full-text-retrieval-response") or payload.get("abstracts-retrieval-response") or {}
    core = content.get("coredata") or {}
    return clean_abstract_text(core.get("dc:description") or content.get("dc:description"))


def restore_inverted_abstract(index: dict[str, list[int]] | None) -> str:
    if not index:
        return ""
    positioned = []
    for word, positions in index.items():
        positioned.extend((pos, word) for pos in positions)
    return " ".join(word for _, word in sorted(positioned))


def title_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, clean_text(left).lower(), clean_text(right).lower()).ratio()
