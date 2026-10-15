from __future__ import annotations

from django.contrib import admin

from .models import (
    AbstractUpdateTask,
    DailyReport,
    FetchLog,
    FetchTask,
    Keyword,
    Paper,
    RescoreTask,
    ResearchDirection,
    RssSource,
    ZoteroCollection,
    ZoteroConfig,
    ZoteroItem,
    ZoteroSyncState,
    SystemSetting,
)


@admin.register(Paper)
class PaperAdmin(admin.ModelAdmin):
    list_display = ("short_title", "journal", "published_date", "doi", "source", "recommend_score", "recommend_level", "is_archived", "is_soft_deleted", "created_at")
    list_filter = ("journal", "source", "recommend_level", "is_archived", "is_soft_deleted", "is_favorite", "zotero_imported", "directions", "keywords", "published_date")
    search_fields = ("title", "authors", "doi", "abstract", "journal")
    ordering = ("-published_date", "-created_at")
    readonly_fields = ("created_at", "updated_at", "dedup_key", "scored_at", "ai_summarized_at")
    filter_horizontal = ("keywords", "directions")
    fieldsets = (
        ("基础信息", {"fields": ("title", "authors", "abstract", "ai_summary", "ai_summary_model", "ai_summarized_at", "doi", "journal", "published_date", "url")}),
        ("来源与分类", {"fields": ("source", "source_name", "source_url", "raw_keywords", "keywords", "directions")}),
        ("推荐评分", {"fields": ("recommend_score", "recommend_level", "matched_fields", "score_detail", "scored_at")}),
        ("状态", {"fields": ("is_favorite", "is_archived", "is_soft_deleted", "zotero_imported", "zotero_imported_at", "zotero_collection_key", "zotero_collection_name", "dedup_key", "created_at", "updated_at")}),
    )

    @admin.display(description="标题")
    def short_title(self, obj: Paper) -> str:
        return obj.title[:80]


@admin.register(RssSource)
class RssSourceAdmin(admin.ModelAdmin):
    list_display = ("name", "fetch_mode", "openalex_issn", "journal", "enabled", "last_fetch_time", "last_fetch_status", "total_fetched_count")
    list_filter = ("enabled",)
    search_fields = ("name", "url", "journal")
    ordering = ("name",)
    readonly_fields = ("last_fetch_time", "last_fetch_status", "last_fetch_message", "total_fetched_count", "created_at", "updated_at")
    fieldsets = (
        ("文献源", {"fields": ("name", "fetch_mode", "url", "openalex_issn", "journal", "enabled", "remark")}),
        ("抓取状态", {"fields": ("last_fetch_time", "last_fetch_status", "last_fetch_message", "total_fetched_count")}),
        ("时间", {"fields": ("created_at", "updated_at")}),
    )


@admin.register(Keyword)
class KeywordAdmin(admin.ModelAdmin):
    list_display = ("keyword", "is_exclusion", "direction", "weight", "enabled")
    list_filter = ("enabled", "direction")
    search_fields = ("keyword", "description")
    ordering = ("keyword",)
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("关键词", {"fields": ("keyword", "aliases", "is_exclusion", "weight", "enabled", "direction", "description")}),
        ("时间", {"fields": ("created_at", "updated_at")}),
    )


@admin.register(ResearchDirection)
class ResearchDirectionAdmin(admin.ModelAdmin):
    list_display = ("name_cn", "name_en", "direction_weight", "priority", "enabled", "created_at")
    list_filter = ("enabled",)
    search_fields = ("name_cn", "name_en")
    ordering = ("name",)
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("研究方向", {"fields": ("name_cn", "name_en", "direction_weight", "priority", "enabled")}),
        ("时间", {"fields": ("created_at", "updated_at")}),
    )


@admin.register(RescoreTask)
class RescoreTaskAdmin(admin.ModelAdmin):
    list_display = ("task_id", "status", "scope", "processed_count", "target_count", "failed_count", "created_at")
    readonly_fields = ("task_id", "status", "scope", "processed_count", "target_count", "failed_count", "message", "error_detail", "started_at", "finished_at", "created_at", "updated_at")


