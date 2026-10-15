from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
from datetime import timedelta
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone

from ..models import (
    Paper,
    ZoteroCollection,
    ZoteroConfig,
    ZoteroItem,
    ZoteroSyncState,
    normalize_doi,
    normalize_space,
)
from .task_lock import task_start_lock

logger = logging.getLogger(__name__)
ZOTERO_BATCH_SIZE = int(os.getenv("ZOTERO_BATCH_SIZE", "50"))
ZOTERO_SYNC_STALE_SECONDS = int(os.getenv("ZOTERO_SYNC_STALE_SECONDS", "3600"))
_zotero_sync_lock = threading.Lock()


def get_zotero_client(*, user_id: str = "", group_id: str = "", api_key: str = ""):
    try:
        from pyzotero import zotero
    except ImportError as exc:
        raise RuntimeError("未安装 pyzotero，请先执行 pip install -r requirements.txt") from exc

    config = ZoteroConfig.get_active()
    key = api_key or (config.api_key if config else "") or os.getenv("ZOTERO_API_KEY", "")
    if not key:
        raise ValueError("未配置 Zotero Access Key，请先到 系统管理 > Zotero 设置 保存")

    configured_group_id = group_id or (config.group_id if config and config.library_type == "group" else "")
    if configured_group_id:
        return zotero.Zotero(str(configured_group_id), "group", key)

    library_id = user_id or (config.user_id if config else "") or os.getenv("ZOTERO_USER_ID", "")
    if not library_id:
        raise ValueError("未配置 Zotero User ID，请先到 系统管理 > Zotero 设置 保存")
    return zotero.Zotero(str(library_id), "user", key)


def read_zotero_library(
    *,
    user_id: str = "",
    group_id: str = "",
    max_items: int = 1000,
    refresh: bool = True,
    full_sync: bool = False,
    background: bool = False,
    include_items: bool = True,
) -> dict[str, Any]:
    sync_error = ""
    sync_state = ZoteroSyncState.objects.filter(name="default").first()
    cache_missing = not sync_state or (
        sync_state.sync_status in {"idle", "success"}
        and (
            not sync_state.last_synced_at
            or (sync_state.item_count > 0 and not ZoteroItem.objects.exists())
            or (sync_state.collection_count > 0 and not ZoteroCollection.objects.exists())
        )
    )
    if background and refresh:
        sync_started = start_zotero_sync_background(user_id=user_id, group_id=group_id, max_items=max_items, full_sync=full_sync)
        payload = read_zotero_library_from_db(max_items=max_items, include_items=include_items)
        payload["sync_started"] = sync_started
        payload["sync_already_running"] = not sync_started
        return payload

    if not refresh and cache_missing:
        sync_started = start_zotero_sync_background(user_id=user_id, group_id=group_id, max_items=max_items, full_sync=True)
        payload = read_zotero_library_from_db(max_items=max_items, include_items=include_items)
        payload["sync_started"] = sync_started
        payload["sync_already_running"] = not sync_started
        return payload

    if refresh:
        try:
            sync_zotero_library_to_db(user_id=user_id, group_id=group_id, max_items=max_items, full_sync=full_sync)
        except Exception as exc:
            sync_error = str(exc)
            if not ZoteroItem.objects.exists():
                raise
    payload = read_zotero_library_from_db(max_items=max_items, include_items=include_items)
    if sync_error:
        payload["sync_error"] = sync_error
    return payload


def start_zotero_sync_background(*, user_id: str = "", group_id: str = "", max_items: int = 1000, full_sync: bool = False) -> bool:
    if not _zotero_sync_lock.acquire(blocking=False):
        return False

    with task_start_lock():
        state, _ = ZoteroSyncState.objects.get_or_create(name="default")
        current_status = get_zotero_sync_status(state=state)
        if current_status["status"] == "running":
            _zotero_sync_lock.release()
            return False

        now = timezone.now()
        mode = "full" if full_sync else "quick"
        claimed = ZoteroSyncState.objects.filter(pk=state.pk).exclude(sync_status="running").update(
            sync_status="running",
            sync_mode=mode,
            sync_started_at=now,
            sync_finished_at=None,
            sync_error="",
            updated_at=now,
        )
        if not claimed:
            _zotero_sync_lock.release()
            return False

    def runner() -> None:
        try:
            sync_zotero_library_to_db(user_id=user_id, group_id=group_id, max_items=max_items, full_sync=full_sync)
        except Exception as exc:
            logger.exception("Zotero background sync failed")
            finished_at = timezone.now()
            ZoteroSyncState.objects.filter(name="default").update(
                sync_status="failed",
                sync_finished_at=finished_at,
                sync_error=str(exc)[:4000],
                updated_at=finished_at,
            )
        else:
            finished_at = timezone.now()
            ZoteroSyncState.objects.filter(name="default").update(
                sync_status="success",
                sync_finished_at=finished_at,
                sync_error="",
                updated_at=finished_at,
            )
        finally:
            _zotero_sync_lock.release()

    thread = threading.Thread(target=runner, name="zotero-sync", daemon=True)
    thread.start()
    return True


