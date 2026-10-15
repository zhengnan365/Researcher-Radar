from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from papers.models import Keyword, ResearchDirection, RssSource, SystemSetting, ZoteroConfig
from papers.services.ai_config import get_ai_config, save_ai_config
from papers.services.runtime_settings import get_runtime_rules, save_runtime_rules


User = get_user_model()


class ConfigTransferApiTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", "admin@example.com", "password")
        self.user = User.objects.create_user("reader", password="password")
        self.client = APIClient()
        self.direction = ResearchDirection.objects.create(name="储能")
        Keyword.objects.create(keyword="battery", aliases="cell", is_exclusion=True, direction=self.direction)
        self.source = RssSource.objects.create(
            name="Applied Energy",
            url="https://example.com/feed.xml",
            journal="Applied Energy",
            total_fetched_count=321,
        )
        ZoteroConfig.objects.create(
            name="default",
            library_type="user",
            user_id="123456",
            api_key="secret-access-key",
            enabled=True,
        )

    def test_export_requires_login_and_contains_shared_settings(self):
        response = self.client.get("/api/settings/config/export/")
        self.assertIn(response.status_code, (401, 403))

        save_ai_config({
            "provider": "deepseek", "base_url": "https://api.deepseek.com",
            "model": "deepseek-flash", "api_key": "secret-ai-key",
        })
        self.client.force_authenticate(self.user)
        response = self.client.get("/api/settings/config/export/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "no-store")
        payload = json.loads(response.content)
        self.assertEqual(payload["format"], "literature-daily-config")
        self.assertTrue(payload["contains_secrets"])
        self.assertEqual(payload["version"], 3)
        self.assertEqual(payload["data"]["zotero"]["api_key"], "secret-access-key")
        self.assertEqual(payload["data"]["ai"]["api_key"], "secret-ai-key")
        self.assertEqual(payload["data"]["ai"]["model"], "deepseek-flash")
        self.assertNotIn("description", payload["data"]["research_directions"][0])
        self.assertEqual(payload["data"]["keywords"][0]["aliases"], "cell")
        self.assertTrue(payload["data"]["keywords"][0]["is_exclusion"])
        self.assertNotIn("category", payload["data"]["keywords"][0])
        for retired_field in ("publisher", "category", "direction"):
            self.assertNotIn(retired_field, payload["data"]["rss_sources"][0])

    def test_import_merges_configuration_and_preserves_fetch_statistics(self):
        self.client.force_authenticate(self.admin)
        exported = self.client.get("/api/settings/config/export/")
        payload = json.loads(exported.content)
        payload["data"]["research_directions"][0]["direction_weight"] = 5
        payload["data"]["rss_sources"][0].update({"publisher": "旧出版社", "category": "旧分类", "direction": "储能"})
        payload["data"]["keywords"].append(
            {
                "keyword": "energy storage",
                "weight": 2,
                "enabled": True,
                "description": "",
                "direction": "储能",
            }
        )
        payload["data"]["zotero"]["api_key"] = "new-secret-key"

        response = self.client.post("/api/settings/config/import/", payload, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.direction.refresh_from_db()
        self.source.refresh_from_db()
        self.assertEqual(self.direction.direction_weight, 5)
        self.assertEqual(self.source.total_fetched_count, 321)
        self.assertEqual(Keyword.objects.get(keyword="energy storage").direction, self.direction)
        self.assertEqual(ZoteroConfig.get_active().api_key, "new-secret-key")

    def test_import_restores_ai_config_and_accepts_version_2(self):
        self.client.force_authenticate(self.user)
        response = self.client.post("/api/settings/config/import/", {
            "format": "literature-daily-config", "version": 3,
            "data": {"ai": {
                "provider": "custom", "base_url": "https://example.org/v1",
                "model": "example-model", "api_key": "portable-key",
            }},
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(get_ai_config(include_key=True)["api_key"], "portable-key")
        self.assertNotIn("portable-key", str(SystemSetting.objects.get(key="ai_summary_provider").value))
        exported = json.loads(self.client.get("/api/settings/config/export/").content)
        self.assertEqual(exported["data"]["ai"]["api_key"], "portable-key")

        legacy = {"format": "literature-daily-config", "version": 2, "data": {"scoring_rules": exported["data"]["scoring_rules"]}}
        response = self.client.post("/api/settings/config/import/", legacy, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(get_ai_config(include_key=True)["api_key"], "portable-key")

    def test_export_import_restores_every_in_app_setting(self):
        self.client.force_authenticate(self.user)
        self.direction.name_en = "Energy Storage"
        self.direction.direction_weight = 5
        self.direction.priority = 4
        self.direction.save()
        keyword = Keyword.objects.get(keyword="battery")
        keyword.weight = 4
        keyword.save()
        self.source.fetch_mode = "both"
        self.source.openalex_issn = "1234-5678"
        self.source.save()
        save_runtime_rules({**get_runtime_rules(), "daily_max_papers": 25})
        save_ai_config({
            "provider": "custom", "base_url": "https://example.org/v1",
            "model": "example-model", "api_key": "portable-ai-key",
        })
        payload = json.loads(self.client.get("/api/settings/config/export/").content)

        self.direction.name_en = None
        self.direction.direction_weight = 1
        self.direction.priority = 1
        self.direction.save()
        keyword.aliases = ""
        keyword.is_exclusion = False
        keyword.weight = 1
        keyword.save()
        self.source.fetch_mode = "rss"
        self.source.openalex_issn = ""
        self.source.save()
        save_runtime_rules({**get_runtime_rules(), "daily_max_papers": 80})
        zotero = ZoteroConfig.get_active()
        zotero.api_key = "changed-key"
        zotero.save()
        save_ai_config({
            "provider": "deepseek", "base_url": "https://api.deepseek.com",
            "model": "changed-model", "api_key": "changed-ai-key",
        })

        response = self.client.post("/api/settings/config/import/", payload, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.direction.refresh_from_db()
        keyword.refresh_from_db()
        self.source.refresh_from_db()
        self.assertEqual((self.direction.name_en, self.direction.direction_weight, self.direction.priority), ("Energy Storage", 5, 4))
        self.assertEqual((keyword.aliases, keyword.is_exclusion, keyword.weight), ("cell", True, 4))
        self.assertEqual((self.source.fetch_mode, self.source.openalex_issn), ("both", "1234-5678"))
        self.assertEqual(get_runtime_rules()["daily_max_papers"], 25)
        self.assertEqual(ZoteroConfig.get_active().api_key, "secret-access-key")
        self.assertEqual((get_ai_config(include_key=True)["model"], get_ai_config(include_key=True)["api_key"]), ("example-model", "portable-ai-key"))

    def test_invalid_ai_config_rolls_back_other_imported_settings(self):
        self.client.force_authenticate(self.user)
        response = self.client.post("/api/settings/config/import/", {
            "format": "literature-daily-config", "version": 3,
            "data": {
                "research_directions": [{"name": "储能", "direction_weight": 5}],
                "ai": {"provider": "custom", "base_url": "http://example.org/v1", "model": "test", "api_key": "secret"},
            },
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.direction.refresh_from_db()
        self.assertEqual(self.direction.direction_weight, 3)
        self.assertFalse(SystemSetting.objects.filter(key="ai_summary_provider").exists())

    def test_invalid_import_rolls_back_every_change(self):
        self.client.force_authenticate(self.admin)
        payload = {
            "format": "literature-daily-config",
            "version": 1,
            "data": {
                "research_directions": [
                    {"name": "储能", "direction_weight": 5, "enabled": True},
                ],
                "rss_sources": [
                    {"name": "无效源", "url": "not-a-url", "enabled": True},
                ],
            },
        }
        response = self.client.post("/api/settings/config/import/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.direction.refresh_from_db()
        self.assertEqual(self.direction.direction_weight, 3)
    def test_import_accepts_openalex_only_source_without_rss_url(self):
        self.client.force_authenticate(self.admin)
        payload = {
            "format": "literature-daily-config",
            "version": 1,
            "data": {"rss_sources": [{
                "name": "OpenAlex only", "url": "", "fetch_mode": "openalex",
                "openalex_issn": "1234-5678", "enabled": True,
            }]},
        }
        response = self.client.post("/api/settings/config/import/", payload, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(RssSource.objects.get(name="OpenAlex only").openalex_issn, "1234-5678")

    def test_import_ignores_removed_profile_fields_from_old_config(self):
        self.client.force_authenticate(self.admin)
        payload = {
            "format": "literature-daily-config",
            "version": 1,
            "data": {"research_directions": [{
                "name": "储能", "description": "更新后的说明", "profile_terms": {"battery": "invalid"},
                "profile_item_count": 3,
            }]},
        }
        response = self.client.post("/api/settings/config/import/", payload, format="json")

        self.assertEqual(response.status_code, 200, response.data)
        self.direction.refresh_from_db()
        exported = json.loads(self.client.get("/api/settings/config/export/").content)
        self.assertNotIn("profile_terms", exported["data"]["research_directions"][0])
        self.assertNotIn("description", exported["data"]["research_directions"][0])
