from unittest.mock import patch
import threading
import time

from django.contrib.auth import get_user_model
from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient

from papers.models import AbstractUpdateTask, DailyReport, FetchTask, Keyword, LoginAttempt, Paper
from papers.services.abstract_task_runner import run_abstract_update_task
from papers.services.fetch_task_runner import close_stale_fetch_tasks
from papers.services.task_lock import task_start_lock


class LoginAndTaskSafetyTests(TestCase):
    def test_login_is_temporarily_limited_after_repeated_failures(self):
        get_user_model().objects.create_user("admin", password="correct-password")
        client = APIClient()
        for _ in range(8):
            self.assertEqual(
                client.post("/api/auth/login/", {"username": "admin", "password": "wrong"}).status_code,
                400,
            )
        self.assertEqual(APIClient().post("/api/auth/login/", {"username": "admin", "password": "correct-password"}).status_code, 429)
        attempt = LoginAttempt.objects.get()
        attempt.expires_at = timezone.now() - timedelta(seconds=1)
        attempt.save(update_fields=["expires_at"])
        self.assertEqual(APIClient().post("/api/auth/login/", {"username": "admin", "password": "correct-password"}).status_code, 200)
        self.assertFalse(LoginAttempt.objects.exists())

    @patch("papers.services.task_process.psutil.pid_exists", return_value=True)
    def test_live_other_worker_task_is_not_marked_failed(self, _pid_exists):
        task = FetchTask.objects.create(status="running", worker_pid=42)
        close_stale_fetch_tasks()
        task.refresh_from_db()
        self.assertEqual(task.status, "running")

    @patch("papers.services.task_process.psutil.pid_exists", return_value=False)
    def test_dead_worker_task_is_marked_failed(self, _pid_exists):
        task = FetchTask.objects.create(status="running", worker_pid=42)
        close_stale_fetch_tasks()
        task.refresh_from_db()
        self.assertEqual(task.status, "failed")

    @patch("papers.services.abstract_task_runner.enrich_abstract", return_value={"abstract": "Battery scheduling operation"})
    def test_abstract_update_rescores_paper_and_report(self, _enrich):
        Keyword.objects.create(keyword="battery", weight=5)
        paper = Paper.objects.create(title="Battery scheduling", dedup_key="abstract-rescore")
        task = AbstractUpdateTask.objects.create(status="pending", paper_ids=[paper.pk], target_count=1)
        run_abstract_update_task(task.pk)
        paper.refresh_from_db()
        task.refresh_from_db()
        self.assertEqual(task.updated, 1)
        self.assertGreaterEqual(paper.recommend_score, 18)
        self.assertTrue(DailyReport.objects.filter(paper_count=1).exists())


class TaskStartLockTests(TransactionTestCase):
    def test_concurrent_starts_are_serialized(self):
        entered = threading.Event()
        release = threading.Event()
        events = []
        errors = []

        def first():
            try:
                with task_start_lock():
                    events.append("first")
                    entered.set()
                    release.wait(timeout=3)
            except Exception as exc:
                errors.append(exc)
            finally:
                close_old_connections()

        def second():
            entered.wait(timeout=3)
            try:
                with task_start_lock():
                    events.append("second")
            except Exception as exc:
                errors.append(exc)
            finally:
                close_old_connections()

        a = threading.Thread(target=first)
        b = threading.Thread(target=second)
        a.start()
        b.start()
        time.sleep(0.1)
        self.assertEqual(events, ["first"])
        release.set()
        a.join(timeout=5)
        b.join(timeout=5)
        self.assertFalse(a.is_alive() or b.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(events, ["first", "second"])