def get_zotero_sync_status(*, state: ZoteroSyncState | None = None) -> dict[str, Any]:
    state = state or ZoteroSyncState.objects.filter(name="default").first()
    if not state:
        return {
            "status": "idle",
            "mode": "quick",
            "started_at": "",
            "finished_at": "",
            "error": "",
            "item_count": ZoteroItem.objects.count(),
            "collection_count": ZoteroCollection.objects.count(),
            "library_version": 0,
            "last_synced_at": "",
        }

    if (
        state.sync_status == "running"
        and state.sync_started_at
        and state.sync_started_at < timezone.now() - timedelta(seconds=ZOTERO_SYNC_STALE_SECONDS)
    ):
        finished_at = timezone.now()
        state.sync_status = "failed"
        state.sync_finished_at = finished_at
        state.sync_error = "同步任务运行超时或后端进程已重启，请重新发起同步。"
        state.save(update_fields=["sync_status", "sync_finished_at", "sync_error", "updated_at"])

    return {
        "status": state.sync_status,
        "mode": state.sync_mode,
        "started_at": state.sync_started_at.isoformat() if state.sync_started_at else "",
        "finished_at": state.sync_finished_at.isoformat() if state.sync_finished_at else "",
        "error": state.sync_error,
        "item_count": state.item_count,
        "collection_count": state.collection_count,
        "library_version": state.library_version,
        "last_synced_at": state.last_synced_at.isoformat() if state.last_synced_at else "",
    }


def sync_zotero_library_to_db(
    *,
    user_id: str = "",
    group_id: str = "",
    max_items: int = 1000,
    full_sync: bool = False,
) -> dict[str, int]:
    zot = get_zotero_client(user_id=user_id, group_id=group_id)
    state, _ = ZoteroSyncState.objects.get_or_create(name="default")
    backfill_zotero_identity_keys()
    cleanup_zotero_identity_duplicates()
    current_version = int(zot.last_modified_version())
    first_sync = (
        not state.last_synced_at
        or (state.item_count > 0 and not ZoteroItem.objects.exists())
        or (state.collection_count > 0 and not ZoteroCollection.objects.exists())
    )
    force_full_sync = full_sync or first_sync

    if force_full_sync:
        collections_raw = fetch_zotero_rows(zot, zot.collections, max_rows=1000)
        items_raw = fetch_zotero_rows(zot, zot.items, max_rows=0, itemType="-attachment")
    else:
        since = max(int(state.library_version or 0), 0)
        if since >= current_version:
            reconcile_paper_zotero_statuses()
            state.last_synced_at = timezone.now()
            state.save(update_fields=["last_synced_at", "updated_at"])
            return {
                "library_version": state.library_version,
                "item_count": state.item_count,
                "collection_count": state.collection_count,
            }
        apply_deleted_zotero_rows(zot.deleted(since=since))
        collection_versions = zot.collection_versions(since=since) if since else {}
        item_versions = zot.item_versions(since=since) if since else {}
        collections_raw = [zot.collection(key) for key in collection_versions.keys()]
        items_raw = fetch_zotero_items_by_keys(zot, list(item_versions.keys()))

    collections = normalize_collections(collections_raw)
    upsert_zotero_collections(collections_raw, collections)

    items = normalize_items(items_raw, collections)
    upsert_zotero_items(items_raw, items)
    if force_full_sync:
        delete_missing_zotero_cache(collections_raw=collections_raw, items_raw=items_raw)
    cleanup_zotero_identity_duplicates()
    refresh_collection_counts()
    reconcile_paper_zotero_statuses()

    state.library_version = current_version
    state.item_count = ZoteroItem.objects.count()
    state.collection_count = ZoteroCollection.objects.count()
    state.last_synced_at = timezone.now()
    state.save(update_fields=["library_version", "item_count", "collection_count", "last_synced_at", "updated_at"])

    return {
        "library_version": state.library_version,
        "item_count": state.item_count,
        "collection_count": state.collection_count,
    }


def sync_zotero_collections_incremental(*, user_id: str = "", group_id: str = "") -> dict[str, int]:
    """Refresh only Zotero collections before an import dialog opens.

    This keeps the collection picker current without scanning thousands of
    items. It deliberately does not advance the global library version, so a
    later item sync cannot miss item changes that happened in the same window.
    """
    zot = get_zotero_client(user_id=user_id, group_id=group_id)
    state, _ = ZoteroSyncState.objects.get_or_create(name="default")
    since = max(int(state.library_version or 0), 0)

    if not since or not ZoteroCollection.objects.exists():
        collections_raw = fetch_zotero_rows(zot, zot.collections, max_rows=1000)
    else:
        collection_versions = zot.collection_versions(since=since) or {}
        collections_raw = [zot.collection(key) for key in collection_versions.keys()]
        deleted = zot.deleted(since=since)
        collection_keys = normalize_deleted_keys((deleted or {}).get("collections") or [])
        if collection_keys:
            ZoteroCollection.objects.filter(key__in=collection_keys).delete()

    collections = normalize_collections(collections_raw)
    upsert_zotero_collections(collections_raw, collections)
    refresh_collection_counts()

    state.collection_count = ZoteroCollection.objects.count()
    state.last_synced_at = timezone.now()
    state.save(update_fields=["collection_count", "last_synced_at", "updated_at"])
    return {
        "library_version": state.library_version,
        "collection_count": state.collection_count,
    }


def zotero_item_year(value: str) -> str:
    match = re.search(r"(?:18|19|20|21)\d{2}", str(value or ""))
    return match.group(0) if match else ""


def zotero_date_sort_key(value: str) -> tuple[int, str]:
    text = str(value or "").strip()
    normalized = re.sub(r"[年月./]", "-", text).replace("日", "")
    match = re.match(r"^(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?", normalized)
    if not match:
        return (-1, text.casefold())
    return (int(match[1]) * 10000 + int(match[2] or 1) * 100 + int(match[3] or 1), text.casefold())


