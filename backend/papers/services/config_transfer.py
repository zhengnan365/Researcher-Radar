from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from papers.models import Keyword, ResearchDirection, RssSource, ZoteroConfig
from papers.services.ai_config import AiConfigError, get_ai_config, save_ai_config
from papers.services.runtime_settings import get_runtime_rules, save_runtime_rules


CONFIG_FORMAT = "literature-daily-config"
CONFIG_VERSION = 3


class ConfigImportError(ValueError):
    pass


@dataclass
class ImportCounter:
    created: int = 0
    updated: int = 0

    def record(self, created: bool) -> None:
        if created:
            self.created += 1
        else:
            self.updated += 1

    def as_dict(self) -> dict[str, int]:
        return {"created": self.created, "updated": self.updated}


def export_system_config() -> dict[str, Any]:
    zotero = ZoteroConfig.get_active()
    ai = get_ai_config(include_key=True)
    return {
        "format": CONFIG_FORMAT,
        "version": CONFIG_VERSION,
        "exported_at": timezone.now().isoformat(),
        "contains_secrets": True,
        "data": {
            "research_directions": [
                {
                    "name": item.name,
                    "name_cn": item.name_cn,
                    "name_en": item.name_en,
                    "direction_weight": item.direction_weight,
                    "priority": item.priority,
                    "enabled": item.enabled,
                }
                for item in ResearchDirection.objects.order_by("name")
            ],
            "keywords": [
                {
                    "keyword": item.keyword,
                    "aliases": item.aliases,
                    "is_exclusion": item.is_exclusion,
                    "weight": item.weight,
                    "enabled": item.enabled,
                    "description": item.description,
                    "direction": item.direction.name if item.direction else "",
                }
                for item in Keyword.objects.select_related("direction").order_by("keyword")
            ],
            "rss_sources": [
                {
                    "name": item.name,
                    "url": item.url,
                    "fetch_mode": item.fetch_mode,
                    "openalex_issn": item.openalex_issn,
                    "journal": item.journal,
                    "enabled": item.enabled,
                    "remark": item.remark,
                }
                for item in RssSource.objects.order_by("name")
            ],
            "scoring_rules": get_runtime_rules(),
            "zotero": {
                "name": zotero.name if zotero else "default",
                "library_type": zotero.library_type if zotero else "user",
                "user_id": zotero.user_id if zotero else "",
                "group_id": zotero.group_id if zotero else "",
                "api_key": zotero.api_key if zotero else "",
                "enabled": zotero.enabled if zotero else True,
            },
            "ai": {
                "provider": ai["provider"],
                "base_url": ai["base_url"],
                "model": ai["model"],
                "api_key": ai["api_key"],
            } if ai["has_api_key"] else None,
        },
    }


