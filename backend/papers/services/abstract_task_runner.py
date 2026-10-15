from __future__ import annotations

import threading
import os
import traceback
from datetime import date, timedelta

from django.db import close_old_connections
from django.db.models import Q
from django.utils import timezone

from papers.models import AbstractUpdateTask, Paper
from papers.services.abstract_enricher import enrich_abstract
from papers.services.relevance_scorer import score_paper
from papers.services.report_generator import generate_daily_report
from papers.services.task_lock import task_start_lock
from papers.services.task_process import mark_orphaned_tasks


ACTIVE_STATUSES = ("pending", "running")
STALE_AFTER = timedelta(hours=3)


def get_active_abstract_task() -> AbstractUpdateTask | None:
    close_stale_abstract_tasks()
    return AbstractUpdateTask.objects.filter(status__in=ACTIVE_STATUSES).order_by("-created_at").first()


def start_abstract_update_task(*, paper_ids: list[int] | None = None, selected_date: str = "") -> tuple[AbstractUpdateTask, bool]:
    close_stale_abstract_tasks()
    paper_ids = paper_ids or []
    parsed_date = date.fromisoformat(selected_date) if selected_date else None
    if not paper_ids and not parsed_date:
        raise ValueError("未勾选文献时，请先选择一个日期再更新摘要。")

    queryset = build_missing_abstract_queryset(paper_ids=paper_ids, selected_date=parsed_date)
    target_count = queryset.count()
    with task_start_lock():
        active_task = get_active_abstract_task()
        if active_task:
            return active_task, False
        task = AbstractUpdateTask.objects.create(
            status="pending",
            message="等待更新摘要",
            selected_date=parsed_date,
            paper_ids=paper_ids,
            target_count=target_count,
            worker_pid=os.getpid(),
        )
    thread = threading.Timer(0.1, run_abstract_update_task, args=(task.pk,))
    thread.daemon = True
    thread.start()
    return task, True


def run_abstract_update_task(task_pk: int) -> None:
    close_old_connections()
    task = AbstractUpdateTask.objects.get(pk=task_pk)
    task.status = "running"
    task.message = f"正在更新摘要：0/{task.target_count}"
    task.started_at = timezone.now()
    task.save(update_fields=["status", "message", "started_at", "updated_at"])

    try:
        changed_dates = set()
        queryset = build_missing_abstract_queryset(
            paper_ids=[int(item) for item in task.paper_ids if str(item).isdigit()],
            selected_date=task.selected_date,
        )
        for paper in queryset.iterator(chunk_size=20):
            try:
                enriched = enrich_abstract(
                    {
                        "title": paper.title,
                        "doi": paper.doi or "",
                        "abstract": paper.abstract or "",
                    }
                )
                abstract = str(enriched.get("abstract") or "").strip()
                if abstract:
                    paper.abstract = abstract
                    paper.save(update_fields=["abstract", "updated_at"])
                    score_paper(paper)
                    changed_dates.add(timezone.localtime(paper.created_at).date())
                    task.updated += 1
                else:
                    task.not_found += 1
            except Exception:  # pragma: no cover - depends on external metadata services
                task.failed += 1
                task.error_detail = "\n\n".join([task.error_detail, traceback.format_exc()]).strip()
            finally:
                task.checked += 1
                task.message = f"正在更新摘要：{task.checked}/{task.target_count}"
                task.save(update_fields=["checked", "updated", "not_found", "failed", "message", "error_detail", "updated_at"])

        for report_date in sorted(changed_dates):
            generate_daily_report(report_date)
        task.status = "success"
        task.message = f"摘要更新完成：补全 {task.updated} 篇，未找到 {task.not_found} 篇，失败 {task.failed} 篇"
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "message", "finished_at", "updated_at"])
    except Exception as exc:
        task.status = "failed"
        task.message = f"摘要更新失败：{exc}"
        task.error_detail = traceback.format_exc()
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "message", "error_detail", "finished_at", "updated_at"])
    finally:
        close_old_connections()


def build_missing_abstract_queryset(*, paper_ids: list[int] | None = None, selected_date: date | None = None):
    # Fill the papers most useful to the researcher first.  A date-wide
    # update used to start with the newest rows only, which left high-scoring
    # papers without abstracts (and therefore without AI reading) waiting
    # behind hundreds of low-value records.
    queryset = Paper.objects.filter(content_pruned_at__isnull=True).filter(Q(abstract="") | Q(abstract__isnull=True)).order_by("-recommend_score", "-created_at")
    if paper_ids:
        return queryset.filter(id__in=paper_ids)
    if selected_date:
        return queryset.filter(created_at__date=selected_date)
    return queryset.none()


def close_stale_abstract_tasks() -> None:
    mark_orphaned_tasks(AbstractUpdateTask, message="后台进程已退出，请重新更新摘要", timeout=STALE_AFTER)