def zotero_library_facets() -> dict[str, Any]:
    direct_keys: dict[str, set[str]] = {}
    uncategorized_count = 0
    years: set[str] = set()
    types: set[str] = set()
    for item_key, date, item_type, item_collections in ZoteroItem.objects.values_list(
        "key", "date", "item_type", "collections"
    ).iterator():
        year = zotero_item_year(date)
        if year:
            years.add(year)
        if item_type:
            types.add(item_type)
        keys = {entry.get("key") for entry in (item_collections or []) if isinstance(entry, dict) and entry.get("key")}
        if not keys:
            uncategorized_count += 1
        for key in keys:
            direct_keys.setdefault(key, set()).add(item_key)

    collections = build_collection_payload()
    children: dict[str, list[str]] = {}
    for collection in collections:
        children.setdefault(collection["parent"], []).append(collection["key"])

    def descendants(key: str, seen: set[str]) -> set[str]:
        if key in seen:
            return set()
        seen.add(key)
        result = set(direct_keys.get(key, set()))
        for child in children.get(key, []):
            result.update(descendants(child, seen))
        return result

    counts = {row["key"]: len(descendants(row["key"], set())) for row in collections}
    return {
        "collection_counts": counts,
        "uncategorized_count": uncategorized_count,
        "available_years": sorted(years, reverse=True),
        "available_types": sorted(types, key=str.casefold),
    }