@admin.register(DailyReport)
class DailyReportAdmin(admin.ModelAdmin):
    list_display = ("report_date", "title", "paper_count", "created_at")
    list_filter = ("report_date",)
    search_fields = ("title", "html_content", "markdown_content")
    ordering = ("-report_date",)
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("日报", {"fields": ("report_date", "title", "paper_count")}),
        ("内容", {"fields": ("html_content", "markdown_content")}),
        ("时间", {"fields": ("created_at", "updated_at")}),
    )


@admin.register(FetchLog)
class FetchLogAdmin(admin.ModelAdmin):
    list_display = ("source_name", "status", "fetched_count", "new_count", "duplicate_count", "created_at")
    list_filter = ("status", "source", "created_at")
    search_fields = ("source_name", "message", "error_detail")
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)
    fieldsets = (
        ("日志", {"fields": ("source", "source_name", "status", "message", "error_detail")}),
        ("统计", {"fields": ("fetched_count", "new_count", "duplicate_count")}),
        ("时间", {"fields": ("created_at",)}),
    )


@admin.register(FetchTask)
class FetchTaskAdmin(admin.ModelAdmin):
    list_display = ("task_id", "status", "new_count", "duplicate_count", "paper_count", "created_at", "finished_at")
    list_filter = ("status", "created_at", "finished_at")
    search_fields = ("task_id", "message", "error_detail")
    ordering = ("-created_at",)
    readonly_fields = ("task_id", "created_at", "updated_at", "started_at", "finished_at")
    fieldsets = (
        ("Task", {"fields": ("task_id", "status", "message", "error_detail")}),
        ("Stats", {"fields": ("source_total", "success_sources", "failed_sources", "fetched_count", "new_count", "duplicate_count")}),
        ("Report", {"fields": ("report_date", "report_title", "paper_count")}),
        ("Time", {"fields": ("started_at", "finished_at", "created_at", "updated_at")}),
    )


@admin.register(AbstractUpdateTask)
class AbstractUpdateTaskAdmin(admin.ModelAdmin):
    list_display = ("task_id", "status", "selected_date", "target_count", "checked", "updated", "not_found", "failed", "created_at", "finished_at")
    list_filter = ("status", "selected_date", "created_at", "finished_at")
    search_fields = ("task_id", "message", "error_detail")
    ordering = ("-created_at",)
    readonly_fields = ("task_id", "created_at", "updated_at", "started_at", "finished_at")
    fieldsets = (
        ("Task", {"fields": ("task_id", "status", "message", "error_detail")}),
        ("Scope", {"fields": ("selected_date", "paper_ids")}),
        ("Stats", {"fields": ("target_count", "checked", "updated", "not_found", "failed")}),
        ("Time", {"fields": ("started_at", "finished_at", "created_at", "updated_at")}),
    )


@admin.register(ZoteroConfig)
class ZoteroConfigAdmin(admin.ModelAdmin):
    list_display = ("name", "library_type", "user_id", "group_id", "enabled", "updated_at")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("连接配置", {"fields": ("name", "library_type", "user_id", "group_id", "api_key", "enabled")}),
        ("时间", {"fields": ("created_at", "updated_at")}),
    )


@admin.register(ZoteroSyncState)
class ZoteroSyncStateAdmin(admin.ModelAdmin):
    list_display = ("name", "sync_status", "sync_mode", "library_version", "item_count", "collection_count", "last_synced_at")
    readonly_fields = (
        "created_at",
        "updated_at",
        "last_synced_at",
        "sync_started_at",
        "sync_finished_at",
        "sync_error",
    )


@admin.register(ZoteroCollection)
class ZoteroCollectionAdmin(admin.ModelAdmin):
    list_display = ("name", "key", "parent_key", "item_count", "zotero_version", "updated_at")
    search_fields = ("name", "key", "parent_key")
    readonly_fields = ("created_at", "updated_at", "raw")


@admin.register(ZoteroItem)
class ZoteroItemAdmin(admin.ModelAdmin):
    list_display = ("short_title", "creator", "date", "journal", "doi", "item_type", "zotero_version")
    list_filter = ("item_type", "journal")
    search_fields = ("title", "creator", "doi", "journal", "abstract")
    readonly_fields = ("created_at", "updated_at", "raw")

    @admin.display(description="Title")
    def short_title(self, obj: ZoteroItem) -> str:
        return obj.title[:80]


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = ("key", "updated_at")
    search_fields = ("key", "description")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("配置", {"fields": ("key", "value", "description")}),
        ("时间", {"fields": ("created_at", "updated_at")}),
    )
