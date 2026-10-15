from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from dateutil import parser as date_parser


DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)


def extract_doi(*values: Any) -> str:
    text = " ".join(str(v or "") for v in values)
    match = DOI_RE.search(text)
    if not match:
        return ""
    return match.group(0).rstrip(").,;").lower()


def parse_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return date_parser.parse(str(value), fuzzy=True).date()
    except Exception:
        return None


def clean_text(value: Any) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    return re.sub(r"\s+", " ", text).strip()


def clean_abstract_text(value: Any) -> str:
    text = clean_text(value)
    return re.sub(r"^abstract\s+", "", text, flags=re.I).strip()


def first(value: Any) -> str:
    if isinstance(value, list) and value:
        return str(value[0] or "")
    return str(value or "")


def join_authors(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, str):
        return clean_text(value)
    names = []
    for item in value:
        if isinstance(item, dict):
            name = item.get("name") or " ".join(part for part in [item.get("given"), item.get("family")] if part)
            if name:
                names.append(name)
        elif item:
            names.append(str(item))
    return "; ".join(names)
