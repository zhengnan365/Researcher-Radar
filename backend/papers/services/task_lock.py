"""Small database-backed lock for starting in-process background jobs.

The application may run more than one Gunicorn worker.  A Python Lock only
protects one worker, so two workers could otherwise both observe no active
task and start duplicate fetch/rescore jobs.  Touching the singleton row
inside an atomic transaction makes SQLite acquire its write lock while the
active-task check and task creation happen.
"""

from contextlib import contextmanager
import sys
import time

from django.db import OperationalError, transaction
from django.utils import timezone

from papers.models import SystemSetting


@contextmanager
def task_start_lock():
    atomic = None
    for attempt in range(8):
        atomic = transaction.atomic()
        atomic.__enter__()
        try:
            # An UPDATE first avoids a stale SQLite read snapshot.
            updated = SystemSetting.objects.filter(key="__background_task_start_lock__").update(updated_at=timezone.now())
            if not updated:
                SystemSetting.objects.get_or_create(
                    key="__background_task_start_lock__",
                    defaults={"value": {}, "description": "后台任务启动锁"},
                )
        except OperationalError as exc:
            atomic.__exit__(*sys.exc_info())
            if "locked" not in str(exc).lower() or attempt == 7:
                raise
            time.sleep(0.05 * (attempt + 1))
        except BaseException:
            atomic.__exit__(*sys.exc_info())
            raise
        else:
            break
    try:
        yield
    except BaseException:
        atomic.__exit__(*sys.exc_info())
        raise
    else:
        atomic.__exit__(None, None, None)
