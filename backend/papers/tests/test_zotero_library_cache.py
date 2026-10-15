from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from papers.models import ZoteroCollection, ZoteroItem, ZoteroSyncState
from papers.services.zotero_api import read_zotero_library, read_zotero_library_from_db


User = get_user_model()


class ZoteroLibraryCacheTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("reader", password="password")
        ZoteroCollection.objects.create(key="COLLECTION1", name="储能")
        self.item = ZoteroItem.objects.create(
            key="ITEM0001",
            title="Energy storage paper",
            creator="Author One",
            creators=[{"name": "Author One", "type": "author"}],
            doi="10.1000/example",
            journal="Applied Energy",
            date="2026",
            item_type="journalArticle",
            abstract="A long abstract that should not be included in the initial library payload.",
            tags=["energy storage"],
            collections=[{"key": "COLLECTION1", "name": "储能"}],
        )

    def test_library_payload_is_lightweight_and_detail_is_complete(self):
        payload = read_zotero_library_from_db(max_items=0)
        self.assertEqual(payload["total_items"], 1)
        self.assertNotIn("grouped", payload)
        self.assertNotIn("abstract", payload["items"][0])
        self.assertEqual(payload["items"][0]["collections"][0]["key"], "COLLECTION1")

        client = APIClient()
        client.force_authenticate(self.user)
        response = client.get("/api/zotero/items/ITEM0001/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["abstract"], self.item.abstract)
        self.assertEqual(response.data["tags"], ["energy storage"])

    @patch("papers.services.zotero_api.start_zotero_sync_background")
    def test_successfully_synced_empty_library_does_not_restart_full_sync(self, start_sync):
        self.item.delete()
        ZoteroCollection.objects.all().delete()
        ZoteroSyncState.objects.create(last_synced_at=timezone.now(), sync_status="success")

        payload = read_zotero_library(max_items=0, refresh=False)

        self.assertEqual(payload["cached_total_items"], 0)
        self.assertEqual(payload["sync_state"]["status"], "success")
        start_sync.assert_not_called()

    @patch("papers.services.zotero_api.start_zotero_sync_background")
    def test_failed_first_sync_waits_for_manual_retry(self, start_sync):
        self.item.delete()
        ZoteroCollection.objects.all().delete()
        ZoteroSyncState.objects.create(sync_status="failed", sync_error="Zotero 连接失败")

        payload = read_zotero_library(max_items=0, refresh=False)

        self.assertEqual(payload["sync_state"]["status"], "failed")
        self.assertEqual(payload["sync_state"]["error"], "Zotero 连接失败")
        start_sync.assert_not_called()

    def test_library_metadata_does_not_send_all_items(self):
        payload = read_zotero_library_from_db(max_items=0, include_items=False)
        self.assertEqual(payload["items"], [])
        self.assertEqual(payload["cached_total_items"], 1)
        self.assertEqual(payload["available_years"], ["2026"])
        self.assertEqual(payload["available_types"], ["journalArticle"])
        self.assertEqual(payload["collection_counts"]["COLLECTION1"], 1)

    def test_paged_library_filters_descendants_search_and_uncategorized(self):
        ZoteroCollection.objects.create(key="CHILD", name="子文件夹", parent_key="COLLECTION1")
        ZoteroItem.objects.create(
            key="ITEM0002", title="Battery research", creator="Second Author", date="2025-04-10",
            item_type="book", collections=[{"key": "CHILD", "name": "子文件夹"}],
        )
        ZoteroItem.objects.create(
            key="ITEM0003", title="Unfiled", creator="Third Author", date="2024", item_type="report",
        )
        client = APIClient()
        client.force_authenticate(self.user)

        response = client.get("/api/zotero/library/items/", {
            "collection": "COLLECTION1", "sort_by": "date", "sort_order": "descending", "page_size": 1,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["folder_total"], 2)
        self.assertEqual(response.data["total"], 2)
        self.assertEqual([row["key"] for row in response.data["items"]], ["ITEM0001"])

        next_page = client.get("/api/zotero/library/items/", {
            "collection": "COLLECTION1", "sort_by": "date", "sort_order": "descending",
            "page_size": 1, "page": 2,
        })
        self.assertEqual(next_page.data["page"], 2)
        self.assertEqual(next_page.data["items"][0]["key"], "ITEM0002")

        response = client.get("/api/zotero/library/items/", {
            "collection": "COLLECTION1", "search": "second", "year": "2025", "page": 99,
        })
        self.assertEqual(response.data["page"], 1)
        self.assertEqual(response.data["folder_total"], 2)
        self.assertEqual(response.data["total"], 1)
        self.assertEqual(response.data["items"][0]["key"], "ITEM0002")

        response = client.get("/api/zotero/library/items/", {"collection": "uncategorized"})
        self.assertEqual(response.data["folder_total"], 1)
        self.assertEqual(response.data["items"][0]["key"], "ITEM0003")

        response = client.get("/api/zotero/library/items/", {"page_size": 201})
        self.assertEqual(response.status_code, 400)
