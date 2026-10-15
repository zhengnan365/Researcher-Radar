from unittest import TestCase
from unittest.mock import patch

import requests

from papers.services import metadata_enricher


class CrossrefCooldownTests(TestCase):
    def test_connection_failure_skips_repeated_doi_and_title_lookups(self):
        data = {"doi": "10.1000/example", "title": "Example"}
        with patch.object(metadata_enricher, "_crossref_retry_at", 0.0), patch.object(
            metadata_enricher.requests, "get", side_effect=requests.exceptions.SSLError("disconnected")
        ) as get:
            self.assertEqual(metadata_enricher.enrich_with_crossref(data), data)
            self.assertEqual(metadata_enricher.enrich_with_crossref(data), data)
            self.assertIsNone(metadata_enricher.search_crossref_by_title("Example"))
            get.assert_called_once()