@transaction.atomic
def import_system_config(payload: dict[str, Any]) -> dict[str, Any]:
    data = _validate_envelope(payload)
    counters = {
        "research_directions": ImportCounter(),
        "keywords": ImportCounter(),
        "rss_sources": ImportCounter(),
        "scoring_rules": ImportCounter(),
        "zotero": ImportCounter(),
        "ai": ImportCounter(),
    }

    if "research_directions" in data:
        for index, raw in enumerate(_as_list(data, "research_directions")):
            item = _as_dict(raw, f"research_directions[{index}]")
            name = _required_text(item.get("name_cn") or item.get("name"), f"research_directions[{index}].name_cn", 120)
            obj = ResearchDirection.objects.filter(name=name).first()
            created = obj is None
            obj = obj or ResearchDirection(name=name)
            obj.name = name
            obj.name_cn = name
            if "name_en" in item:
                obj.name_en = _optional_text(item.get("name_en"), 240) or None
            obj.direction_weight = _weight_1_5(item.get("direction_weight", obj.direction_weight), f"研究方向“{name}”的权重")
            obj.priority = _weight_1_5(item.get("priority", obj.priority), f"研究方向“{name}”的优先级")
            obj.enabled = _as_bool(item.get("enabled", True), f"research_directions[{index}].enabled")
            _save_validated(obj, f"研究方向“{name}”")
            counters["research_directions"].record(created)

    direction_map = {item.name: item for item in ResearchDirection.objects.all()}

    if "keywords" in data:
        for index, raw in enumerate(_as_list(data, "keywords")):
            item = _as_dict(raw, f"keywords[{index}]")
            keyword = _required_text(item.get("keyword"), f"keywords[{index}].keyword", 120)
            direction = _resolve_direction(item.get("direction"), direction_map, f"关键词“{keyword}”")
            weight = _weight_1_5(item.get("weight", 1), f"关键词“{keyword}”的权重")
            obj = Keyword.objects.filter(keyword=keyword).first()
            created = obj is None
            obj = obj or Keyword(keyword=keyword)
            obj.aliases = _optional_text(item.get("aliases"), 10_000)
            obj.is_exclusion = _as_bool(item.get("is_exclusion", False), f"keywords[{index}].is_exclusion")
            obj.weight = weight
            obj.enabled = _as_bool(item.get("enabled", True), f"keywords[{index}].enabled")
            obj.description = _optional_text(item.get("description"), 10_000)
            obj.direction = direction
            _save_validated(obj, f"关键词“{keyword}”")
            counters["keywords"].record(created)

    if "rss_sources" in data:
        for index, raw in enumerate(_as_list(data, "rss_sources")):
            item = _as_dict(raw, f"rss_sources[{index}]")
            mode = str(item.get("fetch_mode") or "rss").strip()
            if mode not in {"rss", "openalex", "both"}:
                raise ConfigImportError(f"rss_sources[{index}].fetch_mode 无效")
            url = _optional_text(item.get("url"), 200)
            issn = _optional_text(item.get("openalex_issn"), 20)
            if mode in {"rss", "both"} and not url:
                raise ConfigImportError(f"rss_sources[{index}].url 不能为空")
            if mode in {"openalex", "both"} and not issn:
                raise ConfigImportError(f"rss_sources[{index}].openalex_issn 不能为空")
            name = _required_text(item.get("name"), f"rss_sources[{index}].name", 200)
            obj = RssSource.objects.filter(url=url).first() if url else RssSource.objects.filter(fetch_mode="openalex", openalex_issn=issn).first()
            created = obj is None
            obj = obj or RssSource()
            obj.url = url
            obj.fetch_mode = mode
            obj.openalex_issn = issn
            obj.name = name
            obj.journal = _optional_text(item.get("journal"), 200)
            obj.enabled = _as_bool(item.get("enabled", True), f"rss_sources[{index}].enabled")
            obj.remark = _optional_text(item.get("remark"), 10_000)
            _save_validated(obj, f"RSS 源“{name}”")
            counters["rss_sources"].record(created)

    if "scoring_rules" in data:
        rules = _as_dict(data["scoring_rules"], "scoring_rules")
        try:
            save_runtime_rules(rules)
        except ValueError as exc:
            raise ConfigImportError(str(exc)) from exc
        counters["scoring_rules"].record(False)

    if "zotero" in data:
        item = _as_dict(data["zotero"], "zotero")
        name = _optional_text(item.get("name"), 80) or "default"
        library_type = str(item.get("library_type") or "user").strip()
        if library_type not in {"user", "group"}:
            raise ConfigImportError("Zotero 文献库类型只能为 user 或 group")
        obj = ZoteroConfig.objects.filter(name=name).first()
        created = obj is None
        obj = obj or ZoteroConfig(name=name)
        obj.library_type = library_type
        obj.user_id = _optional_text(item.get("user_id"), 80)
        obj.group_id = _optional_text(item.get("group_id"), 80)
        obj.api_key = _optional_text(item.get("api_key"), 255)
        obj.enabled = _as_bool(item.get("enabled", True), "zotero.enabled")
        _save_validated(obj, "Zotero 配置")
        counters["zotero"].record(created)

    if data.get("ai") is not None:
        item = _as_dict(data["ai"], "ai")
        if not str(item.get("api_key") or "").strip():
            raise ConfigImportError("AI API Key 不能为空")
        try:
            save_ai_config(item)
        except AiConfigError as exc:
            raise ConfigImportError(str(exc)) from exc
        counters["ai"].record(False)

    return {
        "success": True,
        "mode": "merge",
        "summary": {key: counter.as_dict() for key, counter in counters.items()},
    }


def _validate_envelope(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ConfigImportError("配置文件根节点必须是 JSON 对象")
    if payload.get("format") != CONFIG_FORMAT:
        raise ConfigImportError("不是有效的科研雷达配置文件")
    try:
        version = int(payload.get("version"))
    except (TypeError, ValueError) as exc:
        raise ConfigImportError("配置文件版本无效") from exc
    if version not in {1, 2, CONFIG_VERSION}:
        raise ConfigImportError(f"不支持的配置文件版本：{version}")
    return _as_dict(payload.get("data"), "data")


def _as_list(data: dict[str, Any], key: str) -> list[Any]:
    value = data.get(key)
    if not isinstance(value, list):
        raise ConfigImportError(f"{key} 必须是数组")
    return value


def _as_dict(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigImportError(f"{field} 必须是对象")
    return value


def _required_text(value: Any, field: str, max_length: int) -> str:
    text = str(value or "").strip()
    if not text:
        raise ConfigImportError(f"{field} 不能为空")
    if len(text) > max_length:
        raise ConfigImportError(f"{field} 不能超过 {max_length} 个字符")
    return text


def _optional_text(value: Any, max_length: int) -> str:
    text = str(value or "").strip()
    if len(text) > max_length:
        raise ConfigImportError(f"文本内容不能超过 {max_length} 个字符")
    return text


def _as_bool(value: Any, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if value in {0, 1}:
        return bool(value)
    raise ConfigImportError(f"{field} 必须为布尔值")


def _weight_1_5(value: Any, field: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigImportError(f"{field}必须为 1-5 的整数") from exc
    if not 1 <= number <= 5:
        raise ConfigImportError(f"{field}必须为 1-5 的整数")
    return number


def _resolve_direction(value: Any, direction_map: dict[str, ResearchDirection], owner: str) -> ResearchDirection | None:
    name = str(value or "").strip()
    if not name:
        return None
    direction = direction_map.get(name)
    if not direction:
        raise ConfigImportError(f"{owner}引用了不存在的研究方向“{name}”")
    return direction


def _save_validated(instance, label: str) -> None:
    try:
        instance.full_clean()
        instance.save()
    except ValidationError as exc:
        messages = "; ".join(exc.messages)
        raise ConfigImportError(f"{label}校验失败：{messages}") from exc
