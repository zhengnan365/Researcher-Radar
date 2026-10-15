from __future__ import annotations

from dataclasses import asdict, dataclass

from django.conf import settings

from papers.models import SystemSetting


SCORING_SETTING_KEY = "scoring_rules"


@dataclass(frozen=True)
class RuntimeRules:
    title_factor: float = 3
    abstract_factor: float = 2
    raw_factor: float = 1
    field_bonus: int = 5
    bonus_ratio: float = 0.25
    max_score: int = 100
    report_min_score: int = 18
    key_threshold: int = 30
    normal_threshold: int = 12
    low_score_threshold: int = 8
    low_score_retention_days: int = 90
    report_sort: str = "score"
    sort_by_score_desc: bool = True
    group_by_direction: bool = True
    daily_max_papers: int = 80
    key_papers_max: int = 8
    show_score_detail: bool = True
    show_weak_related: bool = False
    # A title-level signal for clearly out-of-scope applications.  These
    # papers keep their evidence score but cannot become a key recommendation.
    key_demotion_terms: str = (
        "airborne high-power laser\nblast loading\nhydrogen gas explosion\n"
        "nanofiber\ngeochemical interactions\nadsorption material\n"
        "catalyst synthesis\nbattery technologies"
    )


FIELD_ALIASES = {
    "report_min_score": "REPORT_MIN_RECOMMEND_SCORE",
    "low_score_threshold": "SCORE_WEAK_THRESHOLD",
    "daily_max_papers": "REPORT_MAX_PAPERS",
}


def default_rules() -> dict:
    base = asdict(RuntimeRules())
    for field, env_name in FIELD_ALIASES.items():
        base[field] = int(getattr(settings, env_name, base[field]))
    base["show_weak_related"] = bool(getattr(settings, "REPORT_SHOW_WEAK_RELATED", base["show_weak_related"]))
    return base


def get_runtime_rules() -> dict:
    rules = default_rules()
    setting = SystemSetting.objects.filter(key=SCORING_SETTING_KEY).first()
    if setting and isinstance(setting.value, dict):
        rules.update({key: value for key, value in setting.value.items() if key in rules})
    return rules


def save_runtime_rules(payload: dict) -> dict:
    rules = default_rules()
    rules.update({key: payload[key] for key in rules.keys() if key in payload})
    validate_runtime_rules(rules)
    SystemSetting.objects.update_or_create(
        key=SCORING_SETTING_KEY,
        defaults={"value": rules, "description": "推荐评分与日报展示规则"},
    )
    return rules


def reset_runtime_rules() -> dict:
    rules = default_rules()
    SystemSetting.objects.update_or_create(
        key=SCORING_SETTING_KEY,
        defaults={"value": rules, "description": "推荐评分与日报展示规则"},
    )
    return rules


def validate_runtime_rules(rules: dict) -> None:
    terms = rules.get("key_demotion_terms", "")
    if not isinstance(terms, str) or len(terms) > 5000:
        raise ValueError("重点推荐降级词必须是 5000 字符以内的文本")
    integer_fields = [
        "field_bonus",
        "max_score",
        "report_min_score",
        "key_threshold",
        "normal_threshold",
        "low_score_threshold",
        "low_score_retention_days",
        "daily_max_papers",
        "key_papers_max",
    ]
    for field in integer_fields:
        try:
            rules[field] = int(rules.get(field, 0))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field} 必须为数字") from exc
        if rules[field] < 0:
            raise ValueError(f"{field} 不能为负数")
    if rules["daily_max_papers"] < 1:
        raise ValueError("每日最多展示文献数量不能小于 1")
    if not 30 <= rules["low_score_retention_days"] <= 3650:
        raise ValueError("低相关内容保留天数必须在 30-3650 天之间")
    if not 1 <= rules["max_score"] <= 100:
        raise ValueError("单篇文章最高分必须为 1-100")
    if rules["key_papers_max"] < 1:
        raise ValueError("今日重点文献最多展示数量不能小于 1")
    if rules["key_threshold"] <= rules["report_min_score"]:
        raise ValueError("今日重点文献阈值应高于日报最低展示分数")
    if rules["low_score_threshold"] > rules["report_min_score"]:
        raise ValueError("低分条目阈值不应高于日报最低展示分数")
    if not rules["low_score_threshold"] <= rules["normal_threshold"] < rules["key_threshold"]:
        raise ValueError("推荐等级阈值应按低分、一般、重点依次递增")
    for field in ("title_factor", "abstract_factor", "raw_factor", "bonus_ratio"):
        try:
            rules[field] = float(rules.get(field, 0))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field} 必须为数字") from exc
        if rules[field] < 0:
            raise ValueError(f"{field} 不能为负数")
    if rules["bonus_ratio"] > 0.25:
        raise ValueError("附加奖励上限不能超过关键词分的 25%")
    if rules["field_bonus"] > 5:
        raise ValueError("每增加一个命中字段，奖励不能超过 5 分")
    if rules.get("report_sort") not in {"score", "date", "score_date", "direction", "journal", "keyword_count"}:
        raise ValueError("日报默认排序方式不合法")
