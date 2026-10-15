from __future__ import annotations

from dataclasses import dataclass
import re

from papers.models import Keyword


EVIDENCE_FIELDS = ("title", "abstract", "raw_keywords")


@dataclass(frozen=True)
class KeywordMatch:
    keyword: Keyword
    fields: tuple[str, ...]
    terms: dict[str, str]


@dataclass(frozen=True)
class MatchResult:
    keywords: tuple[KeywordMatch, ...]
    exclusion: KeywordMatch | None = None


def term_pattern(term: str) -> re.Pattern | None:
    parts = term.strip().split()
    if not parts:
        return None
    pattern = r"\s+".join(re.escape(part) for part in parts)
    if re.search(r"[a-z0-9]", term, re.I):
        pattern = rf"(?<![a-z0-9]){pattern}(?![a-z0-9])"
    return re.compile(pattern, re.I)


def match_document(title: str = "", abstract: str = "", raw_keywords: str = "", keywords=None) -> MatchResult:
    fields = {"title": title or "", "abstract": abstract or "", "raw_keywords": raw_keywords or ""}
    keywords = keywords if keywords is not None else Keyword.objects.filter(enabled=True).select_related("direction")
    candidates: dict[str, list[tuple[int, int, Keyword, str, bool]]] = {field: [] for field in EVIDENCE_FIELDS}
    exclusions: list[KeywordMatch] = []

    for keyword in keywords:
        terms = [keyword.keyword, *keyword.aliases.splitlines()]
        exclusion_fields = []
        exclusion_terms = {}
        for is_alias, term in enumerate(terms):
            pattern = term_pattern(term)
            if pattern is None:
                continue
            for field, text in fields.items():
                for found in pattern.finditer(text):
                    if keyword.is_exclusion:
                        if field not in exclusion_fields:
                            exclusion_fields.append(field)
                            exclusion_terms[field] = term.strip()
                    else:
                        candidates[field].append((found.start(), found.end(), keyword, term.strip(), bool(is_alias)))
        if exclusion_fields:
            exclusions.append(KeywordMatch(keyword, tuple(exclusion_fields), exclusion_terms))

    if exclusions:
        return MatchResult((), exclusions[0])

    found_by_keyword: dict[int, dict[str, str]] = {}
    keyword_by_id: dict[int, Keyword] = {}
    for field, rows in candidates.items():
        # A longer technical phrase takes precedence over a generic phrase inside it.
        rows.sort(key=lambda row: (-(row[1] - row[0]), row[4], row[0], row[2].id))
        accepted_spans: list[tuple[int, int]] = []
        for start, end, keyword, term, _ in rows:
            if any(start < used_end and used_start < end for used_start, used_end in accepted_spans):
                continue
            accepted_spans.append((start, end))
            found_by_keyword.setdefault(keyword.id, {}).setdefault(field, term)
            keyword_by_id[keyword.id] = keyword

    matches = tuple(
        KeywordMatch(keyword_by_id[keyword_id], tuple(field for field in EVIDENCE_FIELDS if field in terms), terms)
        for keyword_id, terms in sorted(found_by_keyword.items())
    )
    return MatchResult(matches)
