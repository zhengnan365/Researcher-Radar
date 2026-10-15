from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from papers.models import Keyword, Paper, RssSource
from papers.services.relevance_scorer import score_paper
from papers.services.rss_fetcher import upsert_paper
from papers.services.rss_generator import generate_favorites_rss


class RelevanceFeedbackTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(get_user_model().objects.create_user("reader", password="password"))
        Keyword.objects.create(keyword="battery", weight=3)
        self.paper = Paper.objects.create(title="Battery durability study", dedup_key="feedback-battery")
        score_paper(self.paper)

    def test_mark_is_hidden_and_survives_rescoring_while_preserving_dedup(self):
        original_score = self.paper.recommend_score
        self.assertGreater(original_score, 0)

        response = self.client.post(f"/api/papers/{self.paper.pk}/mark-irrelevant/")
        self.assertEqual(response.status_code, 200, response.data)
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.recommend_score, 0)
        self.assertEqual(self.paper.system_recommend_score, original_score)
        self.assertEqual(self.paper.recommend_level, "low")
        self.assertEqual(self.paper.relevance_override, "irrelevant")
        self.assertFalse(self.client.get("/api/papers/").data["results"])
        self.assertFalse(self.client.get("/api/papers/low-score/").data["results"])
        self.assertFalse(self.client.get("/api/papers/", {"recommend_level": "low"}).data["results"])
        self.assertEqual(self.client.get("/api/settings/scoring/distribution/").data["total"], 0)
        self.assertEqual(Paper.objects.filter(dedup_key="feedback-battery", relevance_override="irrelevant").count(), 1)
        self.paper.is_favorite = True
        self.paper.save(update_fields=["is_favorite"])
        self.assertNotIn(self.paper.title, generate_favorites_rss())

        response = self.client.post(f"/api/papers/{self.paper.pk}/rescore/")
        self.assertEqual(response.status_code, 200, response.data)
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.recommend_score, 0)
        self.assertEqual(self.paper.system_recommend_score, original_score)

        source = RssSource.objects.create(name="Battery RSS", url="https://example.org/feed")
        reused, created = upsert_paper({"title": self.paper.title, "journal": "Example Journal"}, source)
        self.assertFalse(created)
        self.assertEqual(reused.pk, self.paper.pk)
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.relevance_override, "irrelevant")
        self.assertEqual(self.paper.recommend_score, 0)
        self.assertEqual(Paper.objects.count(), 1)
