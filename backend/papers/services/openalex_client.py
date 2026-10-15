"""Shared OpenAlex request pacing and rate-limit cooldown for this process."""

from __future__ import annotations

import os
import threading
import time

import requests
from django.conf import settings

_request_lock = threading.Lock()
_last_request_at = 0.0
_retry_at = 0.0


class OpenAlexRateLimitError(requests.HTTPError):
    def __init__(self, retry_after: int, response=None):
        self.retry_after = max(1, int(retry_after or 1))
        super().__init__(f"OpenAlex 返回 429，建议 {self.retry_after} 秒后重试", response=response)


def _retry_seconds(response) -> int:
    # A daily-budget 429 lasts until reset even if Retry-After is shorter.
    remaining = response.headers.get("X-RateLimit-Remaining")
    value = (
        response.headers.get("X-RateLimit-Reset") if remaining == "0" else None
    ) or response.headers.get("Retry-After") or response.headers.get("X-RateLimit-Reset") or "300"
    try:
        return max(1, min(int(float(value)), 86400))
    except (TypeError, ValueError):
        return 300


def request_openalex(url: str, *, params: dict | None = None, timeout: int | None = None):
    global _last_request_at, _retry_at
    request_params = dict(params or {})
    headers = {"User-Agent": "ResearcherRadar/1.0"}
    mailto = os.getenv("OPENALEX_MAILTO", "").strip()
    if mailto:
        headers["User-Agent"] += f" (mailto:{mailto})"
        request_params["mailto"] = mailto
    key = os.getenv("OPENALEX_API_KEY", "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        minimum_interval = max(0.0, float(os.getenv("OPENALEX_MIN_INTERVAL_SECONDS", "0.25")))
    except ValueError:
        minimum_interval = 0.25
    with _request_lock:
        remaining = _retry_at - time.monotonic()
        if remaining > 0:
            raise OpenAlexRateLimitError(int(remaining) + 1)
        wait = minimum_interval - (time.monotonic() - _last_request_at)
        if wait > 0:
            time.sleep(wait)
        response = requests.get(
            url,
            params=request_params,
            headers=headers,
            timeout=timeout or getattr(settings, "LITERATURE_HTTP_TIMEOUT", 10),
        )
        _last_request_at = time.monotonic()
        if response.status_code == 429:
            retry_after = _retry_seconds(response)
            _retry_at = time.monotonic() + retry_after
            raise OpenAlexRateLimitError(retry_after, response=response)
    return response
