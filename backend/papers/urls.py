from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    DailyReportViewSet,
    FetchLogViewSet,
    KeywordViewSet,
    PaperViewSet,
    ResearchDirectionViewSet,
    RssSourceViewSet,
    UserViewSet,
    abstract_update_active,
    abstract_update_status,
    auth_login,
    auth_logout,
    auth_me,
    fetch_daily_active,
    fetch_daily_now,
    fetch_daily_status,
    scoring_settings,
    scoring_rescore_active,
    scoring_rescore_start,
    scoring_rescore_status,
    ai_settings,
    scoring_distribution,
    scoring_settings_reset,
    system_config_export,
    system_config_import,
    zotero_create_collection,
    zotero_import_paper,
    zotero_item_detail,
    zotero_config,
    zotero_library,
    zotero_library_items,
    zotero_suggest_collection,
    zotero_sync,
    zotero_sync_status,
)


router = DefaultRouter()
router.register("papers", PaperViewSet, basename="paper")
router.register("sources", RssSourceViewSet, basename="source")
router.register("keywords", KeywordViewSet, basename="keyword")
router.register("directions", ResearchDirectionViewSet, basename="direction")
router.register("reports", DailyReportViewSet, basename="report")
router.register("fetch_logs", FetchLogViewSet, basename="fetch-log")
router.register("users", UserViewSet, basename="user")

urlpatterns = [
    path("auth/login/", auth_login, name="auth-login"),
    path("auth/logout/", auth_logout, name="auth-logout"),
    path("auth/me/", auth_me, name="auth-me"),
    path("", include(router.urls)),
    path("zotero/sync/", zotero_sync, name="zotero-sync"),
    path("zotero/library/", zotero_library, name="zotero-library"),
    path("zotero/library/items/", zotero_library_items, name="zotero-library-items"),
    path("zotero/items/<str:item_key>/", zotero_item_detail, name="zotero-item-detail"),
    path("zotero/sync-status/", zotero_sync_status, name="zotero-sync-status"),
    path("zotero/config/", zotero_config, name="zotero-config"),
    path("zotero/create-collection/", zotero_create_collection, name="zotero-create-collection"),
    path("zotero/import-paper/", zotero_import_paper, name="zotero-import-paper"),
    path("zotero/suggest-collection/", zotero_suggest_collection, name="zotero-suggest-collection"),
    path("tasks/fetch-daily/", fetch_daily_now, name="fetch-daily-now"),
    path("tasks/fetch-daily/active/", fetch_daily_active, name="fetch-daily-active"),
    path("tasks/fetch-daily/<uuid:task_id>/", fetch_daily_status, name="fetch-daily-status"),
    path("tasks/abstract-update/active/", abstract_update_active, name="abstract-update-active"),
    path("tasks/abstract-update/<uuid:task_id>/", abstract_update_status, name="abstract-update-status"),
    path("settings/scoring/", scoring_settings, name="scoring-settings"),
    path("settings/scoring/rescore/", scoring_rescore_start, name="scoring-rescore-start"),
    path("settings/scoring/rescore/active/", scoring_rescore_active, name="scoring-rescore-active"),
    path("settings/scoring/rescore/<uuid:task_id>/", scoring_rescore_status, name="scoring-rescore-status"),
    path("settings/ai/", ai_settings, name="ai-settings"),
    path("settings/scoring/distribution/", scoring_distribution, name="scoring-distribution"),
    path("settings/scoring/reset/", scoring_settings_reset, name="scoring-settings-reset"),
    path("settings/config/export/", system_config_export, name="system-config-export"),
    path("settings/config/import/", system_config_import, name="system-config-import"),
]
