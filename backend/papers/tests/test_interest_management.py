from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from papers.models import Keyword, ResearchDirection


class InterestManagementTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(get_user_model().objects.create_user("editor", password="password"))

    def test_direction_accepts_chinese_name_and_preserves_legacy_name(self):
        response = self.client.post("/api/directions/", {
            "name_cn": "储能系统", "name_en": "Energy Storage Systems", "direction_weight": 4, "priority": 5,
        })
        self.assertEqual(response.status_code, 201, response.data)
        self.assertNotIn("description", response.data)
        direction = ResearchDirection.objects.get(pk=response.data["id"])
        self.assertEqual(direction.name, direction.name_cn)
        self.assertEqual(direction.direction_weight, 4)

    def test_batch_formats_and_keyword_update(self):
        response = self.client.post("/api/directions/bulk-create/", {
            "names": "储能系统\n氢能系统 | Hydrogen Energy Systems | 5 | 4\n储能系统",
            "direction_weight": 3, "priority": 3,
        })
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(ResearchDirection.objects.count(), 2)
        self.assertEqual(ResearchDirection.objects.get(name="储能系统").name_en, None)
        direction = ResearchDirection.objects.get(name="氢能系统")
        self.assertEqual((direction.direction_weight, direction.priority), (5, 4))

        Keyword.objects.create(keyword="SOFC", weight=1)
        response = self.client.post("/api/keywords/bulk-create/", {
            "direction": direction.pk, "weight": 5,
            "keywords": "sofc,SOEC；fuel cell\nSOEC", "update_existing": True,
        })
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Keyword.objects.count(), 3)
        self.assertEqual(Keyword.objects.get(keyword="SOFC").weight, 5)
        self.assertEqual(Keyword.objects.get(keyword="SOFC").direction, direction)
        bad = self.client.post("/api/keywords/bulk-create/", {
            "direction": direction.pk, "weight": 6, "keywords": "hydrogen",
        })
        self.assertEqual(bad.status_code, 400)

    def test_batch_keywords_accept_row_weight_with_uniform_fallback(self):
        direction = ResearchDirection.objects.create(name="热力循环优化")
        Keyword.objects.create(keyword="energy hub", weight=1)
        response = self.client.post("/api/keywords/bulk-create/", {
            "direction": direction.pk, "weight": 2,
            "keywords": "energy hub | 4\nSOFC | 5\ndemand response",
        })
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Keyword.objects.get(keyword="energy hub").weight, 4)
        self.assertEqual(Keyword.objects.get(keyword="SOFC").weight, 5)
        self.assertEqual(Keyword.objects.get(keyword="demand response").weight, 2)
        self.assertEqual(Keyword.objects.get(keyword="demand response").direction, direction)

        count = Keyword.objects.count()
        invalid = self.client.post("/api/keywords/bulk-create/", {
            "direction": direction.pk, "weight": 2,
            "keywords": "valid keyword\ninvalid keyword | 6",
        })
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(Keyword.objects.count(), count)

        old_format = self.client.post("/api/keywords/bulk-create/", {
            "direction": direction.pk, "keywords": "storage | 技术对象 | 5",
        })
        self.assertEqual(old_format.status_code, 400)
        missing_direction = self.client.post("/api/keywords/bulk-create/", {"keywords": "storage | 5"})
        self.assertEqual(missing_direction.status_code, 400)

    def test_single_keyword_requires_direction_and_hides_legacy_category(self):
        direction = ResearchDirection.objects.create(name="综合能源系统")
        missing = self.client.post("/api/keywords/", {"keyword": "energy hub", "weight": 4})
        self.assertEqual(missing.status_code, 400)
        response = self.client.post("/api/keywords/", {
            "keyword": "energy hub", "weight": 4, "direction": direction.pk, "category": "旧分类",
        })
        self.assertEqual(response.status_code, 201, response.data)
        self.assertNotIn("category", response.data)
