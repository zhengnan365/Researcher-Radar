from unittest.mock import Mock, patch

from django.test import TestCase

from papers.models import Paper, RssSource
from papers.services import openalex_client, openalex_fetcher
from papers.services.rss_fetcher import fetch_source


class OpenAlexIngestTests(TestCase):
    def test_rate_limit_honors_retry_after_and_stops_repeating_requests(self):
        response = Mock(status_code=429, headers={"Retry-After": "3600"})
        with patch.object(openalex_client, "_retry_at", 0.0), patch.dict("os.environ", {"OPENALEX_MIN_INTERVAL_SECONDS": "0"}):
            with patch("papers.services.openalex_client.requests.get", return_value=response) as get:
                with self.assertRaises(openalex_fetcher.OpenAlexRateLimitError) as first:
                    openalex_client.request_openalex("https://api.openalex.org/works")
                self.assertEqual(first.exception.retry_after, 3600)
                with self.assertRaises(openalex_fetcher.OpenAlexRateLimitError):
                    openalex_client.request_openalex("https://api.openalex.org/works")
                get.assert_called_once()

    def test_exhausted_daily_budget_uses_reset_time(self):
        response = Mock(status_code=429, headers={
            "Retry-After": "30", "X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "3600",
        })
        self.assertEqual(openalex_client._retry_seconds(response), 3600)

    def test_abstract_lookup_respects_source_rate_limit(self):
        from papers.services.abstract_enricher import fetch_openalex_abstract

        response = Mock(status_code=429, headers={"X-RateLimit-Reset": "3600"})
        with patch.object(openalex_client, "_retry_at", 0.0), patch.dict("os.environ", {"OPENALEX_MIN_INTERVAL_SECONDS": "0"}):
            with patch("papers.services.openalex_client.requests.get", return_value=response) as get:
                with self.assertRaises(openalex_fetcher.OpenAlexRateLimitError):
                    openalex_client.request_openalex("https://api.openalex.org/works")
                self.assertEqual(fetch_openalex_abstract("10.1234/example"), "")
                get.assert_called_once()

    def test_rate_limited_source_records_actionable_failure(self):
        source = RssSource.objects.create(name="Limited journal", fetch_mode="openalex", openalex_issn="1234-5678")
        with patch("papers.services.openalex_fetcher.resolve_source_id", side_effect=openalex_fetcher.OpenAlexRateLimitError(3600)):
            result = openalex_fetcher.fetch_openalex_source(source)
        source.refresh_from_db()
        self.assertEqual(result["status"], "failed")
        self.assertIn("60 分钟后重试", source.last_fetch_message)

    def test_openalex_only_source_ingests_recent_work(self):
        source = RssSource.objects.create(
            name="Journal of Storage",
            journal="Journal of Storage",
            fetch_mode="openalex",
            openalex_issn="1234-5678",
        )
        source_response = Mock(status_code=200)
        source_response.json.return_value = {"id": "https://openalex.org/S123", "display_name": "Journal of Storage"}
        work_response = Mock(status_code=200)
        work_response.json.return_value = {
            "results": [{
                "title": "Membrane lifetime in fuel cells",
                "doi": "https://doi.org/10.1234/example",
                "publication_date": "2026-10-10",
                "authorships": [{"author": {"display_name": "A. Researcher"}}],
                "primary_location": {"landing_page_url": "https://example.org/paper", "source": {"display_name": "Journal of Storage"}},
                "abstract_inverted_index": {"Fuel": [0], "cells": [1], "last": [2], "longer": [3]},
            }],
            "meta": {"count": 1},
        }
        with patch("papers.services.openalex_client.requests.get", side_effect=[source_response, work_response]) as get:
            result = fetch_source(source)

        self.assertEqual(result["new_count"], 1)
        self.assertEqual(Paper.objects.count(), 1)
        self.assertEqual(Paper.objects.first().doi, "10.1234/example")
        self.assertIn("primary_location.source.id:S123", get.call_args.kwargs["params"]["filter"])

    def test_invalid_openalex_source_without_issn_is_rejected(self):
        from django.contrib.auth import get_user_model
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(get_user_model().objects.create_user("reader", password="password"))
        response = client.post("/api/sources/", {"name": "No ISSN", "fetch_mode": "openalex"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_openalex_source_without_rss_url_is_accepted(self):
        from django.contrib.auth import get_user_model
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(get_user_model().objects.create_user("reader2", password="password"))
        response = client.post(
            "/api/sources/",
            {"name": "Journal", "fetch_mode": "openalex", "openalex_issn": "1234-5678"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)

    def test_mixed_source_preserves_both_fetch_outcomes(self):
        source = RssSource.objects.create(
            name="Mixed journal", url="https://example.org/feed", fetch_mode="both", openalex_issn="1234-5678",
        )

        def rss_fetch(item):
            item.last_fetch_message = "RSS feed unavailable"
            return {"status": "failed", "fetched_count": 0, "new_count": 0, "duplicate_count": 0}

        def openalex_fetch(item):
            item.last_fetch_message = "OpenAlex checked 2 works"
            return {"status": "success", "fetched_count": 2, "new_count": 1, "duplicate_count": 1}

        with patch.dict("os.environ", {"CROSSREF_JOURNAL_FALLBACK_ENABLED": "false"}):
            with patch("papers.services.rss_fetcher._fetch_rss_source", side_effect=rss_fetch):
                with patch("papers.services.openalex_fetcher.fetch_openalex_source", side_effect=openalex_fetch):
                    result = fetch_source(source)

        source.refresh_from_db()
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["new_count"], 1)
        self.assertIn("RSS feed unavailable", source.last_fetch_message)
        self.assertIn("OpenAlex checked 2 works", source.last_fetch_message)
