from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import requests
from django.utils import timezone

from ..models import Paper, normalize_doi, normalize_space


ZOTERO_API_BASE = "https://api.zotero.org"


@dataclass
class ZoteroSyncResult:
    scanned_items: int
    matched_papers: int
    marked_imported: int
    suggestions: list[dict[str, Any]]
    zotero_items: list[dict[str, Any]]
    collections: dict[str, str]


def sync_zotero_library(
    *,
    user_id: str = "",
    group_id: str = "",
    api_key: str = "",
    max_items: int = 1000,
    mark_existing: bool = True,
) -> ZoteroSyncResult:
    key = api_key or os.getenv("ZOTERO_API_KEY", "")
    if not key:
        raise ValueError("未配置 ZOTERO_API_KEY 环境变量")
    if not user_id and not group_id:
        user_id = os.getenv("ZOTERO_USER_ID", "")
    if not user_id and not group_id:
        raise ValueError("请提供 Zotero user_id 或 group_id")

    library_path = f"groups/{group_id}" if group_id else f"users/{user_id}"
    headers = {"Zotero-API-Key": key, "Zotero-API-Version": "3"}
    collections = fetch_collections(library_path, headers)
    items = fetch_items(library_path, headers, max_items=max_items)
    match_keys = build_zotero_match_keys(items)

    matched_ids: set[int] = set()
    papers = Paper.objects.prefetch_related("directions", "keywords").filter(content_pruned_at__isnull=True)
    for paper in papers:
        if paper_matches_zotero(paper, match_keys):
            matched_ids.add(paper.id)

    marked = 0
    if mark_existing and matched_ids:
        marked = Paper.objects.filter(id__in=matched_ids, zotero_imported=False).update(
            zotero_imported=True,
            zotero_imported_at=timezone.now(),
            updated_at=timezone.now(),
        )

    suggestions = build_collection_suggestions(papers.exclude(id__in=matched_ids)[:50])
    return ZoteroSyncResult(
        scanned_items=len(items),
        matched_papers=len(matched_ids),
        marked_imported=marked,
        suggestions=suggestions,
        zotero_items=normalize_zotero_items(items[:100], collections),
        collections=collections,
    )


def fetch_collections(library_path: str, headers: dict[str, str]) -> dict[str, str]:
    url = f"{ZOTERO_API_BASE}/{library_path}/collections"
    try:
        response = requests.get(url, headers=headers, params={"limit": 100}, timeout=20)
        response.raise_for_status()
    except requests.RequestException:
        return {}
    result: dict[str, str] = {}
    for row in response.json():
        key = row.get("key", "")
        name = row.get("data", {}).get("name", "")
        if key and name:
            result[key] = name
    return result


def fetch_items(library_path: str, headers: dict[str, str], *, max_items: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0
    limit = 100
    while len(rows) < max_items:
        response = requests.get(
            f"{ZOTERO_API_BASE}/{library_path}/items",
            headers=headers,
            params={"itemType": "-attachment", "limit": limit, "start": start, "format": "json"},
            timeout=30,
        )
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", "3"))
            time.sleep(min(retry_after, 10))
            continue
        response.raise_for_status()
        batch = response.json()
        if not batch:
            break
        rows.extend(batch)
        start += limit
        if len(batch) < limit:
            break
    return rows[:max_items]


def build_zotero_match_keys(items: list[dict[str, Any]]) -> dict[str, set[str]]:
    keys = {"doi": set(), "url": set(), "title": set()}
    for item in items:
        data = item.get("data", {})
        doi = normalize_doi(data.get("DOI") or data.get("doi"))
        url = normalize_url(data.get("url"))
        title = normalize_title(data.get("title"))
        if doi:
            keys["doi"].add(doi)
        if url:
            keys["url"].add(url)
        if title:
            keys["title"].add(title)
    return keys


def normalize_zotero_items(items: list[dict[str, Any]], collections: dict[str, str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        data = item.get("data", {})
        collection_keys = data.get("collections") or []
        rows.append(
            {
                "key": item.get("key", ""),
                "title": data.get("title", ""),
                "doi": normalize_doi(data.get("DOI") or data.get("doi")),
                "journal": data.get("publicationTitle", ""),
                "date": data.get("date", ""),
                "url": data.get("url", ""),
                "collections": [collections.get(key, key) for key in collection_keys],
            }
        )
    return rows


def paper_matches_zotero(paper: Paper, keys: dict[str, set[str]]) -> bool:
    doi = normalize_doi(paper.doi)
    if doi and doi in keys["doi"]:
        return True
    url = normalize_url(paper.url)
    if url and url in keys["url"]:
        return True
    title = normalize_title(paper.title)
    return bool(title and title in keys["title"])


def build_collection_suggestions(papers) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    for paper in papers:
        direction_names = [item.name for item in paper.directions.all()]
        keyword_names = [item.keyword for item in paper.keywords.all()[:4]]
        collection = direction_names[0] if direction_names else infer_collection_from_text(paper)
        suggestions.append(
            {
                "paper_id": paper.id,
                "title": paper.title,
                "doi": paper.doi,
                "journal": paper.journal or paper.source_name,
                "suggested_collection": collection,
                "reason": "研究方向匹配" if direction_names else "关键词/标题推断",
                "matched_terms": direction_names or keyword_names,
            }
        )
    return suggestions


def infer_collection_from_text(paper: Paper) -> str:
    text = f"{paper.title} {paper.abstract} {paper.raw_keywords}".lower()
    rules = [
        ("燃料电池与电解池", ["fuel cell", "sofc", "pemfc", "electrolyzer", "electrolysis"]),
        ("储能技术与能源系统灵活性", ["battery", "storage", "thermal energy storage"]),
        ("氢能系统", ["hydrogen", "power-to-gas"]),
        ("新能源系统", ["renewable", "solar", "wind", "distributed energy"]),
        ("碳捕集与低碳", ["carbon", "co2", "emission", "low-carbon"]),
    ]
    for name, terms in rules:
        if any(term in text for term in terms):
            return name
    return "待分类文献"


def normalize_url(value: str | None) -> str:
    return str(value or "").strip().lower().removesuffix("/")


def normalize_title(value: str | None) -> str:
    return normalize_space(value).lower()
