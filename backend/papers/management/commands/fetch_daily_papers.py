from __future__ import annotations

from django.core.management.base import BaseCommand

from papers.services.report_generator import generate_daily_report
from papers.services.rss_fetcher import fetch_all_enabled_sources


class Command(BaseCommand):
    help = "Fetch enabled RSS sources, enrich papers, classify them, and generate today's report."

    def handle(self, *args, **options):
        summary = fetch_all_enabled_sources()
        report = generate_daily_report()
        self.stdout.write(self.style.SUCCESS("Literature fetch completed"))
        self.stdout.write(f"RSS sources: {summary.source_total}")
        self.stdout.write(f"Success sources: {summary.success_sources}")
        self.stdout.write(f"Failed sources: {summary.failed_sources}")
        self.stdout.write(f"Fetched RSS entries: {summary.fetched_count}")
        self.stdout.write(f"New papers: {summary.new_count}")
        self.stdout.write(f"Duplicate papers: {summary.duplicate_count}")
        self.stdout.write(f"Skipped unmatched papers: {summary.skipped_unmatched_count}")
        self.stdout.write(f"Report generated: {report.title}, {report.paper_count} papers")
