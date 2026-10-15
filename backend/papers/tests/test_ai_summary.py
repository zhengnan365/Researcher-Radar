from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from papers.models import Paper, SystemSetting


class AiSummaryTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(get_user_model().objects.create_user("reader", password="password"))
        self.paper = Paper.objects.create(
            title="Battery durability study",
            abstract="The study measures capacity retention over repeated charge cycles.",
            dedup_key="battery-summary",
        )

    def test_summary_is_on_demand_and_saved(self):
        response = Mock(status_code=200)
        response.json.return_value = {"choices": [{"message": {"content": "研究问题：电池寿命。\n结论：摘要未提供定量结果。"}}]}
        with patch.dict("os.environ", {"LITERATURE_AI_API_KEY": "test-key", "LITERATURE_AI_MODEL": "test-model"}):
            with patch("papers.services.ai_summary.requests.post", return_value=response) as post:
                result = self.client.post(f"/api/papers/{self.paper.pk}/ai-summary/")

        self.assertEqual(result.status_code, 200, result.data)
        self.paper.refresh_from_db()
        self.assertIn("电池寿命", self.paper.ai_summary)
        self.assertEqual(self.paper.ai_summary_model, "test-model")
        self.assertIn(self.paper.abstract, post.call_args.kwargs["json"]["messages"][1]["content"])
        self.assertEqual(post.call_args.kwargs["json"]["max_tokens"], 450)

    def test_missing_abstract_is_not_summarized(self):
        self.paper.abstract = ""
        self.paper.save(update_fields=["abstract"])
        response = self.client.post(f"/api/papers/{self.paper.pk}/ai-summary/")
        self.assertEqual(response.status_code, 400)

    def test_admin_can_save_deepseek_settings_without_exposing_key(self):
        admin = get_user_model().objects.create_superuser("admin", "admin@example.org", "password")
        self.client.force_authenticate(admin)
        payload = {
            "provider": "deepseek",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-flash",
            "api_key": "secret-test-key",
        }
        result = self.client.post("/api/settings/ai/", payload, format="json")
        self.assertEqual(result.status_code, 200, result.data)
        self.assertTrue(result.data["has_api_key"])
        self.assertNotIn("api_key", result.data)
        saved = SystemSetting.objects.get(key="ai_summary_provider")
        self.assertNotIn("secret-test-key", str(saved.value))
        self.assertNotIn("secret-test-key", str(self.client.get("/api/settings/ai/").data))

        self.client.force_authenticate(get_user_model().objects.get(username="reader"))
        self.assertEqual(self.client.get("/api/settings/ai/").status_code, 200)
        self.assertNotIn("api_key", self.client.get("/api/settings/ai/").data)
        updated = self.client.post("/api/settings/ai/", {
            "provider": "deepseek", "base_url": "https://api.deepseek.com",
            "model": "deepseek-flash", "api_key": "",
        }, format="json")
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertTrue(updated.data["has_api_key"])

        response = Mock(status_code=200)
        response.json.return_value = {"choices": [{"message": {"content": "研究问题：电池寿命。"}}]}
        with patch("papers.services.ai_summary.requests.post", return_value=response) as post:
            result = self.client.post(f"/api/papers/{self.paper.pk}/ai-summary/")
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(post.call_args.args[0], "https://api.deepseek.com/chat/completions")
        self.assertEqual(post.call_args.kwargs["json"]["model"], "deepseek-flash")
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer secret-test-key")

    def test_ai_settings_reject_insecure_remote_url(self):
        admin = get_user_model().objects.create_superuser("admin", "admin@example.org", "password")
        self.client.force_authenticate(admin)
        result = self.client.post("/api/settings/ai/", {
            "provider": "custom", "base_url": "http://example.org/v1", "model": "test", "api_key": "secret"
        }, format="json")
        self.assertEqual(result.status_code, 400)
        result = self.client.post("/api/settings/ai/", {
            "provider": "deepseek", "base_url": "https://api.deepseek.com", "model": "deepseek-flash"
        }, format="json")
        self.assertEqual(result.status_code, 400)
        self.assertFalse(SystemSetting.objects.filter(key="ai_summary_provider").exists())
