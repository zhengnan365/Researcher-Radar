from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from papers.models import DailyReport, Keyword, Paper, RescoreTask
from papers.services.rescore_task_runner import run_rescore_task, start_rescore_task


class RescoreTaskTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(get_user_model().objects.create_user("editor", password="password"))
        Keyword.objects.create(keyword="battery", weight=4)
        self.paper = Paper.objects.create(title="Battery scheduling", dedup_key="rescore-battery")

    @patch("papers.services.rescore_task_runner.threading.Timer")
    def test_start_status_and_run(self, timer):
        response = self.client.post("/api/settings/scoring/rescore/", {"scope": "all"})
        self.assertEqual(response.status_code, 200, response.data)
        task_id = response.data["task"]["task_id"]
        self.assertEqual(response.data["task"]["target_count"], 1)
        timer.return_value.start.assert_called_once()

        duplicate = self.client.post("/api/settings/scoring/rescore/", {"scope": "all"})
        self.assertFalse(duplicate.data["created"])
        blocked = self.client.post("/api/settings/scoring/", {"rules": {"max_score": 100}} , format="json")
        self.assertEqual(blocked.status_code, 409)

        task = RescoreTask.objects.get(task_id=task_id)
        run_rescore_task(task.pk)
        task.refresh_from_db()
        self.paper.refresh_from_db()
        self.assertEqual(task.status, "success")
        self.assertEqual(task.processed_count, 1)
        self.assertGreater(self.paper.recommend_score, 0)
        status = self.client.get(f"/api/settings/scoring/rescore/{task_id}/")
        self.assertEqual(status.data["task"]["status"], "success")

    @patch("papers.services.rescore_task_runner.threading.Timer")
    def test_existing_irrelevant_paper_stays_zero(self, timer):
        self.paper.relevance_override = "irrelevant"
        self.paper.save(update_fields=["relevance_override"])
        task, created = start_rescore_task("all")
        self.assertTrue(created)
        run_rescore_task(task.pk)
        self.paper.refresh_from_db()
        self.assertEqual(self.paper.recommend_score, 0)
        self.assertGreater(self.paper.system_recommend_score, 0)

    @patch("papers.services.rescore_task_runner.threading.Timer")
    def test_existing_daily_report_is_refreshed(self, timer):
        Keyword.objects.update(weight=5)
        self.paper.abstract = "Battery scheduling operation"
        self.paper.save(update_fields=["abstract"])
        report = DailyReport.objects.create(report_date=self.paper.created_at.date(), title="旧日报", paper_count=0)
        task, _ = start_rescore_task("all")
        run_rescore_task(task.pk)
        report.refresh_from_db()
        self.assertEqual(report.paper_count, 1)
        self.assertIn(self.paper.title, report.markdown_content)
