from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from papers.models import Paper, RssSource
from papers.services.low_score_retention import prune_low_score_content
from papers.services.rss_fetcher import find_existing_paper, upsert_paper, fetch_source
from papers.services.runtime_settings import save_runtime_rules


class DedupAndRetentionTests(TestCase):
    def setUp(self):
        self.source = RssSource.objects.create(name="Feed", url="https://example.org/rss")

    def test_indexed_keys_match_hidden_and_normalized_records(self):
        paper = Paper.objects.create(
            title="  Hydrogen   storage  study ", doi="https://doi.org/10.1234/ABC",
            dedup_key="indexed-paper", is_soft_deleted=True,
        )
        self.assertEqual(paper.normalized_doi, "10.1234/abc")
        self.assertEqual(find_existing_paper({"doi": "doi:10.1234/abc"}).pk, paper.pk)
        self.assertEqual(find_existing_paper({"title": "hydrogen storage STUDY"}).pk, paper.pk)
        paper.doi = "10.1234/new"
        paper.title = "Updated   title"
        paper.save(update_fields=["doi", "title"])
        self.assertIsNone(find_existing_paper({"doi": "10.1234/abc", "title": "No match"}))
        self.assertEqual(find_existing_paper({"doi": "https://doi.org/10.1234/NEW"}).pk, paper.pk)
        self.assertEqual(find_existing_paper({"title": "updated title"}).pk, paper.pk)

    @patch("papers.services.rss_fetcher.score_paper")
    @patch("papers.services.rss_fetcher.enrich_abstract", side_effect=lambda data, **kwargs: data)
    @patch("papers.services.rss_fetcher.enrich_with_crossref", side_effect=lambda data: data)
    @patch("papers.services.rss_fetcher.feedparser.parse")
    @patch("papers.services.rss_fetcher.requests.get")
    def test_new_item_after_thirty_duplicates_is_not_skipped(self, get, parse, _crossref, _abstract, _score):
        for number in range(30):
            Paper.objects.create(title=f"Existing {number}", dedup_key=f"existing-{number}")
        get.return_value.content = b"rss"
        get.return_value.raise_for_status.return_value = None
        parse.return_value = SimpleNamespace(
            bozo=False,
            entries=[{"title": f"Existing {number}"} for number in range(30)] + [{"title": "New after old entries"}],
        )
        result = fetch_source(self.source)
        self.assertEqual(result["new_count"], 1)
        self.assertTrue(Paper.objects.filter(title="New after old entries").exists())

    def test_old_low_score_paper_is_compacted_and_never_rehydrated(self):
        now = timezone.now()
        paper = Paper.objects.create(
            title="Hydrogen storage system", doi="10.1234/low", url="https://example.org/low",
            abstract="Long abstract " * 100, authors="Author", raw_keywords="hydrogen",
            ai_summary="AI summary", recommend_score=2, dedup_key="old-low",
        )
        Paper.objects.filter(pk=paper.pk).update(created_at=now - timedelta(days=91))
        self.assertEqual(prune_low_score_content(now=now), 1)
        paper.refresh_from_db()
        self.assertIsNotNone(paper.content_pruned_at)
        self.assertEqual(paper.abstract, "")
        self.assertEqual(paper.ai_summary, "")
        self.assertEqual(paper.authors, "")
        self.assertEqual(paper.doi, "10.1234/low")
        self.assertEqual(paper.url, "https://example.org/low")
        self.assertEqual(prune_low_score_content(now=now), 0)
        found, created = upsert_paper({"title": paper.title, "doi": paper.doi, "abstract": "restored"}, self.source)
        self.assertFalse(created)
        self.assertEqual(found.pk, paper.pk)
        paper.refresh_from_db()
        self.assertEqual(paper.abstract, "")
        self.assertEqual(Paper.objects.count(), 1)

    def test_retention_respects_config_and_protected_papers(self):
        save_runtime_rules({"low_score_retention_days": 120})
        now = timezone.now()
        young = Paper.objects.create(title="Young", dedup_key="young", recommend_score=0)
        favorite = Paper.objects.create(title="Favorite", dedup_key="favorite", recommend_score=0, is_favorite=True)
        imported = Paper.objects.create(title="Imported", dedup_key="imported", recommend_score=0, zotero_imported=True)
        for paper in (young, favorite, imported):
            Paper.objects.filter(pk=paper.pk).update(created_at=now - timedelta(days=100 if paper == young else 150))
        self.assertEqual(prune_low_score_content(now=now), 0)
        self.assertEqual(Paper.objects.filter(content_pruned_at__isnull=True).count(), 3)

    def test_low_score_defaults_to_recent_and_all_history_is_available(self):
        now = timezone.now()
        recent = Paper.objects.create(title="Recent", dedup_key="recent", recommend_score=1)
        old = Paper.objects.create(title="Old", dedup_key="old", recommend_score=1)
        Paper.objects.filter(pk=old.pk).update(created_at=now - timedelta(days=100))
        client = APIClient()
        client.force_authenticate(get_user_model().objects.create_user("reader", password="test"))
        response = client.get("/api/papers/low-score/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.data["results"]], [recent.pk])
        response = client.get("/api/papers/low-score/", {"history_scope": "all"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        Paper.objects.filter(pk=old.pk).update(content_pruned_at=now)
        response = client.get("/api/papers/low-score/", {"history_scope": "all"})
        self.assertEqual(response.data["count"], 1)
