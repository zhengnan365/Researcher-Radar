from unittest.mock import Mock, patch

import requests
from django.test import TestCase

from papers.models import Paper, RssSource
from papers.services import abstract_enricher, crossref_journal_fallback, elsevier_journal_fallback
from papers.services.rss_fetcher import fetch_source


class JournalFallbackTests(TestCase):
    def test_issn_from_sciencedirect_rss_only(self):
        source = RssSource(name="Applied Energy", url="https://rss.sciencedirect.com/publication/science/03062619")
        self.assertEqual(crossref_journal_fallback.source_issn(source), "0306-2619")
        source.url = "https://example.org/03062619"
        self.assertEqual(crossref_journal_fallback.source_issn(source), "")

    def test_rss_success_does_not_call_crossref(self):
        source = RssSource.objects.create(name="Feed", url="https://rss.sciencedirect.com/publication/science/03062619")
        with patch("papers.services.rss_fetcher._fetch_rss_source", return_value={"status": "success", "fetched_count": 1, "new_count": 1, "duplicate_count": 0}):
            with patch("papers.services.crossref_journal_fallback.fetch_crossref_journal") as fallback:
                result = fetch_source(source)
        self.assertEqual(result["status"], "success")
        fallback.assert_not_called()

    def test_storage_failure_does_not_start_backup_request(self):
        source = RssSource.objects.create(name="Feed", url="https://rss.sciencedirect.com/publication/science/03062619")
        with patch("papers.services.rss_fetcher._fetch_rss_source", return_value={"status": "failed", "backup_eligible": False, "fetched_count": 1}):
            with patch("papers.services.crossref_journal_fallback.fetch_crossref_journal") as fallback:
                result = fetch_source(source)
        self.assertEqual(result["status"], "failed")
        fallback.assert_not_called()

    def test_rss_failure_uses_crossref_and_records_partial_status(self):
        source = RssSource.objects.create(name="Feed", url="https://rss.sciencedirect.com/publication/science/03062619")
        def failed_rss(item):
            item.last_fetch_message = "RSS unavailable"
            return {"status": "failed", "fetched_count": 0, "new_count": 0, "duplicate_count": 0}
        response = Mock(status_code=200)
        response.json.return_value = {"message": {"items": [{
            "DOI": "10.1016/j.apenergy.2026.123456",
            "title": ["Optimal scheduling of integrated energy systems"],
            "container-title": ["Applied Energy"],
            "published-online": {"date-parts": [[2026, 10, 10]]},
            "abstract": "<jats:p>Energy system abstract.</jats:p>",
        }]}}
        with patch("papers.services.rss_fetcher._fetch_rss_source", side_effect=failed_rss):
            with patch("papers.services.crossref_journal_fallback.requests.get", return_value=response) as get:
                result = fetch_source(source)
        source.refresh_from_db()
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["new_count"], 1)
        self.assertEqual(Paper.objects.count(), 1)
        self.assertEqual(Paper.objects.first().abstract, "Energy system abstract.")
        self.assertIn("RSS unavailable", source.last_fetch_message)
        self.assertIn("Crossref", source.last_fetch_message)
        self.assertIn("from-pub-date:", get.call_args.kwargs["params"]["filter"])

    def test_openalex_failure_can_use_crossref_backup(self):
        source = RssSource.objects.create(name="Journal", fetch_mode="openalex", openalex_issn="0306-2619")
        def failed_openalex(item):
            item.last_fetch_message = "OpenAlex 429"
            return {"status": "failed", "fetched_count": 0, "new_count": 0, "duplicate_count": 0}
        def successful_crossref(item):
            item.last_fetch_message = "Crossref checked 2"
            return {"status": "success", "fetched_count": 2, "new_count": 1, "duplicate_count": 1}
        with patch("papers.services.openalex_fetcher.fetch_openalex_source", side_effect=failed_openalex):
            with patch("papers.services.crossref_journal_fallback.fetch_crossref_journal", side_effect=successful_crossref):
                result = fetch_source(source)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["new_count"], 1)
        self.assertIn("OpenAlex 429", source.last_fetch_message)
        self.assertIn("Crossref checked 2", source.last_fetch_message)

    def test_crossref_429_stops_following_requests(self):
        source = RssSource.objects.create(name="Feed", url="https://rss.sciencedirect.com/publication/science/03062619")
        response = Mock(status_code=429, headers={"Retry-After": "3600"})
        with patch.object(crossref_journal_fallback, "_retry_at", 0.0):
            with patch("papers.services.crossref_journal_fallback.requests.get", return_value=response) as get:
                self.assertEqual(crossref_journal_fallback.fetch_crossref_journal(source)["status"], "failed")
                self.assertEqual(crossref_journal_fallback.fetch_crossref_journal(source)["status"], "failed")
                get.assert_called_once()

    def test_crossref_page_cap_is_reported_as_partial(self):
        source = RssSource.objects.create(name="Feed", url="https://rss.sciencedirect.com/publication/science/03062619")
        response = Mock(status_code=200)
        response.json.return_value = {"message": {"total-results": 150, "items": [
            {"DOI": "10.1016/example", "title": ["Example"]} for _ in range(100)
        ]}}
        with patch.dict("os.environ", {"CROSSREF_FALLBACK_MAX_PAGES": "1"}), patch.object(crossref_journal_fallback, "_retry_at", 0.0):
            with patch("papers.services.crossref_journal_fallback.requests.get", return_value=response):
                with patch("papers.services.crossref_journal_fallback.should_skip_unmatched_article", return_value=True):
                    result = crossref_journal_fallback.fetch_crossref_journal(source)
        source.refresh_from_db()
        self.assertEqual(result["status"], "partial")
        self.assertIn("页数上限", source.last_fetch_message)

    def test_elsevier_is_not_requested_without_key(self):
        source = RssSource.objects.create(name="Applied Energy", url="https://rss.sciencedirect.com/publication/science/03062619")
        with patch.dict("os.environ", {"ELSEVIER_API_KEY": "", "CROSSREF_JOURNAL_FALLBACK_ENABLED": "false"}):
            with patch("papers.services.rss_fetcher._fetch_rss_source", return_value={"status": "failed"}):
                with patch("papers.services.elsevier_journal_fallback.requests.put") as put:
                    result = fetch_source(source)
        self.assertEqual(result["status"], "failed")
        put.assert_not_called()

    def test_elsevier_runs_after_empty_crossref_and_deduplicates(self):
        source = RssSource.objects.create(name="Applied Energy", journal="Applied Energy", url="https://rss.sciencedirect.com/publication/science/03062619")
        response = Mock(status_code=200)
        response.json.return_value = {"resultsFound": 3, "results": [
            {"doi": "10.1016/j.apenergy.2026.1", "title": "Optimal scheduling of integrated energy systems", "sourceTitle": "Applied Energy", "publicationDate": "2026-10-10", "authors": [{"name": "Author One"}]},
            {"doi": "10.1016/j.apenergy.2026.1", "title": "Optimal scheduling of integrated energy systems", "sourceTitle": "Applied Energy", "publicationDate": "2026-10-10"},
            {"doi": "10.1016/j.other.2026.1", "title": "Unrelated journal", "sourceTitle": "Other Journal"},
        ]}
        with patch.dict("os.environ", {"ELSEVIER_API_KEY": "test-key"}), patch.object(elsevier_journal_fallback, "_retry_at", 0.0):
            with patch("papers.services.rss_fetcher._fetch_rss_source", return_value={"status": "failed"}):
                with patch("papers.services.crossref_journal_fallback.fetch_crossref_journal", return_value={"status": "success", "fetched_count": 0}):
                    with patch("papers.services.elsevier_journal_fallback.requests.put", return_value=response) as put:
                        result = fetch_source(source)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["new_count"], 1)
        self.assertEqual(result["duplicate_count"], 1)
        self.assertEqual(Paper.objects.count(), 1)
        self.assertIn("Elsevier", source.last_fetch_message)
        self.assertEqual(put.call_args.kwargs["json"]["pub"], "Applied Energy")

    def test_elsevier_403_cools_down_and_preserves_failure(self):
        source = RssSource.objects.create(name="Applied Energy", journal="Applied Energy")
        response = Mock(status_code=403)
        with patch.dict("os.environ", {"ELSEVIER_API_KEY": "test-key"}), patch.object(elsevier_journal_fallback, "_retry_at", 0.0):
            with patch("papers.services.elsevier_journal_fallback.requests.put", return_value=response) as put:
                self.assertEqual(elsevier_journal_fallback.fetch_elsevier_journal(source)["status"], "failed")
                source.refresh_from_db()
                self.assertIn("ScienceDirect API 权限", source.last_fetch_message)
                self.assertEqual(elsevier_journal_fallback.fetch_elsevier_journal(source)["status"], "failed")
                put.assert_called_once()

    def test_elsevier_429_cools_down(self):
        source = RssSource.objects.create(name="Applied Energy", journal="Applied Energy")
        response = Mock(status_code=429, headers={"Retry-After": "3600"})
        with patch.dict("os.environ", {"ELSEVIER_API_KEY": "test-key"}), patch.object(elsevier_journal_fallback, "_retry_at", 0.0):
            with patch("papers.services.elsevier_journal_fallback.requests.put", return_value=response) as put:
                self.assertEqual(elsevier_journal_fallback.fetch_elsevier_journal(source)["status"], "failed")
                self.assertEqual(elsevier_journal_fallback.fetch_elsevier_journal(source)["status"], "failed")
                put.assert_called_once()

    def test_successful_crossref_does_not_call_elsevier(self):
        source = RssSource.objects.create(name="Applied Energy", url="https://rss.sciencedirect.com/publication/science/03062619")
        with patch.dict("os.environ", {"ELSEVIER_API_KEY": "test-key"}):
            with patch("papers.services.rss_fetcher._fetch_rss_source", return_value={"status": "failed"}):
                with patch("papers.services.crossref_journal_fallback.fetch_crossref_journal", return_value={"status": "success", "fetched_count": 1}):
                    with patch("papers.services.elsevier_journal_fallback.requests.put") as put:
                        fetch_source(source)
        put.assert_not_called()

    def test_empty_backup_does_not_hide_primary_failure(self):
        source = RssSource.objects.create(name="Applied Energy", url="https://rss.sciencedirect.com/publication/science/03062619")
        with patch.dict("os.environ", {"ELSEVIER_API_KEY": ""}):
            with patch("papers.services.rss_fetcher._fetch_rss_source", return_value={"status": "failed"}):
                with patch("papers.services.crossref_journal_fallback.fetch_crossref_journal", return_value={"status": "success", "fetched_count": 0}):
                    result = fetch_source(source)
        source.refresh_from_db()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(source.last_fetch_status, "failed")


