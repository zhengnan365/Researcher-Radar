from unittest import TestCase
from unittest.mock import patch

import requests

from papers.services import abstract_enricher


class QuickAbstractEnrichmentTests(TestCase):
    def test_quick_lookup_skips_title_search_without_doi(self):
        with patch.object(abstract_enricher, "fetch_openalex_title_abstract") as title_lookup:
            result = abstract_enricher.enrich_abstract({"title": "Example"}, quick=True)
        self.assertEqual(result, {"title": "Example"})
        title_lookup.assert_not_called()

    def test_quick_lookup_cools_down_after_connection_failure(self):
        data = {"doi": "10.1000/example", "title": "Example"}
        with patch.object(abstract_enricher, "_quick_openalex_retry_at", 0.0), patch.object(
            abstract_enricher, "fetch_openalex_abstract", side_effect=requests.exceptions.SSLError("disconnected")
        ) as lookup:
            self.assertEqual(abstract_enricher.enrich_abstract(data, quick=True), data)
            self.assertEqual(abstract_enricher.enrich_abstract(data, quick=True), data)
            lookup.assert_called_once_with("10.1000/example", timeout=3)

    def test_quick_lookup_keeps_original_metadata(self):
        data = {"doi": "10.1000/example", "title": "Example"}
        with patch.object(abstract_enricher, "_quick_openalex_retry_at", 0.0), patch.object(
            abstract_enricher, "fetch_openalex_abstract", return_value="Abstract text"
        ):
            result = abstract_enricher.enrich_abstract(data, quick=True)
        self.assertEqual(result["abstract"], "Abstract text")
        self.assertNotIn("abstract", data)
