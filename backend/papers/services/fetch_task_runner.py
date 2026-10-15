from __future__ import annotations

import threading
import os
import traceback
from datetime import timedelta

from django.db import close_old_connections
from django.utils import timezone

from papers.models import FetchTask, RssSource
from papers.services.report_generator import generate_daily_report
from papers.services.rss_fetcher import FetchSummary, fetch_all_enabled_sources
from papers.services.task_lock import task_start_lock
from papers.services.task_process import mark_orphaned_tasks


ACTIVE_STATUSES = ("pending", "running")
STALE_AFTER = timedelta(hours=6)


def get_active_fetch_task() -> FetchTask | None:
    close_stale_fetch_tasks()
    return FetchTask.objects.filter(status__in=ACTIVE_STATUSES).order_by("-created_at").first()


def start_fetch_task() -> tuple[FetchTask, bool]:
    with task_start_lock():
        active_task = get_active_fetch_task()
        if active_task:
            return active_task, False
        task = FetchTask.objects.create(status="pending", message="等待抓取", worker_pid=os.getpid())
    thread = threading.Timer(0.1, run_fetch_task, args=(task.pk,))
    thread.daemon = True
    thread.start()
    return task, True


def run_fetch_task(task_pk: int) -> None:
    close_old_connections()
    task = FetchTask.objects.get(pk=task_pk)
    task.status = "running"
    task.message = "正在抓取 RSS"
    task.started_at = timezone.now()
    task.source_total = RssSource.objects.filter(enabled=True).count()
    task.save(update_fields=["status", "message", "started_at", "source_total", "updated_at"])

    try:
        summary = fetch_all_enabled_sources(progress_callback=lambda summary, source, index, phase: update_fetch_progress(task.pk, summary, source, index, phase))
        task.message = "正在生成日报"
        task.save(update_fields=["message", "updated_at"])

        report = generate_daily_report()
        task.status = "success"
        task.message = f"抓取完成：新入库 {summary.new_count} 篇，已存在 {summary.duplicate_count} 篇"
        task.source_total = summary.source_total
        task.success_sources = summary.success_sources
        task.failed_sources = summary.failed_sources
        task.fetched_count = summary.fetched_count
        task.new_count = summary.new_count
        task.duplicate_count = summary.duplicate_count
        task.report_date = report.report_date
        task.report_title = report.title
        task.paper_count = report.paper_count
        task.finished_at = timezone.now()
        task.save()
    except Exception as exc:  # pragma: no cover - external networks make this path environment dependent
        task.status = "failed"
        task.message = f"自动抓取失败：{exc}"
        task.error_detail = traceback.format_exc()
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "message", "error_detail", "finished_at", "updated_at"])
    finally:
        close_old_connections()


def update_fetch_progress(task_pk: int, summary: FetchSummary, source: RssSource | None, index: int, phase: str) -> None:
    """Persist coarse progress so the frontend does not look frozen."""
    message = "正在抓取 RSS"
    if source and phase == "source_started":
        message = f"正在抓取 RSS：{index}/{summary.source_total} {source.name}"
    elif source and phase == "source_finished":
        message = f"已完成 RSS：{index}/{summary.source_total} {source.name}"

    FetchTask.objects.filter(pk=task_pk, status__in=ACTIVE_STATUSES).update(
        message=message,
        source_total=summary.source_total,
        success_sources=summary.success_sources,
        failed_sources=summary.failed_sources,
        fetched_count=summary.fetched_count,
        new_count=summary.new_count,
        duplicate_count=summary.duplicate_count,
        updated_at=timezone.now(),
    )


def close_stale_fetch_tasks() -> None:
    mark_orphaned_tasks(FetchTask, message="后台进程已退出，请重新抓取", timeout=STALE_AFTER)
