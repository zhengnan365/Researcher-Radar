from __future__ import annotations

import logging

from papers.models import Paper, RssSource
from papers.services.matching_engine import match_document

logger = logging.getLogger(__name__)


def match_keywords_and_directions(paper: Paper) -> None:
    try:
        result = match_document(paper.title, paper.abstract, paper.raw_keywords)
        keywords, directions = matched_objects(result)
        paper.keywords.set(keywords)
        paper.directions.set(directions)
    except Exception:
        logger.exception("Keyword matching failed for paper_id=%s", paper.pk)


def classify_payload_keywords_and_directions(data: dict, source: RssSource | None) -> tuple[list, list]:
    result = match_document(data.get("title", ""), data.get("abstract", ""), data.get("raw_keywords", ""))
    return matched_objects(result)


def matched_objects(result) -> tuple[list, list]:
    if result.exclusion:
        return [], []
    keywords = [match.keyword for match in result.keywords]
    directions = list({keyword.direction_id: keyword.direction for keyword in keywords if keyword.direction_id and keyword.direction.enabled}.values())
    return keywords, directions
