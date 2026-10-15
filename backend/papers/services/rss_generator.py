from __future__ import annotations

from datetime import datetime, time, timezone
from email.utils import format_datetime
from xml.dom import minidom
from xml.etree.ElementTree import Element, SubElement, tostring

from django.utils.html import escape

from papers.models import Paper


def generate_favorites_rss(site_url: str = "") -> str:
    rss = Element("rss", {"version": "2.0"})
    channel = SubElement(rss, "channel")
    add_text(channel, "title", "Literature Favorites RSS")
    add_text(channel, "link", site_url)
    add_text(channel, "description", "已收藏文献 RSS，可用于 Zotero 订阅")
    add_text(channel, "language", "zh-CN")
    add_text(channel, "lastBuildDate", format_datetime(datetime.now(timezone.utc)))

    for paper in Paper.objects.filter(is_favorite=True, zotero_imported=False).exclude(relevance_override="irrelevant").order_by("-updated_at"):
        item = SubElement(channel, "item")
        add_text(item, "title", paper.title)
        add_text(item, "link", paper.url)
        add_text(item, "guid", paper.doi or paper.url or str(paper.pk))
        add_text(item, "pubDate", paper_pub_date(paper))
        add_text(item, "description", item_description(paper))

    return minidom.parseString(tostring(rss, encoding="utf-8")).toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")


def add_text(parent: Element, tag: str, value) -> None:
    child = SubElement(parent, tag)
    child.text = str(value or "")


def paper_pub_date(paper: Paper) -> str:
    if paper.published_date:
        dt = datetime.combine(paper.published_date, time.min, tzinfo=timezone.utc)
    else:
        dt = paper.created_at.astimezone(timezone.utc)
    return format_datetime(dt)


def item_description(paper: Paper) -> str:
    return "\n".join(
        [
            f"<p><strong>作者：</strong>{escape(paper.authors or '未获取')}</p>",
            f"<p><strong>期刊：</strong>{escape(paper.journal or '未获取')}</p>",
            f"<p><strong>发布日期：</strong>{escape(str(paper.published_date or '未获取'))}</p>",
            f"<p><strong>DOI：</strong>{escape(paper.doi or '未获取')}</p>",
            f"<p><strong>摘要：</strong>{escape(paper.abstract or '未获取')}</p>",
        ]
    )
