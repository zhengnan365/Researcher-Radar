from __future__ import annotations

from datetime import date

from django.conf import settings
from django.utils.html import escape

from papers.models import DailyReport, Paper
from papers.services.runtime_settings import get_runtime_rules


def generate_daily_report(report_date: date | None = None) -> DailyReport:
    report_date = report_date or date.today()
    rules = get_runtime_rules()
    papers = (
        Paper.objects.filter(created_at__date=report_date)
        .filter(is_archived=False, is_soft_deleted=False, recommend_score__gte=int(rules["report_min_score"]))
        .exclude(relevance_override="irrelevant")
        .prefetch_related("directions", "keywords")
        .select_related("source")
    )
    if not rules["show_weak_related"]:
        papers = papers.exclude(recommend_level__in=["weak", "low"])
    papers = apply_report_order(papers, rules["report_sort"], bool(rules["sort_by_score_desc"]))
    max_papers = int(rules["daily_max_papers"])
    if max_papers:
        papers = papers[:max_papers]
    markdown = build_markdown(report_date, list(papers))
    html = markdown_to_simple_html(markdown)
    report, _ = DailyReport.objects.update_or_create(
        report_date=report_date,
        defaults={
            "title": f"科研雷达 · 文献日报 - {report_date.isoformat()}",
            "html_content": html,
            "markdown_content": markdown,
            "paper_count": papers.count(),
        },
    )
    return report


def apply_report_order(queryset, report_sort: str, score_desc: bool):
    from django.db.models import Max

    queryset = queryset.annotate(direction_priority=Max("directions__priority"))
    score_field = "-recommend_score" if score_desc else "recommend_score"
    if report_sort == "date":
        return queryset.order_by("-published_date", "-created_at")
    if report_sort == "journal":
        return queryset.order_by("journal", score_field, "title")
    if report_sort == "direction":
        return queryset.order_by("-direction_priority", score_field, "-published_date", "-id")
    if report_sort == "keyword_count":
        from django.db.models import Count

        return queryset.annotate(keyword_count=Count("keywords")).order_by("-keyword_count", score_field)
    if report_sort == "score_date":
        return queryset.order_by(score_field, "-direction_priority", "-published_date", "-created_at", "-id")
    return queryset.order_by(score_field, "-direction_priority", "-published_date", "journal", "title", "-id")


def build_markdown(report_date: date, papers: list[Paper]) -> str:
    lines = [f"# 科研雷达 · 文献日报 - {report_date.isoformat()}", "", f"新增文献数量：{len(papers)}", ""]
    if not papers:
        lines.append("今日暂无新文献。")
        return "\n".join(lines)
    by_direction: dict[str, list[Paper]] = {}
    for paper in papers:
        names = [d.name for d in paper.directions.all()] or ["未分类"]
        for name in names:
            by_direction.setdefault(name, []).append(paper)
    item_number = 1
    for direction, items in by_direction.items():
        lines.extend([f"## {direction}", ""])
        for paper in items:
            meta_lines = []
            if paper.authors:
                meta_lines.append(f"- 作者：{paper.authors}")
            if paper.journal:
                meta_lines.append(f"- 期刊：{paper.journal}")
            if paper.published_date:
                meta_lines.append(f"- 发布日期：{paper.published_date}")
            if paper.doi:
                meta_lines.append(f"- DOI：{paper.doi}")
            if paper.url:
                meta_lines.append(f"- 原文链接：{paper.url}")
            meta_lines.append(f"- 推荐分数：{paper.recommend_score}（{paper.get_recommend_level_display()}）")
            if paper.keywords.exists():
                meta_lines.append(f"- 命中关键词：{'、'.join(k.keyword for k in paper.keywords.all())}")
            lines.extend(
                [
                    f"### {item_number}. {paper.title}",
                    *meta_lines,
                    "",
                    f"摘要：{paper.abstract or '暂无摘要'}",
                    "",
                ]
            )
            item_number += 1
    return "\n".join(lines)


def markdown_to_simple_html(markdown: str) -> str:
    body = []
    for line in markdown.splitlines():
        if line.startswith("# "):
            body.append(f"<h1>{escape(line[2:])}</h1>")
        elif line.startswith("## "):
            body.append(f"<h2>{escape(line[3:])}</h2>")
        elif line.startswith("### "):
            body.append(f"<h3>{escape(line[4:])}</h3>")
        elif line.startswith("- "):
            body.append(f"<p>{escape(line)}</p>")
        elif line:
            body.append(f"<p>{escape(line)}</p>")
    return "<!doctype html><html><head><meta charset='utf-8'><title>科研雷达 · 文献日报</title></head><body>" + "\n".join(body) + "</body></html>"
