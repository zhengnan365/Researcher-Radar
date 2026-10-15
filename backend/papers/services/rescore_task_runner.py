from __future__ import annotations

import logging
import os
import threading
import traceback
from datetime import timedelta

from django.db import close_old_connections
from django.db.models.functions import TruncDate
from django.utils import timezone

from papers.models import DailyReport, Keyword, Paper, RescoreTask
from papers.services.relevance_scorer import get_score_rules, score_paper
from papers.services.report_generator import generate_daily_report
from papers.services.task_lock import task_start_lock
from papers.services.task_process import mark_orphaned_tasks


logger = logging.getLogger(__name__)
ACTIVE_STATUSES = ("pending", "running")
_start_lock = threading.Lock()


def rescore_queryset(scope: str):
    queryset = Paper.objects.filter(content_pruned_at__isnull=True).order_by("id")
    if scope in {"7", "30"}:
        queryset = queryset.filter(created_at__gte=timezone.now() - timedelta(days=int(scope)))
    return queryset


def get_active_rescore_task() -> RescoreTask | None:
    close_stale_rescore_tasks()
    return RescoreTask.objects.filter(status__in=ACTIVE_STATUSES).first()


def start_rescore_task(scope: str = "all") -> tuple[RescoreTask, bool]:
    if scope not in {"7", "30", "all"}:
        raise ValueError("重新评分范围无效。")
    with _start_lock:
        with task_start_lock():
            active = get_active_rescore_task()
            if active:
                return active, False
            task = RescoreTask.objects.create(scope=scope, target_count=rescore_queryset(scope).count(), message="等待重新评分", worker_pid=os.getpid())
        thread = threading.Timer(0.1, run_rescore_task, args=(task.pk,))
        thread.daemon = True
        thread.start()
        return task, True


def run_rescore_task(task_pk: int) -> None:
    close_old_connections()
    task = RescoreTask.objects.get(pk=task_pk)
    task.status = "running"
    task.started_at = timezone.now()
    task.message = f"正在重新评分：0/{task.target_count}"
    task.save(update_fields=["status", "started_at", "message", "updated_at"])
    try:
        keywords = list(Keyword.objects.filter(enabled=True).select_related("direction"))
        rules = get_score_rules()
        queryset = rescore_queryset(task.scope)
        report_dates = list(
            DailyReport.objects.filter(report_date__in=queryset.annotate(day=TruncDate("created_at")).values("day"))
            .values_list("report_date", flat=True)
            .distinct()
        )
        for paper in queryset.iterator(chunk_size=100):
            try:
                score_paper(paper, keywords=keywords, rules=rules)
            except Exception:
                task.failed_count += 1
                logger.exception("Rescore failed for paper_id=%s", paper.pk)
                task.error_detail = "\n".join([task.error_detail, f"paper_id={paper.pk}: {traceback.format_exc()}"]).strip()[-12000:]
            task.processed_count += 1
            if task.processed_count % 10 == 0 or task.processed_count == task.target_count:
                task.message = f"正在重新评分：{task.processed_count}/{task.target_count}"
                task.save(update_fields=["processed_count", "failed_count", "message", "error_detail", "updated_at"])

        refreshed_reports = 0
        if task.failed_count == 0:
            for report_date in report_dates:
                generate_daily_report(report_date)
                refreshed_reports += 1
        task.status = "partial" if task.failed_count else "success"
        task.message = f"重新评分完成：{task.processed_count - task.failed_count}/{task.target_count} 篇，失败 {task.failed_count} 篇；刷新日报 {refreshed_reports} 份"
    except Exception:
        task.status = "failed"
        task.message = "重新评分任务失败"
        task.error_detail = traceback.format_exc()[-12000:]
        logger.exception("Rescore task failed task_id=%s", task.task_id)
    finally:
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "processed_count", "failed_count", "message", "error_detail", "finished_at", "updated_at"])
        close_old_connections()


def close_stale_rescore_tasks() -> None:
    mark_orphaned_tasks(RescoreTask, message="后台进程已退出，请重新评分", timeout=timedelta(hours=3))


def rescore_task_payload(task: RescoreTask) -> dict:
    return {
        "task_id": str(task.task_id), "status": task.status, "scope": task.scope,
        "target_count": task.target_count, "processed_count": task.processed_count,
        "failed_count": task.failed_count, "message": task.message,
        "error_detail": task.error_detail if task.status in {"failed", "partial"} else "",
        "started_at": task.started_at, "finished_at": task.finished_at,
    }
