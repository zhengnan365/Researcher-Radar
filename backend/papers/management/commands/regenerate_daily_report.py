from __future__ import annotations

from datetime import date

from django.core.management.base import BaseCommand

from papers.services.report_generator import generate_daily_report


class Command(BaseCommand):
    help = "Regenerate a daily report. Usage: python manage.py regenerate_daily_report report_date=2026-07-05"

    def add_arguments(self, parser):
        parser.add_argument("report_date", nargs="?", default="")

    def handle(self, *args, **options):
        raw = options.get("report_date") or ""
        if raw.startswith("report_date="):
            raw = raw.split("=", 1)[1]
        report_date = date.fromisoformat(raw) if raw else date.today()
        report = generate_daily_report(report_date)
        self.stdout.write(self.style.SUCCESS(f"日报已生成: {report.title}, {report.paper_count} 篇"))
