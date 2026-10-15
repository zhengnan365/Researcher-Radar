from __future__ import annotations

import logging
import json
import hashlib
import time
import requests
from collections import defaultdict
from datetime import date, timedelta

from django.contrib.auth import authenticate, get_user_model
from django.db import DatabaseError, OperationalError, models, transaction
from django.db.models import F
from django.http import HttpResponse
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.authtoken.models import Token
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response

from .filters import filter_fetch_logs, filter_papers
from .models import AbstractUpdateTask, DailyReport, FetchLog, FetchTask, Keyword, LoginAttempt, Paper, ResearchDirection, RescoreTask, RssSource, ZoteroConfig, ZoteroItem
from .serializers import (
    DailyReportSerializer,
    FetchLogSerializer,
    KeywordSerializer,
    PaperSerializer,
    ResearchDirectionSerializer,
    RssSourceSerializer,
    UserSerializer,
)
from .services.report_generator import generate_daily_report
from .services.fetch_task_runner import get_active_fetch_task, start_fetch_task
from .services.rss_fetcher import test_feed_url
from .services.abstract_task_runner import get_active_abstract_task, start_abstract_update_task
from .services.config_transfer import ConfigImportError, export_system_config, import_system_config
from .services.relevance_scorer import score_paper
from .services.rescore import rescore_papers_queryset
from .services.rescore_task_runner import get_active_rescore_task, rescore_task_payload, start_rescore_task
from .services.runtime_settings import default_rules, get_runtime_rules, reset_runtime_rules, save_runtime_rules
from .services.zotero_api import (
    create_zotero_collection,
    get_zotero_sync_status,
    import_paper_to_zotero,
    read_zotero_library,
    read_zotero_library_page,
    suggest_collection_for_paper,
    zotero_item_to_dict,
)
from .services.zotero_sync import sync_zotero_library
from .services.ai_summary import AiSummaryError, summarize_paper
from .services.ai_config import AiConfigError, get_ai_config, save_ai_config

User = get_user_model()
logger = logging.getLogger(__name__)


def user_payload(user) -> dict:
    return {"id": user.id, "username": user.get_username()}