class AbstractFallbackTests(TestCase):
    def test_elsevier_requires_key_and_cools_down_on_missing_entitlement(self):
        response = Mock(status_code=403)
        with patch.object(abstract_enricher, "_elsevier_retry_at", 0.0), patch.dict("os.environ", {"ELSEVIER_API_KEY": "test-key"}):
            with patch("papers.services.abstract_enricher.requests.get", return_value=response) as get:
                self.assertEqual(abstract_enricher.fetch_elsevier_abstract("10.1016/example"), "")
                self.assertEqual(abstract_enricher.fetch_elsevier_abstract("10.1016/example"), "")
                get.assert_called_once()

    def test_elsevier_without_key_does_not_call_api(self):
        with patch.dict("os.environ", {"ELSEVIER_API_KEY": ""}):
            with patch("papers.services.abstract_enricher.requests.get") as get:
                self.assertEqual(abstract_enricher.fetch_elsevier_abstract("10.1016/example"), "")
                get.assert_not_called()

    def test_elsevier_abstract_response(self):
        response = Mock(status_code=200)
        response.json.return_value = {"full-text-retrieval-response": {"coredata": {"dc:description": "<p>Abstract text.</p>"}}}
        with patch.object(abstract_enricher, "_elsevier_retry_at", 0.0), patch.dict("os.environ", {"ELSEVIER_API_KEY": "test-key"}):
            with patch("papers.services.abstract_enricher.requests.get", return_value=response):
                self.assertEqual(abstract_enricher.fetch_elsevier_abstract("10.1016/example"), "text.")

    def test_semantic_scholar_429_cools_down(self):
        response = Mock(status_code=429, headers={"Retry-After": "600"})
        with patch.object(abstract_enricher, "_semantic_retry_at", 0.0):
            with patch("papers.services.abstract_enricher.requests.get", return_value=response) as get:
                self.assertEqual(abstract_enricher.fetch_semantic_scholar_abstract("10.1234/example"), "")
                self.assertEqual(abstract_enricher.fetch_semantic_scholar_abstract("10.1234/example"), "")
                get.assert_called_once()

    def test_semantic_scholar_connection_failure_cools_down(self):
        with patch.object(abstract_enricher, "_semantic_retry_at", 0.0):
            with patch("papers.services.abstract_enricher.requests.get", side_effect=requests.ConnectionError("offline")) as get:
                self.assertEqual(abstract_enricher.fetch_semantic_scholar_abstract("10.1234/example"), "")
                self.assertEqual(abstract_enricher.fetch_semantic_scholar_abstract("10.1234/example"), "")
                get.assert_called_once()
