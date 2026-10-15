from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_HALF_UP
import re

from django.utils import timezone

from papers.models import Paper, ResearchDirection
from papers.services.matching_engine import match_document, term_pattern
from papers.services.runtime_settings import get_runtime_rules


DIRECTION_BONUSES = {1: 1, 2: 3, 3: 5, 4: 8, 5: 10}


@dataclass(frozen=True)
class ScoreRules:
    title_factor: float = 3
    abstract_factor: float = 2
    raw_factor: float = 1
    field_bonus: int = 5
    bonus_ratio: float = 0.25
    max_score: int = 100
    key_threshold: int = 30
    normal_threshold: int = 12
    weak_threshold: int = 8
    key_demotion_terms: str = ""


def get_score_rules() -> ScoreRules:
    runtime = get_runtime_rules()
    return ScoreRules(
        title_factor=float(runtime.get("title_factor", 3)),
        abstract_factor=float(runtime.get("abstract_factor", 2)),
        raw_factor=float(runtime.get("raw_factor", 1)),
        field_bonus=int(runtime.get("field_bonus", 5)),
        bonus_ratio=float(runtime.get("bonus_ratio", 0.25)),
        max_score=int(runtime.get("max_score", 100)),
        key_threshold=int(runtime.get("key_threshold", 30)),
        normal_threshold=int(runtime.get("normal_threshold", 12)),
        weak_threshold=int(runtime.get("low_score_threshold", 8)),
        key_demotion_terms=str(runtime.get("key_demotion_terms", "")),
    )


def score_paper(paper: Paper, *, keywords=None, rules: ScoreRules | None = None) -> Paper:
    if paper.content_pruned_at is not None:
        return paper
    rules = rules or get_score_rules()
    if re.match(r"^\s*(?:retraction|correction|erratum|corrigendum)\b", paper.title or "", flags=re.I) or re.match(r"^\s*(?:撤稿|更正|勘误)", paper.title or ""):
        return suppress_paper(paper, "publication_type", ["title"])

    result = match_document(paper.title, paper.abstract, paper.raw_keywords, keywords=keywords)
    if result.exclusion:
        return suppress_paper(paper, result.exclusion.keyword.keyword, list(result.exclusion.fields))

    factors = {
        "title": Decimal(str(rules.title_factor)),
        "abstract": Decimal(str(rules.abstract_factor)),
        "raw_keywords": Decimal(str(rules.raw_factor)),
    }
    keyword_score = Decimal("0")
    keyword_details = []
    matched_fields = {}
    matched_field_names = set()
    matched_directions: dict[int, ResearchDirection] = {}
    items = []

    for match in result.keywords:
        keyword = match.keyword
        field_total = Decimal("0")
        matched_fields[keyword.keyword] = list(match.fields)
        matched_field_names.update(match.fields)
        for field in match.fields:
            contribution = Decimal(keyword.weight) * factors[field]
            field_total += contribution
            keyword_details.append({
                "keyword": keyword.keyword,
                "term": match.terms[field],
                "direction": keyword.direction.name_cn if keyword.direction_id and keyword.direction else "",
                "field": field,
                "weight": keyword.weight,
                "factor": float(factors[field]),
                "score": float(contribution),
            })
        keyword_score += field_total
        items.append({"type": "keyword", "name": keyword.keyword, "fields": list(match.fields), "score": float(field_total)})
        if keyword.direction_id and keyword.direction.enabled:
            matched_directions[keyword.direction_id] = keyword.direction

    best_direction = max(
        matched_directions.values(),
        key=lambda direction: (direction.direction_weight, direction.priority, -direction.pk),
        default=None,
    )
    direction_nominal = Decimal(DIRECTION_BONUSES[best_direction.direction_weight]) if best_direction else Decimal("0")
    field_nominal = Decimal(rules.field_bonus * max(0, len(matched_field_names) - 1))
    bonus_cap = keyword_score * Decimal(str(rules.bonus_ratio))
    nominal_total = direction_nominal + field_nominal
    applied_total = min(nominal_total, bonus_cap)
    direction_bonus = (
        (applied_total * direction_nominal / nominal_total).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        if nominal_total else Decimal("0")
    )
    field_bonus = applied_total - direction_bonus
    raw_score = keyword_score + direction_bonus + field_bonus
    unrestricted_score = min(int(raw_score.quantize(Decimal("1"), rounding=ROUND_HALF_UP)), rules.max_score, 100)
    demotion_match = next(
        (
            term.strip()
            for term in rules.key_demotion_terms.splitlines()
            if (pattern := term_pattern(term)) is not None and pattern.search(paper.title or "")
        ),
        "",
    )
    final_score = min(unrestricted_score, rules.key_threshold - 1) if demotion_match else unrestricted_score

    if best_direction:
        items.append({"type": "direction", "name": best_direction.name_cn, "score": float(direction_bonus)})
    if field_bonus:
        items.append({"type": "multi_field", "name": "多字段", "score": float(field_bonus)})

    paper.keywords.set([match.keyword for match in result.keywords])
    paper.directions.set(matched_directions.values())
    paper.system_recommend_score = final_score
    paper.recommend_score = 0 if paper.relevance_override == "irrelevant" else final_score
    paper.recommend_level = "low" if paper.relevance_override == "irrelevant" else recommend_level(final_score, rules)
    paper.matched_fields = matched_fields
    paper.score_detail = {
        "version": 2,
        "rules": asdict(rules),
        "keywords": keyword_details,
        "keyword_score": float(keyword_score),
        "direction_bonus": {
            "name": best_direction.name_cn if best_direction else "",
            "weight": best_direction.direction_weight if best_direction else 0,
            "nominal": float(direction_nominal),
            "score": float(direction_bonus),
        },
        "field_bonus": float(field_bonus),
        "field_bonus_nominal": float(field_nominal),
        "bonus_cap": float(bonus_cap),
        "raw_score": float(raw_score),
        "unrestricted_score": unrestricted_score,
        "key_demotion_match": demotion_match,
        "final_score": final_score,
        "items": items,
    }
    paper.scored_at = timezone.now()
    paper.save(update_fields=["system_recommend_score", "recommend_score", "recommend_level", "matched_fields", "score_detail", "scored_at", "updated_at"])
    return paper


def suppress_paper(paper: Paper, reason: str, fields: list[str]) -> Paper:
    paper.keywords.clear()
    paper.directions.clear()
    paper.recommend_score = 0
    paper.system_recommend_score = 0
    paper.recommend_level = "low"
    paper.matched_fields = {}
    paper.score_detail = {"version": 2, "exclusion": reason, "fields": fields, "keywords": [], "final_score": 0, "items": []}
    paper.scored_at = timezone.now()
    paper.save(update_fields=["system_recommend_score", "recommend_score", "recommend_level", "matched_fields", "score_detail", "scored_at", "updated_at"])
    return paper


def recommend_level(score: int, rules: ScoreRules) -> str:
    if score >= rules.key_threshold:
        return "key"
    if score >= rules.normal_threshold:
        return "normal"
    if score >= rules.weak_threshold:
        return "weak"
    return "low"