@api_view(["POST"])
@permission_classes([AllowAny])
def auth_login(request):
    username = str(request.data.get("username") or "").strip()
    password = str(request.data.get("password") or "")
    identity = f"{request.META.get('REMOTE_ADDR', 'unknown')}:{username.casefold()}"
    attempt_key = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    now = timezone.now()
    if LoginAttempt.objects.filter(identity_hash=attempt_key, expires_at__gt=now, failures__gte=8).exists():
        return Response({"success": False, "message": "登录失败次数过多，请 15 分钟后再试。"}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    user = authenticate(request, username=username, password=password)
    if not user:
        try:
            attempt, _ = LoginAttempt.objects.get_or_create(
                identity_hash=attempt_key,
                defaults={"expires_at": now + timedelta(minutes=15)},
            )
            active = LoginAttempt.objects.filter(pk=attempt.pk, expires_at__gt=now)
            if active.update(failures=F("failures") + 1, updated_at=now) == 0:
                LoginAttempt.objects.filter(pk=attempt.pk).update(
                    failures=1, expires_at=now + timedelta(minutes=15), updated_at=now,
                )
        except DatabaseError:
            logger.exception("Login rate limit database operation failed")
            return Response({"success": False, "message": "登录服务暂时不可用，请稍后再试。"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({"success": False, "message": "用户名或密码错误"}, status=status.HTTP_400_BAD_REQUEST)
    if not user.is_active:
        return Response({"success": False, "message": "用户已被禁用"}, status=status.HTTP_403_FORBIDDEN)
    LoginAttempt.objects.filter(identity_hash=attempt_key).delete()
    LoginAttempt.objects.filter(expires_at__lt=now - timedelta(days=1)).delete()
    token = None
    for attempt in range(3):
        try:
            token, _ = Token.objects.get_or_create(user=user)
            break
        except OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt == 2:
                logger.exception("Login token database operation failed for user_id=%s", user.pk)
                return Response(
                    {"success": False, "message": "登录服务暂时不可用，请检查数据库迁移、权限或锁定状态。"},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            time.sleep(0.2 * (attempt + 1))
        except DatabaseError:
            logger.exception("Login token database operation failed for user_id=%s", user.pk)
            return Response(
                {"success": False, "message": "登录服务暂时不可用，请检查数据库迁移和写入权限。"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
    return Response({"success": True, "token": token.key, "user": user_payload(user)})


@api_view(["POST"])
@permission_classes([AllowAny])
def auth_logout(request):
    if request.auth:
        request.auth.delete()
    return Response({"success": True})


@api_view(["GET"])
@permission_classes([AllowAny])
def auth_me(request):
    if request.user and request.user.is_authenticated:
        return Response({"authenticated": True, "user": user_payload(request.user)})
    return Response({"authenticated": False})


class PaperViewSet(viewsets.ModelViewSet):
    serializer_class = PaperSerializer

    def get_queryset(self):
        queryset = Paper.objects.select_related("source").prefetch_related("keywords", "directions").filter(content_pruned_at__isnull=True)
        params = self.request.query_params
        if self.action == "list":
            queryset = queryset.exclude(relevance_override="irrelevant")
        if "archived" not in params:
            queryset = queryset.filter(is_archived=False)
        if "soft_deleted" not in params:
            queryset = queryset.filter(is_soft_deleted=False)
        return filter_papers(
            queryset,
            params,
        )

    @action(detail=True, methods=["post"], url_path="ai-summary")
    def ai_summary(self, request, pk=None):
        paper = self.get_object()
        try:
            summarize_paper(paper, force=bool(request.data.get("force", False)))
        except AiSummaryError as exc:
            code = status.HTTP_503_SERVICE_UNAVAILABLE if "设置" in str(exc) else status.HTTP_400_BAD_REQUEST
            return Response({"detail": str(exc)}, status=code)
        except requests.RequestException:
            logger.exception("AI summary provider failed for paper_id=%s", paper.pk)
            return Response({"detail": "AI 服务请求失败，请检查服务配置及日志。"}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(PaperSerializer(paper).data)

    @action(detail=True, methods=["post"], url_path="mark-irrelevant")
    def mark_irrelevant(self, request, pk=None):
        paper = self.get_object()
        if paper.relevance_override != "irrelevant":
            paper.system_recommend_score = paper.system_recommend_score if paper.system_recommend_score is not None else paper.recommend_score
            paper.relevance_override = "irrelevant"
            paper.recommend_score = 0
            paper.recommend_level = "low"
            paper.save(update_fields=["system_recommend_score", "relevance_override", "recommend_score", "recommend_level", "updated_at"])
        return Response(PaperSerializer(paper).data)

    @action(detail=True, methods=["post"])
    def favorite(self, request, pk=None):
        paper = self.get_object()
        paper.is_favorite = True
        paper.save(update_fields=["is_favorite", "updated_at"])
        return Response(PaperSerializer(paper).data)

    @favorite.mapping.delete
    def unfavorite(self, request, pk=None):
        paper = self.get_object()
        paper.is_favorite = False
        paper.save(update_fields=["is_favorite", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="zotero-imported")
    def zotero_imported(self, request, pk=None):
        paper = self.get_object()
        paper.zotero_imported = True
        paper.zotero_imported_at = timezone.now()
        paper.save(update_fields=["zotero_imported", "zotero_imported_at", "updated_at"])
        return Response(PaperSerializer(paper).data)

    @zotero_imported.mapping.delete
    def zotero_unimported(self, request, pk=None):
        paper = self.get_object()
        paper.zotero_imported = False
        paper.zotero_imported_at = None
        paper.save(update_fields=["zotero_imported", "zotero_imported_at", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["get"])
    def date_counts(self, request):
        params = request.query_params.copy()
        params.pop("date", None)
        year = params.pop("year", [None])[0]
        month = params.pop("month", [None])[0]

        queryset = filter_papers(Paper.objects.filter(is_archived=False, is_soft_deleted=False).exclude(relevance_override="irrelevant"), params)
        if year:
            queryset = queryset.filter(created_at__year=year)
        if month:
            queryset = queryset.filter(created_at__month=month)

        rows = (
            queryset.annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(count=Count("id"))
            .order_by("day")
        )
        return Response([{"date": row["day"].isoformat(), "count": row["count"]} for row in rows if row["day"]])

    @action(detail=False, methods=["get"], url_path="dashboard-stats")
    def dashboard_stats(self, request):
        """Return homepage statistics with database aggregation instead of paged rows."""
        selected_date = str(request.query_params.get("date") or "").strip()
        queryset = Paper.objects.filter(is_archived=False, is_soft_deleted=False).exclude(relevance_override="irrelevant")
        if selected_date:
            queryset = queryset.filter(created_at__date=selected_date)

        total = queryset.count()
        doi_count = queryset.exclude(doi__isnull=True).exclude(doi="").count()
        abstract_count = queryset.exclude(abstract__isnull=True).exclude(abstract="").count()
        imported_count = queryset.filter(zotero_imported=True).count()

        source_counter: dict[str, int] = defaultdict(int)
        for row in queryset.values("journal", "source_name").annotate(count=Count("id")):
            name = clean_dashboard_label(row.get("journal")) or clean_dashboard_label(row.get("source_name")) or "Other"
            source_counter[name] += row["count"]

        direction_counter: dict[str, int] = defaultdict(int)
        for row in queryset.values("directions__name").annotate(count=Count("id")):
            name = clean_dashboard_label(row.get("directions__name")) or "未分类"
            direction_counter[name] += row["count"]

        keyword_counter: dict[str, int] = defaultdict(int)
        for row in queryset.values("keywords__keyword").annotate(count=Count("id")):
            name = clean_dashboard_label(row.get("keywords__keyword"))
            if name:
                keyword_counter[name] += row["count"]

        return Response(
            {
                "date": selected_date,
                "total": total,
                "doi_count": doi_count,
                "abstract_count": abstract_count,
                "zotero_imported_count": imported_count,
                "source_rows": ranked_dashboard_rows(source_counter, limit=8),
                "direction_rows": ranked_dashboard_rows(direction_counter, limit=8),
                "keyword_rows": ranked_dashboard_rows(keyword_counter, limit=8),
            }
        )

    @action(detail=False, methods=["get"], url_path="low-score")
    def low_score(self, request):
        rules = get_runtime_rules()
        params = request.query_params.copy()
        queryset = Paper.objects.select_related("source").prefetch_related("keywords", "directions").filter(content_pruned_at__isnull=True).exclude(relevance_override="irrelevant")
        history_scope = str(params.pop("history_scope", ["recent"])[0]).strip().lower()
        if history_scope not in {"recent", "all"}:
            return Response({"detail": "历史范围无效。"}, status=status.HTTP_400_BAD_REQUEST)
        if history_scope == "recent":
            queryset = queryset.filter(created_at__gte=timezone.now() - timedelta(days=90))
        score_lt = params.pop("max_score", [None])[0]
        if score_lt not in {None, ""}:
            queryset = queryset.filter(recommend_score__lt=int(score_lt))
        else:
            queryset = queryset.filter(recommend_score__lt=int(rules["low_score_threshold"]))
        if "archived" not in params:
            queryset = queryset.filter(is_archived=False)
        if "soft_deleted" not in params:
            queryset = queryset.filter(is_soft_deleted=False)
        queryset = filter_papers(queryset, params)
        queryset = apply_low_score_filters(queryset, params)
        page = self.paginate_queryset(queryset.order_by("recommend_score", "-created_at"))
        if page is not None:
            return self.get_paginated_response(PaperSerializer(page, many=True).data)
        return Response(PaperSerializer(queryset, many=True).data)

    @action(detail=False, methods=["post"], url_path="bulk-soft-delete")
    def bulk_soft_delete(self, request):
        ids = parse_id_list(request.data.get("ids") or [])
        count = Paper.objects.filter(id__in=ids).update(is_soft_deleted=True, updated_at=timezone.now())
        return Response({"updated": count})

    @action(detail=False, methods=["post"], url_path="bulk-restore")
    def bulk_restore(self, request):
        ids = parse_id_list(request.data.get("ids") or [])
        count = Paper.objects.filter(id__in=ids).update(is_archived=False, is_soft_deleted=False, updated_at=timezone.now())
        return Response({"updated": count})

    @action(detail=False, methods=["post"], url_path="bulk-rescore")
    def bulk_rescore(self, request):
        ids = parse_id_list(request.data.get("ids") or [])
        count = rescore_papers_queryset(paper_ids=ids)
        return Response({"rescored": count})

    @action(detail=True, methods=["post"], url_path="soft-delete")
    def soft_delete(self, request, pk=None):
        paper = Paper.objects.get(pk=pk)
        paper.is_soft_deleted = True
        paper.save(update_fields=["is_soft_deleted", "updated_at"])
        return Response(PaperSerializer(paper).data)

    @action(detail=True, methods=["post"], url_path="restore")
    def restore(self, request, pk=None):
        paper = Paper.objects.get(pk=pk)
        paper.is_archived = False
        paper.is_soft_deleted = False
        paper.save(update_fields=["is_archived", "is_soft_deleted", "updated_at"])
        return Response(PaperSerializer(paper).data)

    @action(detail=True, methods=["post"], url_path="rescore")
    def rescore(self, request, pk=None):
        paper = score_paper(Paper.objects.get(pk=pk))
        return Response(PaperSerializer(paper).data)

    @action(detail=False, methods=["post"], url_path="update-abstracts")
    def update_abstracts(self, request):
        raw_ids = request.data.get("paper_ids") or []
        paper_ids = [int(item) for item in raw_ids if str(item).isdigit()]
        selected_date = str(request.data.get("date") or "").strip()
        try:
            task, created = start_abstract_update_task(paper_ids=paper_ids, selected_date=selected_date)
        except ValueError:
            return Response({"detail": "未勾选文献时，请先选择一个日期再更新摘要。"}, status=status.HTTP_400_BAD_REQUEST)
        payload = abstract_task_payload(task)
        payload["created"] = created
        return Response(payload, status=status.HTTP_202_ACCEPTED)


class RssSourceViewSet(viewsets.ModelViewSet):
    serializer_class = RssSourceSerializer

    def get_queryset(self):
        queryset = RssSource.objects.all()
        params = self.request.query_params
        search = str(params.get("search") or "").strip()
        enabled = str(params.get("enabled") or "").strip().lower()
        if search:
            queryset = queryset.filter(
                models.Q(name__icontains=search)
                | models.Q(url__icontains=search)
                | models.Q(journal__icontains=search)
            )
        if enabled in {"true", "1", "yes"}:
            queryset = queryset.filter(enabled=True)
        elif enabled in {"false", "0", "no"}:
            queryset = queryset.filter(enabled=False)
        return queryset

    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        source = self.get_object()
        if source.fetch_mode == "openalex":
            from .services.openalex_fetcher import test_openalex_issn
            return Response(test_openalex_issn(source.openalex_issn))
        if source.fetch_mode == "both":
            from .services.openalex_fetcher import test_openalex_issn
            rss_result = test_feed_url(source.url)
            openalex_result = test_openalex_issn(source.openalex_issn)
            return Response({"ok": rss_result["ok"] and openalex_result["ok"], "title": source.name, "entry_count": rss_result["entry_count"], "message": f"RSS: {rss_result['message']}；OpenAlex: {openalex_result['message']}"})
        return Response(test_feed_url(source.url))

    @action(detail=False, methods=["post"], url_path="bulk-create")
    def bulk_create(self, request):
        raw_sources = request.data.get("sources") or ""
        enabled = str(request.data.get("enabled", True)).lower() not in {"false", "0", "no"}
        rows = parse_bulk_lines(raw_sources)
        if not rows:
            return Response({"detail": "请至少填写一个 RSS 源。"}, status=status.HTTP_400_BAD_REQUEST)

        created = []
        updated = []
        skipped = []
        for row in rows:
            parts = split_bulk_fields(row)
            url = next((item for item in parts if item.lower().startswith(("http://", "https://"))), "")
            if not url:
                skipped.append(row)
                continue
            name = parts[0] if parts[0] != url else ""
            journal = parts[2] if len(parts) >= 3 else ""
            defaults = {
                "name": name or journal or url,
                "journal": journal,
                "enabled": enabled,
            }
            source, was_created = RssSource.objects.get_or_create(url=url, defaults=defaults)
            if was_created:
                created.append(source.name)
            else:
                for key, value in defaults.items():
                    if value not in {"", None}:
                        setattr(source, key, value)
                source.save()
                updated.append(source.name)
        return Response({"created": created, "updated": updated, "skipped": skipped})

    @action(detail=False, methods=["post"], url_path="bulk-delete")
    def bulk_delete(self, request):
        ids = parse_id_list(request.data.get("ids") or [])
        deleted, _ = RssSource.objects.filter(id__in=ids).delete()
        return Response({"deleted": deleted})


class KeywordViewSet(viewsets.ModelViewSet):
    serializer_class = KeywordSerializer

    def get_queryset(self):
        queryset = Keyword.objects.select_related("direction").all()
        params = self.request.query_params
        direction = str(params.get("direction") or "").strip()
        search = str(params.get("search") or "").strip()
        enabled = str(params.get("enabled") or "").strip().lower()
        if direction:
            if direction.isdigit():
                queryset = queryset.filter(direction_id=int(direction))
            else:
                queryset = queryset.filter(direction__name__icontains=direction)
        if search:
            queryset = queryset.filter(keyword__icontains=search)
        if enabled in {"true", "1", "yes"}:
            queryset = queryset.filter(enabled=True)
        elif enabled in {"false", "0", "no"}:
            queryset = queryset.filter(enabled=False)
        return queryset

    @action(detail=False, methods=["post"], url_path="bulk-create")
    @transaction.atomic
    def bulk_create(self, request):
        raw_keywords = request.data.get("keywords") or []
        if isinstance(raw_keywords, str):
            raw_keywords = raw_keywords.replace("；", ";").replace("，", ",")
            for sep in [";", ","]:
                raw_keywords = raw_keywords.replace(sep, "\n")
            keyword_values = [item.strip() for item in raw_keywords.splitlines() if item.strip()]
        else:
            keyword_values = [str(item).strip() for item in raw_keywords if str(item).strip()]
        if not keyword_values:
            return Response({"detail": "请至少填写一个关键词。"}, status=status.HTTP_400_BAD_REQUEST)

        direction_id = request.data.get("direction") or None
        try:
            weight = int(request.data.get("weight", 1))
        except (TypeError, ValueError):
            return Response({"detail": "关键词权重必须为 1-5 的整数。"}, status=status.HTTP_400_BAD_REQUEST)
        if not 1 <= weight <= 5:
            return Response({"detail": "关键词权重必须为 1-5 的整数。"}, status=status.HTTP_400_BAD_REQUEST)
        if not direction_id:
            return Response({"detail": "请先选择研究方向。"}, status=status.HTTP_400_BAD_REQUEST)
        if not str(direction_id).isdigit() or not ResearchDirection.objects.filter(pk=int(direction_id)).exists():
            return Response({"detail": "研究方向不存在。"}, status=status.HTTP_400_BAD_REQUEST)
        parsed = []
        seen = set()
        for line_number, row in enumerate(keyword_values, start=1):
            columns = [item.strip() for item in row.split("|" if "|" in row else "\t")]
            if len(columns) not in {1, 2} or not columns[0]:
                return Response({"detail": f"第 {line_number} 项格式应为：关键词 | 权重。"}, status=status.HTTP_400_BAD_REQUEST)
            value = columns[0]
            raw_weight = columns[-1] if len(columns) > 1 else weight
            try:
                row_weight = int(raw_weight)
            except (TypeError, ValueError):
                return Response({"detail": f"第 {line_number} 项权重必须为 1-5 的整数。"}, status=status.HTTP_400_BAD_REQUEST)
            if not 1 <= row_weight <= 5:
                return Response({"detail": f"第 {line_number} 项权重必须为 1-5 的整数。"}, status=status.HTTP_400_BAD_REQUEST)
            if len(value) > 120:
                return Response({"detail": f"第 {line_number} 项关键词不能超过 120 个字符。"}, status=status.HTTP_400_BAD_REQUEST)
            if value.lower() not in seen:
                seen.add(value.lower())
                parsed.append((value, row_weight))
        enabled = str(request.data.get("enabled", True)).lower() not in {"false", "0", "no"}
        update_existing = str(request.data.get("update_existing", True)).lower() not in {"false", "0", "no"}

        created = []
        updated = []
        skipped = []
        for value, row_weight in parsed:
            defaults = {
                "weight": row_weight,
                "enabled": enabled,
                "direction_id": direction_id,
            }
            keyword = Keyword.objects.filter(keyword__iexact=value).first()
            was_created = keyword is None
            if was_created:
                keyword = Keyword.objects.create(keyword=value, **defaults)
            if was_created:
                created.append(keyword.keyword)
                continue
            if update_existing:
                keyword.weight = row_weight
                keyword.enabled = enabled
                keyword.direction_id = direction_id
                keyword.save(update_fields=["weight", "enabled", "direction", "updated_at"])
                updated.append(keyword.keyword)
            else:
                skipped.append(keyword.keyword)

        return Response({"created": created, "updated": updated, "skipped": skipped})

    @action(detail=False, methods=["post"], url_path="bulk-delete")
    def bulk_delete(self, request):
        ids = parse_id_list(request.data.get("ids") or [])
        deleted, _ = Keyword.objects.filter(id__in=ids).delete()
        return Response({"deleted": deleted})


class ResearchDirectionViewSet(viewsets.ModelViewSet):
    serializer_class = ResearchDirectionSerializer

    def get_queryset(self):
        queryset = ResearchDirection.objects.all()
        params = self.request.query_params
        search = str(params.get("search") or "").strip()
        enabled = str(params.get("enabled") or "").strip().lower()
        if search:
            queryset = queryset.filter(models.Q(name__icontains=search) | models.Q(name_en__icontains=search))
        if enabled in {"true", "1", "yes"}:
            queryset = queryset.filter(enabled=True)
        elif enabled in {"false", "0", "no"}:
            queryset = queryset.filter(enabled=False)
        return queryset

    @action(detail=False, methods=["post"], url_path="bulk-create")
    @transaction.atomic
    def bulk_create(self, request):
        names = parse_bulk_lines(request.data.get("names") or "")
        names = [part.strip() for line in names for part in (line.split(",") if "|" not in line else [line]) if part.strip()]
        enabled = str(request.data.get("enabled", True)).lower() not in {"false", "0", "no"}
        if not names:
            return Response({"detail": "请至少填写一个研究方向。"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            default_weight = int(request.data.get("direction_weight", 3))
            default_priority = int(request.data.get("priority", 3))
        except (TypeError, ValueError):
            return Response({"detail": "研究相关度和关注优先级必须为 1-5 的整数。"}, status=status.HTTP_400_BAD_REQUEST)
        if not all(1 <= value <= 5 for value in (default_weight, default_priority)):
            return Response({"detail": "研究相关度和关注优先级必须为 1-5 的整数。"}, status=status.HTTP_400_BAD_REQUEST)
        parsed = []
        seen = set()
        for line in names:
            columns = [part.strip() for part in line.split("|")]
            if len(columns) not in {1, 4} or not columns[0]:
                return Response({"detail": f"格式错误：{line}"}, status=status.HTTP_400_BAD_REQUEST)
            try:
                weight = int(columns[2]) if len(columns) == 4 else default_weight
                priority = int(columns[3]) if len(columns) == 4 else default_priority
            except (TypeError, ValueError):
                return Response({"detail": f"研究相关度和关注优先级必须为整数：{line}"}, status=status.HTTP_400_BAD_REQUEST)
            if not all(1 <= value <= 5 for value in (weight, priority)):
                return Response({"detail": f"研究相关度和关注优先级必须为 1-5：{line}"}, status=status.HTTP_400_BAD_REQUEST)
            name, name_en = columns[0], columns[1] if len(columns) == 4 else ""
            if len(name) > 120 or len(name_en) > 240:
                return Response({"detail": f"名称过长：{name}"}, status=status.HTTP_400_BAD_REQUEST)
            if name.casefold() not in seen:
                parsed.append((name, name_en, weight, priority))
                seen.add(name.casefold())
        created = []
        updated = []
        for name, name_en, weight, priority in parsed:
            direction = ResearchDirection.objects.filter(name__iexact=name).first()
            was_created = direction is None
            if was_created:
                direction = ResearchDirection.objects.create(name=name, name_en=name_en or None, direction_weight=weight, priority=priority, enabled=enabled)
                created.append(direction.name)
            else:
                if name_en:
                    direction.name_en = name_en
                direction.direction_weight = weight
                direction.priority = priority
                direction.enabled = enabled
                direction.save()
                updated.append(direction.name)
        return Response({"created": created, "updated": updated})

    @action(detail=False, methods=["post"], url_path="bulk-delete")
    def bulk_delete(self, request):
        ids = parse_id_list(request.data.get("ids") or [])
        deleted, _ = ResearchDirection.objects.filter(id__in=ids).delete()
        return Response({"deleted": deleted})


class FetchLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = FetchLogSerializer

    def get_queryset(self):
        return filter_fetch_logs(FetchLog.objects.select_related("source").all(), self.request.query_params)


class DailyReportViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = DailyReport.objects.all()
    serializer_class = DailyReportSerializer

    @action(detail=False, methods=["post"])
    def regenerate(self, request):
        value = request.data.get("report_date")
        report_date = date.fromisoformat(value) if value else date.today()
        report = generate_daily_report(report_date)
        return Response(DailyReportSerializer(report).data)


class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        queryset = User.objects.all().order_by("-date_joined")
        params = self.request.query_params
        search = str(params.get("search") or "").strip()
        active = str(params.get("active") or "").strip().lower()
        staff = str(params.get("staff") or "").strip().lower()
        if search:
            queryset = queryset.filter(
                models.Q(username__icontains=search)
                | models.Q(email__icontains=search)
                | models.Q(first_name__icontains=search)
                | models.Q(last_name__icontains=search)
            )
        if active in {"true", "1", "yes"}:
            queryset = queryset.filter(is_active=True)
        elif active in {"false", "0", "no"}:
            queryset = queryset.filter(is_active=False)
        if staff in {"true", "1", "yes"}:
            queryset = queryset.filter(is_staff=True)
        elif staff in {"false", "0", "no"}:
            queryset = queryset.filter(is_staff=False)
        return queryset

    def destroy(self, request, *args, **kwargs):
        user = self.get_object()
        if user.pk == request.user.pk:
            return Response({"detail": "不能删除当前登录用户。"}, status=status.HTTP_400_BAD_REQUEST)
        return super().destroy(request, *args, **kwargs)


@api_view(["POST"])
def zotero_sync(request):
    raw_mark_existing = request.data.get("mark_existing", True)
    mark_existing = str(raw_mark_existing).lower() not in {"0", "false", "no"}
    try:
        result = sync_zotero_library(
            user_id=str(request.data.get("user_id", "")).strip(),
            group_id=str(request.data.get("group_id", "")).strip(),
            max_items=int(request.data.get("max_items") or 1000),
            mark_existing=mark_existing,
        )
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        logger.exception("Zotero legacy sync failed")
        return Response({"detail": f"Zotero 同步失败：{exc}"}, status=status.HTTP_502_BAD_GATEWAY)

    return Response(
        {
            "scanned_items": result.scanned_items,
            "matched_papers": result.matched_papers,
            "marked_imported": result.marked_imported,
            "suggestions": result.suggestions,
            "zotero_items": result.zotero_items,
            "collections": result.collections,
        }
    )


@api_view(["POST"])
def zotero_library(request):
    try:
        raw_refresh = request.data.get("refresh", False)
        refresh = str(raw_refresh).lower() in {"1", "true", "yes"}
        raw_max_items = request.data.get("max_items", 1000)
        if raw_max_items in {"", None}:
            raw_max_items = 1000
        payload = read_zotero_library(
            user_id=str(request.data.get("user_id", "")).strip(),
            group_id=str(request.data.get("group_id", "")).strip(),
            max_items=int(raw_max_items),
            refresh=refresh,
            full_sync=str(request.data.get("full_sync", False)).lower() in {"1", "true", "yes"},
            background=str(request.data.get("background", False)).lower() in {"1", "true", "yes"},
            include_items=str(request.data.get("include_items", True)).lower() in {"1", "true", "yes"},
        )
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        logger.exception("Zotero library sync failed")
        return Response({"detail": f"读取 Zotero 文献库失败：{exc}"}, status=status.HTTP_502_BAD_GATEWAY)
    return Response(payload)


@api_view(["GET"])
def zotero_library_items(request):
    try:
        payload = read_zotero_library_page(
            collection_key=str(request.query_params.get("collection", "__all__")),
            search=str(request.query_params.get("search", "")),
            year=str(request.query_params.get("year", "")),
            item_type=str(request.query_params.get("item_type", "")),
            sort_by=str(request.query_params.get("sort_by", "title")),
            sort_order=str(request.query_params.get("sort_order", "ascending")),
            page=int(request.query_params.get("page", 1)),
            page_size=int(request.query_params.get("page_size", 100)),
        )
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(payload)


@api_view(["GET"])
def zotero_item_detail(request, item_key: str):
    try:
        item = ZoteroItem.objects.get(key=item_key)
    except ZoteroItem.DoesNotExist:
        return Response({"detail": "Zotero 条目不存在"}, status=status.HTTP_404_NOT_FOUND)
    return Response(zotero_item_to_dict(item))


@api_view(["GET"])
def zotero_sync_status(request):
    return Response(get_zotero_sync_status())


@api_view(["POST"])
def zotero_import_paper(request):
    try:
        result = import_paper_to_zotero(
            paper_id=int(request.data.get("paper_id")),
            collection_key=str(request.data.get("collection_key", "")).strip(),
            collection_name=str(request.data.get("collection_name", "")).strip(),
            user_id=str(request.data.get("user_id", "")).strip(),
            group_id=str(request.data.get("group_id", "")).strip(),
        )
    except Paper.DoesNotExist:
        return Response({"detail": "文献不存在"}, status=status.HTTP_404_NOT_FOUND)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        logger.exception("Zotero import failed")
        return Response({"detail": f"导入 Zotero 失败：{exc}"}, status=status.HTTP_502_BAD_GATEWAY)
    return Response(result)


@api_view(["POST"])
def zotero_create_collection(request):
    try:
        result = create_zotero_collection(
            name=str(request.data.get("name", "")).strip(),
            parent_key=str(request.data.get("parent_key", "")).strip(),
            user_id=str(request.data.get("user_id", "")).strip(),
            group_id=str(request.data.get("group_id", "")).strip(),
        )
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        logger.exception("Zotero collection creation failed")
        return Response({"detail": f"创建 Zotero 文件夹失败：{exc}"}, status=status.HTTP_502_BAD_GATEWAY)
    return Response(result)


@api_view(["POST"])
def zotero_suggest_collection(request):
    try:
        result = suggest_collection_for_paper(
            paper_id=int(request.data.get("paper_id")),
            user_id=str(request.data.get("user_id", "")).strip(),
            group_id=str(request.data.get("group_id", "")).strip(),
        )
    except Paper.DoesNotExist:
        return Response({"detail": "文献不存在"}, status=status.HTTP_404_NOT_FOUND)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        logger.exception("Zotero collection suggestion failed")
        return Response({"detail": f"获取 Zotero 分组建议失败：{exc}"}, status=status.HTTP_502_BAD_GATEWAY)
    return Response(result)


@api_view(["GET", "POST"])
def zotero_config(request):
    config = ZoteroConfig.get_active() or ZoteroConfig(name="default", enabled=True)
    if request.method == "POST":
        config.library_type = str(request.data.get("library_type") or "user")
        config.user_id = str(request.data.get("user_id") or "").strip()
        config.group_id = str(request.data.get("group_id") or "").strip()
        incoming_key = str(request.data.get("api_key") or "").strip()
        if incoming_key:
            config.api_key = incoming_key
        config.enabled = True
        config.save()

    return Response(
        {
            "library_type": config.library_type,
            "user_id": config.user_id,
            "group_id": config.group_id,
            "has_api_key": bool(config.api_key),
            "api_key_masked": mask_key(config.api_key),
            "updated_at": config.updated_at,
        }
    )


def mask_key(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}...{value[-4:]}"


def parse_bulk_lines(value) -> list[str]:
    if isinstance(value, list):
        raw_items = [str(item) for item in value]
    else:
        raw = str(value or "").replace("；", "\n")
        raw_items = raw.splitlines()
    seen = set()
    rows = []
    for item in raw_items:
        text = item.strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        rows.append(text)
    return rows


def split_bulk_fields(line: str) -> list[str]:
    delimiter = "|" if "|" in line else "\t" if "\t" in line else ","
    return [item.strip() for item in line.split(delimiter) if item.strip()]


def clean_dashboard_label(value) -> str:
    text = str(value or "").strip()
    if text.lower().startswith("sciencedirect publication:"):
        text = text.split(":", 1)[1].strip()
    return text


def ranked_dashboard_rows(counter: dict[str, int], limit: int = 8) -> list[dict]:
    rows = [
        {"name": name, "count": count}
        for name, count in counter.items()
        if name and count
    ]
    rows.sort(key=lambda item: (-item["count"], item["name"].lower()))
    rows = rows[:limit]
    total_count = sum(item["count"] for item in rows) or 1
    return [
        {
            **item,
            "percent": round(item["count"] / total_count * 100, 1),
        }
        for item in rows
    ]


def parse_id_list(value) -> list[int]:
    ids = value if isinstance(value, list) else str(value or "").split(",")
    return [int(item) for item in ids if str(item).isdigit()]


def apply_low_score_filters(queryset, params):
    published_start = str(params.get("published_start") or "").strip()
    published_end = str(params.get("published_end") or "").strip()
    report_candidate = str(params.get("report_candidate") or "").strip().lower()
    rules = get_runtime_rules()
    if published_start:
        queryset = queryset.filter(published_date__gte=published_start)
    if published_end:
        queryset = queryset.filter(published_date__lte=published_end)
    if report_candidate in {"true", "1", "yes"}:
        queryset = queryset.filter(recommend_score__gte=int(rules["report_min_score"]), is_archived=False, is_soft_deleted=False)
        if not rules["show_weak_related"]:
            queryset = queryset.exclude(recommend_level__in=["weak", "low"])
    elif report_candidate in {"false", "0", "no"}:
        candidate = models.Q(recommend_score__lt=int(rules["report_min_score"])) | models.Q(is_archived=True) | models.Q(is_soft_deleted=True)
        if not rules["show_weak_related"]:
            candidate |= models.Q(recommend_level__in=["weak", "low"])
        queryset = queryset.filter(candidate)
    return queryset


@api_view(["GET", "POST"])
def scoring_settings(request):
    if request.method == "GET":
        return Response({"rules": get_runtime_rules(), "defaults": default_rules()})
    data = request.data or {}
    if get_active_rescore_task():
        return Response({"detail": "重新评分任务运行中，请完成后再修改规则。"}, status=status.HTTP_409_CONFLICT)
    rescore_scope = str(data.get("rescore_scope") or "none")
    if rescore_scope not in {"none", "7", "30", "all"}:
        return Response({"detail": "重新评分范围无效。"}, status=status.HTTP_400_BAD_REQUEST)
    try:
        rules = save_runtime_rules(data.get("rules", data))
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    task = None
    if rescore_scope != "none":
        task, _ = start_rescore_task(rescore_scope)
    return Response({"rules": rules, "task": rescore_task_payload(task) if task else None})


@api_view(["POST"])
def scoring_rescore_start(request):
    try:
        task, created = start_rescore_task(str(request.data.get("scope") or "all"))
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response({"task": rescore_task_payload(task), "created": created})


@api_view(["GET"])
def scoring_rescore_active(request):
    task = get_active_rescore_task()
    return Response({"task": rescore_task_payload(task) if task else None})


@api_view(["GET"])
def scoring_rescore_status(request, task_id):
    task = RescoreTask.objects.filter(task_id=task_id).first()
    if task is None:
        return Response({"detail": "任务不存在。"}, status=status.HTTP_404_NOT_FOUND)
    return Response({"task": rescore_task_payload(task)})


@api_view(["GET", "POST"])
def ai_settings(request):
    try:
        config = get_ai_config() if request.method == "GET" else save_ai_config(request.data or {})
    except AiConfigError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    response = Response(config)
    response["Cache-Control"] = "no-store"
    return response


@api_view(["POST"])
def scoring_settings_reset(request):
    if get_active_rescore_task():
        return Response({"detail": "重新评分任务运行中，请完成后再修改规则。"}, status=status.HTTP_409_CONFLICT)
    rules = reset_runtime_rules()
    return Response({"rules": rules, "defaults": default_rules()})


@api_view(["GET"])
def system_config_export(request):
    try:
        payload = export_system_config()
    except AiConfigError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    filename = f"researcher_radar_config_{timezone.localdate():%Y%m%d}.json"
    response = HttpResponse(
        json.dumps(payload, ensure_ascii=False, indent=2),
        content_type="application/json; charset=utf-8",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Cache-Control"] = "no-store"
    return response


@api_view(["POST"])
def system_config_import(request):
    try:
        result = import_system_config(request.data)
    except ConfigImportError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception:
        logger.exception("System configuration import failed")
        return Response({"detail": "配置导入失败，所有修改已回滚。"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return Response(result)


@api_view(["GET"])
def scoring_distribution(request):
    params = request.query_params
    range_value = str(params.get("range") or "all")
    selected_date = str(params.get("date") or "").strip()
    include_archived = str(params.get("include_archived") or "false").lower() in {"1", "true", "yes"}
    include_deleted = str(params.get("include_deleted") or "false").lower() in {"1", "true", "yes"}

    queryset = Paper.objects.filter(content_pruned_at__isnull=True).exclude(relevance_override="irrelevant")
    if not include_archived:
        queryset = queryset.filter(is_archived=False)
    if not include_deleted:
        queryset = queryset.filter(is_soft_deleted=False)
    if selected_date:
        queryset = queryset.filter(created_at__date=selected_date)
        range_value = "date"
    elif range_value == "30d":
        queryset = queryset.filter(created_at__gte=timezone.now() - timedelta(days=30))

    total = queryset.count()
    bucket_specs = [
        ("0-9", 0, 9, "低分区间；是否进入低分条目取决于低分阈值"),
        ("10-14", 10, 14, "弱相关，默认不进入日报"),
        ("15-29", 15, 29, "18 分起可进入日报候选"),
        ("30+", 30, None, "今日重点推荐文献"),
    ]
    buckets = []
    for label, min_score, max_score, meaning in bucket_specs:
        bucket_qs = queryset.filter(recommend_score__gte=min_score)
        if max_score is not None:
            bucket_qs = bucket_qs.filter(recommend_score__lte=max_score)
        count = bucket_qs.count()
        ratio = round((count / total * 100), 1) if total else 0
        buckets.append(
            {
                "label": label,
                "min": min_score,
                "max": max_score,
                "count": count,
                "ratio": ratio,
                "meaning": meaning,
            }
        )
    return Response(
        {
            "range": range_value,
            "date": selected_date,
            "total": total,
            "include_archived": include_archived,
            "include_deleted": include_deleted,
            "buckets": buckets,
        }
    )


@api_view(["POST"])
def fetch_daily_now(request):
    task, created = start_fetch_task()
    payload = fetch_task_payload(task)
    payload["created"] = created
    return Response(payload, status=status.HTTP_202_ACCEPTED)


@api_view(["GET"])
def fetch_daily_active(request):
    task = get_active_fetch_task()
    if not task:
        return Response({"active": False})
    payload = fetch_task_payload(task)
    payload["active"] = True
    return Response(payload)


@api_view(["GET"])
def fetch_daily_status(request, task_id):
    try:
        task = FetchTask.objects.get(task_id=task_id)
    except FetchTask.DoesNotExist:
        return Response({"detail": "抓取任务不存在"}, status=status.HTTP_404_NOT_FOUND)
    return Response(fetch_task_payload(task))


def fetch_task_payload(task: FetchTask) -> dict:
    return {
        "task_id": str(task.task_id),
        "status": task.status,
        "message": task.message,
        "error_detail": task.error_detail,
        "source_total": task.source_total,
        "success_sources": task.success_sources,
        "failed_sources": task.failed_sources,
        "fetched_count": task.fetched_count,
        "new_count": task.new_count,
        "duplicate_count": task.duplicate_count,
        "report_date": task.report_date.isoformat() if task.report_date else "",
        "report_title": task.report_title,
        "paper_count": task.paper_count,
        "started_at": task.started_at.isoformat() if task.started_at else "",
        "finished_at": task.finished_at.isoformat() if task.finished_at else "",
        "created_at": task.created_at.isoformat() if task.created_at else "",
        "updated_at": task.updated_at.isoformat() if task.updated_at else "",
    }


@api_view(["GET"])
def abstract_update_active(request):
    task = get_active_abstract_task()
    if not task:
        return Response({"active": False})
    payload = abstract_task_payload(task)
    payload["active"] = True
    return Response(payload)


@api_view(["GET"])
def abstract_update_status(request, task_id):
    try:
        task = AbstractUpdateTask.objects.get(task_id=task_id)
    except AbstractUpdateTask.DoesNotExist:
        return Response({"detail": "摘要更新任务不存在"}, status=status.HTTP_404_NOT_FOUND)
    return Response(abstract_task_payload(task))


def abstract_task_payload(task: AbstractUpdateTask) -> dict:
    return {
        "task_id": str(task.task_id),
        "status": task.status,
        "message": task.message,
        "error_detail": task.error_detail,
        "selected_date": task.selected_date.isoformat() if task.selected_date else "",
        "paper_ids": task.paper_ids,
        "target_count": task.target_count,
        "checked": task.checked,
        "updated": task.updated,
        "not_found": task.not_found,
        "failed": task.failed,
        "started_at": task.started_at.isoformat() if task.started_at else "",
        "finished_at": task.finished_at.isoformat() if task.finished_at else "",
        "created_at": task.created_at.isoformat() if task.created_at else "",
        "updated_at": task.updated_at.isoformat() if task.updated_at else "",
    }