def read_zotero_library_page(
    *, collection_key: str = "__all__", search: str = "", year: str = "",
    item_type: str = "", sort_by: str = "title", sort_order: str = "ascending",
    page: int = 1, page_size: int = 100,
) -> dict[str, Any]:
    if page < 1 or not 1 <= page_size <= 200:
        raise ValueError("无效的页码或每页条数")
    if sort_by not in {"title", "creator", "date", "journal"} or sort_order not in {"ascending", "descending"}:
        raise ValueError("无效的排序条件")
    if year and not re.fullmatch(r"(?:18|19|20|21)\d{2}", year):
        raise ValueError("无效的年份")

    queryset = ZoteroItem.objects.all()
    if collection_key != "__all__" or year:
        collections = list(ZoteroCollection.objects.values_list("key", "parent_key"))
        known_keys = {key for key, _ in collections}
        if collection_key not in {"__all__", "uncategorized"} and collection_key not in known_keys:
            raise ValueError("文件夹不存在")
        descendants = {collection_key}
        changed = True
        while changed:
            before = len(descendants)
            descendants.update(key for key, parent in collections if parent in descendants)
            changed = len(descendants) != before
        matching_keys = []
        folder_total = 0
        for key, date, item_collections in ZoteroItem.objects.values_list("key", "date", "collections").iterator():
            keys = {entry.get("key") for entry in (item_collections or []) if isinstance(entry, dict)}
            in_collection = (
                collection_key == "__all__"
                or (not keys if collection_key == "uncategorized" else bool(keys & descendants))
            )
            if in_collection:
                folder_total += 1
                if not year or zotero_item_year(date) == year:
                    matching_keys.append(key)
        queryset = queryset.filter(key__in=matching_keys)
    else:
        folder_total = queryset.count()
    if item_type:
        queryset = queryset.filter(item_type=item_type)
    search = search.strip()
    if search:
        queryset = queryset.filter(Q(title__icontains=search) | Q(creator__icontains=search) | Q(doi__icontains=search))
    total = queryset.count()
    page = min(page, max(1, (total + page_size - 1) // page_size))
    start = (page - 1) * page_size
    if sort_by == "date":
        dates = list(queryset.values_list("key", "date"))
        dates.sort(key=lambda row: (zotero_date_sort_key(row[1]), row[0]), reverse=sort_order == "descending")
        keys = [key for key, _ in dates[start:start + page_size]]
        by_key = {row.key: row for row in queryset.filter(key__in=keys).only(
            "key", "title", "creator", "doi", "journal", "date", "item_type", "collections"
        )}
        rows = [by_key[key] for key in keys]
    else:
        direction = "-" if sort_order == "descending" else ""
        rows = queryset.only("key", "title", "creator", "doi", "journal", "date", "item_type", "collections").alias(
            sort_value=Lower(sort_by)
        ).order_by(f"{direction}sort_value", "key")[start:start + page_size]
    return {"items": [zotero_item_to_summary(row) for row in rows], "total": total,
            "folder_total": folder_total, "page": page, "page_size": page_size}


def read_zotero_library_from_db(*, max_items: int = 1000, include_items: bool = True) -> dict[str, Any]:
    collections = build_collection_payload()
    queryset = ZoteroItem.objects.only(
        "key",
        "title",
        "creator",
        "doi",
        "journal",
        "date",
        "item_type",
        "collections",
    ).order_by("title")
    if max_items > 0:
        queryset = queryset[:max_items]
    items = [zotero_item_to_summary(row) for row in queryset] if include_items else []
    state = ZoteroSyncState.objects.filter(name="default").first()
    return {
        "collections": collections,
        "items": items,
        "total_items": len(items) if include_items else ZoteroItem.objects.count(),
        "cached_total_items": ZoteroItem.objects.count(),
        "library_version": state.library_version if state else 0,
        "last_synced_at": state.last_synced_at.isoformat() if state and state.last_synced_at else "",
        "sync_state": get_zotero_sync_status(state=state),
        **(zotero_library_facets() if not include_items else {}),
    }


def create_zotero_collection(
    *,
    name: str,
    parent_key: str = "",
    user_id: str = "",
    group_id: str = "",
) -> dict[str, Any]:
    name = normalize_space(name)
    parent_key = normalize_space(parent_key)
    if not name:
        raise ValueError("请输入文件夹名称")

    existing = ZoteroCollection.objects.filter(name=name, parent_key=parent_key).first()
    if existing:
        collection = collection_payload_for_key(existing.key)
        return {
            "created": False,
            "message": "同一父文件夹下已存在同名文件夹",
            "collection": collection,
        }

    zot = get_zotero_client(user_id=user_id, group_id=group_id)
    payload: dict[str, Any] = {"name": name}
    if parent_key:
        payload["parentCollection"] = parent_key

    result = zot.create_collections([payload])
    created_key = str((result.get("success") or {}).get("0", "")).strip()
    if not created_key:
        raise ValueError(f"Zotero 创建文件夹失败：{result}")

    try:
        raw = zot.collection(created_key)
    except Exception:
        raw = {
            "key": created_key,
            "version": 0,
            "data": {
                "key": created_key,
                "name": name,
                "parentCollection": parent_key,
            },
        }

    normalized = normalize_collections([raw])
    upsert_zotero_collections([raw], normalized)
    refresh_collection_counts()
    state, _ = ZoteroSyncState.objects.get_or_create(name="default")
    state.collection_count = ZoteroCollection.objects.count()
    state.last_synced_at = timezone.now()
    state.save(update_fields=["collection_count", "last_synced_at", "updated_at"])

    return {
        "created": True,
        "server_synced": True,
        "message": "文件夹创建成功",
        "collection": collection_payload_for_key(created_key),
        "zotero_result": result,
    }


def collection_payload_for_key(key: str) -> dict[str, Any]:
    for row in build_collection_payload():
        if row["key"] == key:
            return row
    return {}


def build_collection_payload() -> list[dict[str, Any]]:
    rows = list(ZoteroCollection.objects.all().order_by("name"))
    by_key = {row.key: row for row in rows}

    def build_path(row: ZoteroCollection) -> str:
        names = [row.name]
        parent_key = row.parent_key
        visited = {row.key}
        while parent_key and parent_key in by_key and parent_key not in visited:
            parent = by_key[parent_key]
            names.append(parent.name)
            visited.add(parent.key)
            parent_key = parent.parent_key
        return " / ".join(reversed(names))

    payload = []
    for row in rows:
        path = build_path(row)
        depth = max(path.count(" / "), 0)
        payload.append(
            {
                "key": row.key,
                "name": row.name,
                "parent": row.parent_key,
                "path": path,
                "label": path,
                "depth": depth,
                "item_count": row.item_count,
            }
        )
    return payload


def fetch_zotero_rows(zot, query_func, *, max_rows: int, **kwargs) -> list[dict[str, Any]]:
    """Read a bounded number of Zotero rows.

    Pyzotero's ``everything()`` deliberately ignores ``limit`` and reads all
    pages, which is too slow for large libraries. This helper keeps UI reads
    responsive by fetching only the requested pages.
    """
    rows: list[dict[str, Any]] = []
    unbounded = max_rows <= 0
    limit = 100 if unbounded else min(max(max_rows, 1), 100)
    start = 0
    while unbounded or len(rows) < max_rows:
        batch = query_func(start=start, limit=limit, **kwargs)
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < limit:
            break
        start += limit
    return rows if unbounded else rows[:max_rows]


def fetch_zotero_items_by_keys(zot, item_keys: list[str]) -> list[dict[str, Any]]:
    """Fetch changed Zotero items in batches.

    Fetching each item with ``zot.item(key)`` is very slow for libraries with
    many changed items and often trips production proxy timeouts. Zotero's API
    accepts an ``itemKey`` comma-separated filter on ``items``; pyzotero passes
    it through to the API.
    """
    keys = [str(key).strip() for key in item_keys if str(key).strip()]
    if not keys:
        return []

    rows: list[dict[str, Any]] = []
    batch_size = max(1, min(ZOTERO_BATCH_SIZE, 50))
    for batch in chunked(keys, batch_size):
        try:
            rows.extend(zot.items(itemKey=",".join(batch), itemType="-attachment", limit=len(batch)))
        except Exception as exc:
            logger.warning("Zotero batch item fetch failed; falling back to single-item fetch: %s", exc)
            for key in batch:
                try:
                    row = zot.item(key)
                    data = row.get("data", {}) if isinstance(row, dict) else {}
                    if (data.get("itemType") or "").lower() != "attachment":
                        rows.append(row)
                except Exception:
                    logger.exception("Zotero single item fetch failed for key=%s", key)
    return rows


def chunked(values: list[str], size: int) -> list[list[str]]:
    return [values[index:index + size] for index in range(0, len(values), size)]


def upsert_zotero_collections(raw_rows: list[dict[str, Any]], normalized: dict[str, dict[str, Any]]) -> None:
    raw_by_key = {}
    for row in raw_rows:
        data = row.get("data", {})
        key = data.get("key") or row.get("key", "")
        if key:
            raw_by_key[key] = row
    for key, item in normalized.items():
        raw = raw_by_key.get(key, {})
        ZoteroCollection.objects.update_or_create(
            key=key,
            defaults={
                "name": item.get("name", ""),
                "parent_key": item.get("parent", ""),
                "zotero_version": int(raw.get("version") or raw.get("data", {}).get("version") or 0),
                "raw": raw,
            },
        )


def upsert_zotero_items(raw_rows: list[dict[str, Any]], normalized: list[dict[str, Any]]) -> None:
    raw_by_key = {}
    for row in raw_rows:
        data = row.get("data", {})
        key = data.get("key") or row.get("key", "")
        if key:
            raw_by_key[key] = row
    for item in normalized:
        raw = raw_by_key.get(item["key"], {})
        identity_key = build_zotero_identity_key(item)
        defaults = zotero_item_defaults(item, raw, identity_key)
        save_zotero_item_by_identity(item["key"], identity_key, defaults)


def delete_missing_zotero_cache(*, collections_raw: list[dict[str, Any]], items_raw: list[dict[str, Any]]) -> None:
    """During full sync, make the local cache match Zotero Web API state."""
    item_keys = {extract_zotero_key(row) for row in items_raw}
    item_keys.discard("")
    collection_keys = {extract_zotero_key(row) for row in collections_raw}
    collection_keys.discard("")
    if item_keys:
        ZoteroItem.objects.exclude(key__in=item_keys).delete()
    if collection_keys:
        ZoteroCollection.objects.exclude(key__in=collection_keys).delete()


def extract_zotero_key(row: dict[str, Any]) -> str:
    data = row.get("data", {}) if isinstance(row, dict) else {}
    return str(data.get("key") or row.get("key", "")).strip()


def apply_deleted_zotero_rows(deleted: dict[str, Any] | None) -> None:
    """Apply Zotero Web API deletion feed since the previous library version."""
    if not deleted:
        return
    item_keys = normalize_deleted_keys(deleted.get("items") or deleted.get("top") or [])
    collection_keys = normalize_deleted_keys(deleted.get("collections") or [])
    if item_keys:
        ZoteroItem.objects.filter(key__in=item_keys).delete()
    if collection_keys:
        ZoteroCollection.objects.filter(key__in=collection_keys).delete()


def normalize_deleted_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        value = value.keys()
    for item in value or []:
        if isinstance(item, str):
            key = item
        elif isinstance(item, dict):
            key = extract_zotero_key(item)
        else:
            key = ""
        if key:
            keys.add(key)
    return keys


def reconcile_paper_zotero_statuses() -> dict[str, int]:
    """Keep Paper.zotero_imported consistent with the synced Zotero cache."""
    items_by_identity = {
        item.identity_key: item
        for item in ZoteroItem.objects.exclude(identity_key="").only(
            "id",
            "identity_key",
            "collections",
        )
    }
    changed = 0
    marked_imported = 0
    marked_unimported = 0
    collection_payload = {row["key"]: row for row in build_collection_payload()}

    for paper in Paper.objects.filter(content_pruned_at__isnull=True).only(
        "id",
        "title",
        "doi",
        "zotero_imported",
        "zotero_imported_at",
        "zotero_collection_key",
        "zotero_collection_name",
    ):
        zotero_item = find_zotero_item_for_paper_from_map(paper, items_by_identity)
        update_fields: list[str] = []

        if zotero_item:
            collection_key, collection_name = preferred_collection_for_paper(paper, zotero_item, collection_payload)
            if not paper.zotero_imported:
                paper.zotero_imported = True
                paper.zotero_imported_at = timezone.now()
                update_fields.extend(["zotero_imported", "zotero_imported_at"])
                marked_imported += 1
            if paper.zotero_collection_key != collection_key:
                paper.zotero_collection_key = collection_key
                update_fields.append("zotero_collection_key")
            if paper.zotero_collection_name != collection_name:
                paper.zotero_collection_name = collection_name
                update_fields.append("zotero_collection_name")
        elif paper.zotero_imported:
            paper.zotero_imported = False
            paper.zotero_imported_at = None
            paper.zotero_collection_key = ""
            paper.zotero_collection_name = ""
            update_fields.extend([
                "zotero_imported",
                "zotero_imported_at",
                "zotero_collection_key",
                "zotero_collection_name",
            ])
            marked_unimported += 1

        if update_fields:
            paper.save(update_fields=list(dict.fromkeys(update_fields + ["updated_at"])))
            changed += 1

    return {
        "changed": changed,
        "marked_imported": marked_imported,
        "marked_unimported": marked_unimported,
    }


def preferred_collection_for_paper(
    paper: Paper,
    zotero_item: ZoteroItem,
    collection_payload: dict[str, dict[str, Any]],
) -> tuple[str, str]:
    collections = zotero_item.collections or []
    if paper.zotero_collection_key:
        for collection in collections:
            if collection.get("key") == paper.zotero_collection_key:
                name = collection_payload.get(paper.zotero_collection_key, {}).get("path") or collection.get("name", "")
                return paper.zotero_collection_key, name
    if collections:
        key = collections[0].get("key", "")
        name = collection_payload.get(key, {}).get("path") or collections[0].get("name", "")
        return key, name
    return "", ""


def zotero_item_defaults(item: dict[str, Any], raw: dict[str, Any], identity_key: str) -> dict[str, Any]:
    return {
        "identity_key": identity_key,
        "title": item.get("title", ""),
        "creator": item.get("creator", ""),
        "creators": item.get("creators", []),
        "doi": item.get("doi", ""),
        "journal": item.get("journal", ""),
        "date": item.get("date", ""),
        "url": item.get("url", ""),
        "item_type": item.get("item_type", ""),
        "abstract": item.get("abstract", ""),
        "publisher": item.get("publisher", ""),
        "volume": item.get("volume", ""),
        "issue": item.get("issue", ""),
        "pages": item.get("pages", ""),
        "language": item.get("language", ""),
        "issn": item.get("issn", ""),
        "isbn": item.get("isbn", ""),
        "archive": item.get("archive", ""),
        "library_catalog": item.get("library_catalog", ""),
        "extra": item.get("extra", ""),
        "date_added": item.get("date_added", ""),
        "date_modified": item.get("date_modified", ""),
        "access_date": item.get("access_date", ""),
        "tags": item.get("tags", []),
        "collections": item.get("collections", []),
        "zotero_version": int(raw.get("version") or raw.get("data", {}).get("version") or 0),
        "raw": raw,
    }


def save_zotero_item_by_identity(key: str, identity_key: str, defaults: dict[str, Any]) -> ZoteroItem:
    """Upsert a Zotero item by DOI/title identity, falling back to Zotero key.

    Zotero item keys can change between imports or duplicate user copies. For
    deduplication we therefore prefer DOI; if DOI is missing, a normalized title
    hash is used. The Zotero key is only a final fallback when there is no title.
    """
    with transaction.atomic():
        by_identity = ZoteroItem.objects.filter(identity_key=identity_key).order_by("id").first() if identity_key else None
        by_key = ZoteroItem.objects.filter(key=key).first() if key else None
        target = by_identity or by_key

        if target:
            if by_identity and by_key and by_identity.pk != by_key.pk:
                merge_zotero_rows(target=by_identity, duplicate=by_key)
                target = by_identity
            for field, value in defaults.items():
                setattr(target, field, value)
            if key and target.key != key and not ZoteroItem.objects.filter(key=key).exclude(pk=target.pk).exists():
                target.key = key
            target.save()
            return target

        try:
            return ZoteroItem.objects.create(key=key, **defaults)
        except IntegrityError:
            fallback = ZoteroItem.objects.filter(key=key).first() or ZoteroItem.objects.filter(identity_key=identity_key).order_by("id").first()
            if not fallback:
                raise
            for field, value in defaults.items():
                setattr(fallback, field, value)
            fallback.save()
            return fallback


def build_zotero_identity_key(item: dict[str, Any]) -> str:
    doi = normalize_doi(item.get("doi") or "")
    if doi:
        return f"doi:{doi}"
    title = normalize_space(item.get("title") or "").lower()
    if title:
        digest = hashlib.sha256(title.encode("utf-8")).hexdigest()
        return f"title:{digest}"
    return f"zotero:{item.get('key', '')}"


def merge_zotero_rows(*, target: ZoteroItem, duplicate: ZoteroItem) -> None:
    merged_collections = merge_list_by_key(target.collections or [], duplicate.collections or [])
    merged_tags = sorted(set((target.tags or []) + (duplicate.tags or [])))
    target.collections = merged_collections
    target.tags = merged_tags
    target.save(update_fields=["collections", "tags", "updated_at"])
    duplicate.delete()


def merge_list_by_key(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for item in left + right:
        key = item.get("key") or item.get("name") or str(item)
        rows[key] = item
    return list(rows.values())


def cleanup_zotero_identity_duplicates() -> None:
    seen: dict[str, ZoteroItem] = {}
    for row in ZoteroItem.objects.exclude(identity_key="").order_by("id"):
        target = seen.get(row.identity_key)
        if target:
            merge_zotero_rows(target=target, duplicate=row)
        else:
            seen[row.identity_key] = row


def backfill_zotero_identity_keys() -> None:
    for row in ZoteroItem.objects.filter(identity_key="").only("id", "key", "doi", "title", "identity_key"):
        identity_key = build_zotero_identity_key({"key": row.key, "doi": row.doi, "title": row.title})
        if identity_key:
            row.identity_key = identity_key
            row.save(update_fields=["identity_key", "updated_at"])


def refresh_collection_counts() -> None:
    counts: dict[str, int] = {}
    for item in ZoteroItem.objects.all().only("collections"):
        for collection in item.collections or []:
            key = collection.get("key")
            if key:
                counts[key] = counts.get(key, 0) + 1
    for collection in ZoteroCollection.objects.all():
        count = counts.get(collection.key, 0)
        if collection.item_count != count:
            collection.item_count = count
            collection.save(update_fields=["item_count", "updated_at"])


def zotero_item_to_dict(row: ZoteroItem) -> dict[str, Any]:
    return {
        "key": row.key,
        "title": row.title,
        "creator": row.creator,
        "creators": row.creators,
        "doi": row.doi,
        "journal": row.journal,
        "date": row.date,
        "url": row.url,
        "item_type": row.item_type,
        "abstract": row.abstract,
        "publisher": row.publisher,
        "volume": row.volume,
        "issue": row.issue,
        "pages": row.pages,
        "language": row.language,
        "issn": row.issn,
        "isbn": row.isbn,
        "archive": row.archive,
        "library_catalog": row.library_catalog,
        "extra": row.extra,
        "date_added": row.date_added,
        "date_modified": row.date_modified,
        "access_date": row.access_date,
        "tags": row.tags,
        "collections": row.collections,
    }


def zotero_item_to_summary(row: ZoteroItem) -> dict[str, Any]:
    """Return only fields needed by the library tree and center table."""
    return {
        "key": row.key,
        "title": row.title,
        "creator": row.creator,
        "doi": row.doi,
        "journal": row.journal,
        "date": row.date,
        "item_type": row.item_type,
        "collections": row.collections,
    }


def import_paper_to_zotero(
    *,
    paper_id: int,
    collection_key: str = "",
    collection_name: str = "",
    user_id: str = "",
    group_id: str = "",
) -> dict[str, Any]:
    paper = Paper.objects.prefetch_related("directions", "keywords").get(id=paper_id)
    zot = get_zotero_client(user_id=user_id, group_id=group_id)
    existing = find_cached_zotero_item_for_paper(paper)
    result: dict[str, Any] = {"success": {}, "failed": {}, "unchanged": {}}
    zotero_key = ""
    import_status = "created"

    if existing:
        zotero_key = existing.key
        already_in_collection = bool(collection_key and cached_item_has_collection(existing, collection_key))
        if collection_key and not already_in_collection:
            server_item = zot.item(existing.key)
            zot.addto_collection(collection_key, server_item)
            append_collection_to_cached_item(existing, collection_key, collection_name)
            import_status = "added_to_collection"
        else:
            append_collection_to_cached_item(existing, collection_key, collection_name)
            import_status = "already_exists"
        result["unchanged"] = {"0": existing.key}
    else:
        item = build_zotero_item(paper, collection_key)
        result = zot.create_items([item])
        zotero_key = str((result.get("success") or {}).get("0", "")).strip()
        if not zotero_key:
            raise ValueError(f"Zotero 创建条目失败：{result}")
        upsert_created_zotero_item(zot, zotero_key, fallback_item=item, collection_key=collection_key, collection_name=collection_name)

    paper.zotero_imported = True
    paper.zotero_imported_at = timezone.now()
    paper.zotero_collection_key = collection_key
    paper.zotero_collection_name = collection_name
    paper.save(update_fields=[
        "zotero_imported",
        "zotero_imported_at",
        "zotero_collection_key",
        "zotero_collection_name",
        "updated_at",
    ])

    return {
        "paper_id": paper.id,
        "title": paper.title,
        "zotero_key": zotero_key,
        "collection_key": collection_key,
        "collection_name": collection_name,
        "status": import_status,
        "zotero_result": result,
    }


def find_cached_zotero_item_for_paper(paper: Paper) -> ZoteroItem | None:
    for identity_key in build_paper_zotero_identity_keys(paper):
        item = ZoteroItem.objects.filter(identity_key=identity_key).order_by("id").first()
        if item:
            return item
    return None


def find_zotero_item_for_paper_from_map(
    paper: Paper,
    items_by_identity: dict[str, ZoteroItem],
) -> ZoteroItem | None:
    for identity_key in build_paper_zotero_identity_keys(paper):
        item = items_by_identity.get(identity_key)
        if item:
            return item
    return None


def build_paper_zotero_identity_keys(paper: Paper) -> list[str]:
    keys: list[str] = []
    doi = normalize_doi(paper.doi or "")
    if doi:
        keys.append(f"doi:{doi}")
    title = normalize_space(paper.title or "").lower()
    if title:
        keys.append(f"title:{hashlib.sha256(title.encode('utf-8')).hexdigest()}")
    return keys


def build_paper_zotero_identity_key(paper: Paper) -> str:
    keys = build_paper_zotero_identity_keys(paper)
    return keys[0] if keys else ""


def cached_item_has_collection(item: ZoteroItem, collection_key: str) -> bool:
    return any(row.get("key") == collection_key for row in item.collections or [])


def append_collection_to_cached_item(item: ZoteroItem, collection_key: str, collection_name: str = "") -> None:
    if not collection_key:
        return
    collection_name = collection_name or collection_display_name(collection_key)
    collections = merge_list_by_key(item.collections or [], [{"key": collection_key, "name": collection_name or collection_key}])
    item.collections = collections
    item.save(update_fields=["collections", "updated_at"])
    refresh_collection_counts()


def collection_display_name(collection_key: str) -> str:
    collection = ZoteroCollection.objects.filter(key=collection_key).first()
    if not collection:
        return ""
    payload = {row["key"]: row for row in build_collection_payload()}
    return payload.get(collection.key, {}).get("path") or collection.name


def upsert_created_zotero_item(
    zot,
    zotero_key: str,
    *,
    fallback_item: dict[str, Any],
    collection_key: str = "",
    collection_name: str = "",
) -> None:
    try:
        raw = zot.item(zotero_key)
    except Exception:
        data = dict(fallback_item)
        data["key"] = zotero_key
        raw = {"key": zotero_key, "data": data, "version": 0}

    collections = cached_collections_map()
    if collection_key and collection_key not in collections:
        collections[collection_key] = {
            "key": collection_key,
            "name": collection_name or collection_key,
            "parent": "",
            "item_count": 0,
        }
    normalized = normalize_items([raw], collections)
    upsert_zotero_items([raw], normalized)
    refresh_collection_counts()


def cached_collections_map() -> dict[str, dict[str, Any]]:
    return {
        row.key: {
            "key": row.key,
            "name": row.name,
            "parent": row.parent_key,
            "item_count": row.item_count,
        }
        for row in ZoteroCollection.objects.all()
    }


def suggest_collection_for_paper(*, paper_id: int, user_id: str = "", group_id: str = "") -> dict[str, Any]:
    paper = Paper.objects.prefetch_related("directions", "keywords").get(id=paper_id)
    sync_zotero_collections_incremental(user_id=user_id, group_id=group_id)
    library = read_zotero_library(user_id=user_id, group_id=group_id, max_items=0, refresh=False)
    collections = library["collections"]
    desired_name, terms, reason = infer_collection_name(paper)
    selected = best_collection_match(desired_name, collections)
    return {
        "paper_id": paper.id,
        "title": paper.title,
        "suggested_collection_name": selected.get("name") or desired_name,
        "suggested_collection_key": selected.get("key", ""),
        "reason": reason,
        "matched_terms": terms,
        "collections": collections,
    }


def normalize_collections(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    collections: dict[str, dict[str, Any]] = {}
    for row in rows:
        data = row.get("data", {})
        key = data.get("key") or row.get("key", "")
        if not key:
            continue
        collections[key] = {
            "key": key,
            "name": data.get("name", "未命名分类"),
            "parent": data.get("parentCollection") or "",
            "item_count": 0,
        }
    return collections


def normalize_items(rows: list[dict[str, Any]], collections: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in rows:
        data = row.get("data", {})
        collection_keys = data.get("collections") or []
        for key in collection_keys:
            if key in collections:
                collections[key]["item_count"] += 1
        items.append(
            {
                "key": data.get("key") or row.get("key", ""),
                "title": data.get("title", ""),
                "creator": creator_text(data.get("creators") or []),
                "creators": normalize_creators(data.get("creators") or []),
                "doi": normalize_doi(data.get("DOI") or data.get("doi")),
                "journal": data.get("publicationTitle", ""),
                "date": data.get("date", ""),
                "url": data.get("url", ""),
                "item_type": data.get("itemType", ""),
                "abstract": data.get("abstractNote", ""),
                "publisher": data.get("publisher", ""),
                "volume": data.get("volume", ""),
                "issue": data.get("issue", ""),
                "pages": data.get("pages", ""),
                "language": data.get("language", ""),
                "issn": data.get("ISSN", ""),
                "isbn": data.get("ISBN", ""),
                "archive": data.get("archive", ""),
                "library_catalog": data.get("libraryCatalog", ""),
                "extra": data.get("extra", ""),
                "date_added": data.get("dateAdded", ""),
                "date_modified": data.get("dateModified", ""),
                "access_date": data.get("accessDate", ""),
                "tags": [tag.get("tag", "") for tag in data.get("tags", []) if tag.get("tag")],
                "collections": [
                    {"key": key, "name": collections.get(key, {}).get("name", key)}
                    for key in collection_keys
                ],
            }
        )
    return items


def normalize_creators(creators: list[dict[str, str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for creator in creators:
        name = creator.get("name") or " ".join([creator.get("firstName", ""), creator.get("lastName", "")]).strip()
        if name:
            rows.append({"name": name, "type": creator.get("creatorType", "")})
    return rows


def group_items_by_collection(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    uncategorized = {"key": "", "name": "未分类", "items": []}
    for item in items:
        if not item["collections"]:
            uncategorized["items"].append(item)
            continue
        for collection in item["collections"]:
            key = collection["key"]
            grouped.setdefault(key, {"key": key, "name": collection["name"], "items": []})
            grouped[key]["items"].append(item)
    rows = sorted(grouped.values(), key=lambda row: row["name"])
    if uncategorized["items"]:
        rows.append(uncategorized)
    return rows


def build_zotero_item(paper: Paper, collection_key: str = "") -> dict[str, Any]:
    item = {
        "itemType": "journalArticle",
        "title": paper.title,
        "creators": build_creators(paper.authors),
        "publicationTitle": paper.journal or paper.source_name,
        "date": paper.published_date.isoformat() if paper.published_date else "",
        "DOI": paper.doi or "",
        "url": paper.url or "",
        "abstractNote": paper.abstract or "",
        "tags": [{"tag": item.keyword} for item in paper.keywords.all()],
    }
    if collection_key:
        item["collections"] = [collection_key]
    return item


def build_creators(authors: str) -> list[dict[str, str]]:
    names = [normalize_space(item) for item in str(authors or "").replace(" and ", ";").split(";") if normalize_space(item)]
    creators = []
    for name in names[:20]:
        parts = name.split()
        if len(parts) >= 2:
            creators.append({"creatorType": "author", "firstName": " ".join(parts[:-1]), "lastName": parts[-1]})
        else:
            creators.append({"creatorType": "author", "name": name})
    return creators


def creator_text(creators: list[dict[str, str]]) -> str:
    names = []
    for creator in creators[:3]:
        if creator.get("name"):
            names.append(creator["name"])
        else:
            full = " ".join([creator.get("firstName", ""), creator.get("lastName", "")]).strip()
            if full:
                names.append(full)
    suffix = " et al." if len(creators) > 3 else ""
    return ", ".join(names) + suffix if names else ""


def infer_collection_name(paper: Paper) -> tuple[str, list[str], str]:
    directions = [item.name for item in paper.directions.all()]
    if directions:
        return directions[0], directions, "研究方向匹配"

    keywords = [item.keyword for item in paper.keywords.all()[:6]]
    if keywords:
        return infer_collection_from_terms(keywords), keywords, "关键词匹配"

    text = f"{paper.title} {paper.abstract} {paper.raw_keywords}".lower()
    rules = [
        ("燃料电池与电解池", ["fuel cell", "sofc", "pemfc", "electrolyzer", "electrolysis"]),
        ("储能技术与能源系统灵活性", ["battery", "storage", "thermal energy storage"]),
        ("氢能系统", ["hydrogen", "power-to-gas"]),
        ("新能源系统", ["renewable", "solar", "wind", "distributed energy"]),
        ("碳捕集与低碳", ["carbon", "co2", "emission", "low-carbon"]),
    ]
    for name, terms in rules:
        matched = [term for term in terms if term in text]
        if matched:
            return name, matched, "标题/摘要推断"
    return "待分类文献", [], "暂无明显匹配"


def infer_collection_from_terms(terms: list[str]) -> str:
    text = " ".join(terms).lower()
    if any(term in text for term in ["fuel cell", "sofc", "pemfc", "pemec", "soec"]):
        return "燃料电池与电解池"
    if any(term in text for term in ["battery", "storage"]):
        return "储能技术与能源系统灵活性"
    if "hydrogen" in text:
        return "氢能系统"
    if any(term in text for term in ["renewable", "solar", "wind"]):
        return "新能源系统"
    if any(term in text for term in ["carbon", "co2"]):
        return "碳捕集与低碳"
    return terms[0] if terms else "待分类文献"


def best_collection_match(name: str, collections: list[dict[str, Any]]) -> dict[str, Any]:
    normalized = normalize_space(name).lower()
    for collection in collections:
        if normalize_space(collection.get("name")).lower() == normalized:
            return collection
    for collection in collections:
        cname = normalize_space(collection.get("name")).lower()
        if normalized and (normalized in cname or cname in normalized):
            return collection
    return {}
