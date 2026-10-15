"""Identify jobs orphaned by a worker restart without touching live workers."""

import psutil
from django.utils import timezone


def mark_orphaned_tasks(model, *, message: str, timeout):
    active = model.objects.filter(status__in=("pending", "running"))
    now = timezone.now()
    for task in active.only("pk", "worker_pid", "updated_at"):
        if task.worker_pid and not psutil.pid_exists(task.worker_pid):
            model.objects.filter(pk=task.pk, status__in=("pending", "running")).update(
                status="failed", message=message, finished_at=now, updated_at=now,
            )
    active.filter(updated_at__lt=now - timeout).update(
        status="failed", message="后台任务长时间无进展，请重新启动", finished_at=now, updated_at=now,
    )
