from __future__ import annotations

import hashlib
import uuid

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        abstract = True


class LoginAttempt(models.Model):
    identity_hash = models.CharField(max_length=64, primary_key=True)
    failures = models.PositiveSmallIntegerField(default=0)
    expires_at = models.DateTimeField(db_index=True)
    updated_at = models.DateTimeField(default=timezone.now)


class ResearchDirection(TimeStampedModel):
    name = models.CharField(max_length=120, unique=True, verbose_name="研究方向名称")
    name_cn = models.CharField(max_length=120, unique=True, verbose_name="中文名称")
    name_en = models.CharField(max_length=240, null=True, blank=True, verbose_name="英文名称")
    direction_weight = models.PositiveSmallIntegerField(default=3, validators=[MinValueValidator(1), MaxValueValidator(5)], verbose_name="方向权重")
    priority = models.PositiveSmallIntegerField(default=3, validators=[MinValueValidator(1), MaxValueValidator(5)], verbose_name="优先级")
    enabled = models.BooleanField(default=True, verbose_name="是否启用")

    class Meta:
        ordering = ["name"]
        verbose_name = "研究方向"
        verbose_name_plural = "研究方向"
        constraints = [
            models.CheckConstraint(condition=models.Q(direction_weight__gte=1, direction_weight__lte=5), name="direction_weight_1_5"),
            models.CheckConstraint(condition=models.Q(priority__gte=1, priority__lte=5), name="direction_priority_1_5"),
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).values("name", "name_cn").first()
            if previous and self.name != self.name_cn:
                if self.name != previous["name"] and self.name_cn == previous["name_cn"]:
                    self.name_cn = self.name
                else:
                    self.name = self.name_cn
        else:
            self.name_cn = self.name_cn or self.name
            self.name = self.name_cn
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and {"name", "name_cn"} & set(update_fields):
            kwargs["update_fields"] = set(update_fields) | {"name", "name_cn"}
        super().save(*args, **kwargs)


class Keyword(TimeStampedModel):
    keyword = models.CharField(max_length=120, unique=True, verbose_name="关键词")
    aliases = models.TextField(blank=True, verbose_name="同义词（每行一个）")
    is_exclusion = models.BooleanField(default=False, verbose_name="排除词")
    weight = models.IntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(5)], verbose_name="权重")
    enabled = models.BooleanField(default=True, verbose_name="是否启用")
    description = models.TextField(blank=True, verbose_name="说明")
    direction = models.ForeignKey(
        ResearchDirection,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="keywords",
        verbose_name="研究方向",
    )

    class Meta:
        ordering = ["keyword"]
        verbose_name = "关键词"
        verbose_name_plural = "关键词"
        constraints = [models.CheckConstraint(condition=models.Q(weight__gte=1, weight__lte=5), name="keyword_weight_1_5")]

    def __str__(self) -> str:
        return self.keyword


class RssSource(TimeStampedModel):
    FETCH_MODE_CHOICES = [
        ("rss", "RSS"),
        ("openalex", "OpenAlex"),
        ("both", "RSS + OpenAlex"),
    ]
    STATUS_CHOICES = [
        ("pending", "pending"),
        ("success", "success"),
        ("failed", "failed"),
        ("partial", "partial"),
    ]

    name = models.CharField(max_length=200, verbose_name="RSS 源名称")
    url = models.URLField(blank=True, verbose_name="RSS 地址")
    fetch_mode = models.CharField(max_length=12, choices=FETCH_MODE_CHOICES, default="rss", verbose_name="抓取方式")
    openalex_issn = models.CharField(max_length=20, blank=True, db_index=True, verbose_name="OpenAlex ISSN")
    journal = models.CharField(max_length=200, blank=True, verbose_name="期刊名称")
    enabled = models.BooleanField(default=True, verbose_name="是否启用")
    remark = models.TextField(blank=True, verbose_name="备注")
    last_fetch_time = models.DateTimeField(null=True, blank=True, verbose_name="最近抓取时间")
    last_fetch_status = models.CharField(max_length=20, choices=STATUS_CHOICES, blank=True, verbose_name="最近抓取状态")
    last_fetch_message = models.TextField(blank=True, verbose_name="最近抓取信息")
    total_fetched_count = models.IntegerField(default=0, verbose_name="累计抓取数量")

    class Meta:
        ordering = ["name"]
        verbose_name = "RSS 源"
        verbose_name_plural = "RSS 源"
        constraints = [models.UniqueConstraint(fields=["url"], condition=~models.Q(url=""), name="unique_nonempty_rss_source_url")]

    def __str__(self) -> str:
        return self.name

    def clean(self):
        if self.fetch_mode in {"rss", "both"} and not self.url:
            raise ValidationError({"url": "RSS 抓取方式需要填写 URL。"})
        if self.fetch_mode in {"openalex", "both"} and not self.openalex_issn:
            raise ValidationError({"openalex_issn": "OpenAlex 抓取方式需要填写 ISSN。"})


class Paper(TimeStampedModel):
    RECOMMEND_LEVEL_CHOICES = [
        ("key", "重点推荐"),
        ("normal", "一般推荐"),
        ("weak", "弱相关"),
        ("low", "低相关归档"),
    ]

    title = models.TextField(verbose_name="标题")
    authors = models.TextField(blank=True, verbose_name="作者")
    journal = models.CharField(max_length=240, blank=True, verbose_name="期刊")
    published_date = models.DateField(null=True, blank=True, verbose_name="发布日期")
    doi = models.CharField(max_length=255, blank=True, null=True, db_index=True, verbose_name="DOI")
    normalized_doi = models.CharField(max_length=255, blank=True, db_index=True, verbose_name="规范化 DOI")
    normalized_title_hash = models.CharField(max_length=64, blank=True, db_index=True, verbose_name="规范化标题检索键")
    url = models.URLField(blank=True, verbose_name="原文链接")
    abstract = models.TextField(blank=True, verbose_name="摘要")
    ai_summary = models.TextField(blank=True, verbose_name="AI 摘要")
    ai_summary_model = models.CharField(max_length=120, blank=True, verbose_name="AI 摘要模型")
    ai_summary_input_hash = models.CharField(max_length=64, blank=True, verbose_name="AI 摘要输入哈希")
    ai_summarized_at = models.DateTimeField(null=True, blank=True, verbose_name="AI 摘要生成时间")
    source = models.ForeignKey(
        RssSource,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="papers",
        verbose_name="RSS 源",
    )
    source_name = models.CharField(max_length=200, blank=True, verbose_name="来源名称")
    source_url = models.URLField(blank=True, verbose_name="来源地址")
    keywords = models.ManyToManyField(Keyword, blank=True, related_name="papers", verbose_name="关键词")
    directions = models.ManyToManyField(ResearchDirection, blank=True, related_name="papers", verbose_name="研究方向")
    raw_keywords = models.TextField(blank=True, verbose_name="原始关键词")
    is_favorite = models.BooleanField(default=False, db_index=True, verbose_name="是否收藏")
    zotero_imported = models.BooleanField(default=False, db_index=True, verbose_name="已导入 Zotero")
    zotero_imported_at = models.DateTimeField(null=True, blank=True, verbose_name="Zotero 导入时间")
    zotero_collection_key = models.CharField(max_length=120, blank=True, verbose_name="Zotero Collection Key")
    zotero_collection_name = models.CharField(max_length=255, blank=True, verbose_name="Zotero Collection Name")
    recommend_score = models.IntegerField(default=0, db_index=True, verbose_name="推荐分数")
    system_recommend_score = models.IntegerField(null=True, blank=True, verbose_name="系统原评分")
    relevance_override = models.CharField(max_length=20, blank=True, default="", choices=[("", "未标记"), ("irrelevant", "不相关")], db_index=True, verbose_name="相关性标记")
    recommend_level = models.CharField(
        max_length=20,
        choices=RECOMMEND_LEVEL_CHOICES,
        default="low",
        db_index=True,
        verbose_name="推荐等级",
    )
    matched_fields = models.JSONField(default=dict, blank=True, verbose_name="命中字段")
    score_detail = models.JSONField(default=dict, blank=True, verbose_name="分数明细")
    scored_at = models.DateTimeField(null=True, blank=True, verbose_name="最近评分时间")
    is_archived = models.BooleanField(default=False, db_index=True, verbose_name="已归档")
    is_soft_deleted = models.BooleanField(default=False, db_index=True, verbose_name="已软删除")
    content_pruned_at = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name="低相关内容清理时间")
    dedup_key = models.CharField(max_length=64, unique=True, db_index=True, verbose_name="去重键")

    class Meta:
        ordering = ["-published_date", "-created_at"]
        verbose_name = "文献"
        verbose_name_plural = "文献"
        indexes = [
            models.Index(fields=["journal", "published_date"]),
            models.Index(fields=["is_favorite", "created_at"]),
            models.Index(fields=["is_favorite", "zotero_imported"]),
            models.Index(fields=["recommend_level", "recommend_score"]),
            models.Index(fields=["content_pruned_at", "created_at", "recommend_score"], name="paper_recent_low_idx2"),
            models.Index(fields=["is_archived", "is_soft_deleted"]),
        ]

    def __str__(self) -> str:
        return self.title[:120]

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        if update_fields is None or "doi" in update_fields:
            self.normalized_doi = normalize_doi(self.doi)
        if update_fields is None or "title" in update_fields:
            self.normalized_title_hash = normalized_title_hash(self.title)
        if update_fields is not None:
            fields = set(update_fields)
            if "doi" in fields:
                fields.add("normalized_doi")
            if "title" in fields:
                fields.add("normalized_title_hash")
            kwargs["update_fields"] = fields
        return super().save(*args, **kwargs)

    def mark_zotero_imported(self, collection_key: str = "", collection_name: str = "") -> None:
        self.zotero_imported = True
        self.zotero_imported_at = timezone.now()
        self.zotero_collection_key = collection_key
        self.zotero_collection_name = collection_name
        self.save(update_fields=[
            "zotero_imported",
            "zotero_imported_at",
            "zotero_collection_key",
            "zotero_collection_name",
            "updated_at",
        ])

    @staticmethod
    def build_dedup_key(title: str = "", journal: str = "", published_date: str | None = "", doi: str | None = "", url: str = "") -> str:
        if doi:
            raw = f"doi:{normalize_doi(doi)}"
        elif url:
            raw = f"url:{url.strip().lower()}"
        else:
            raw = f"title:{normalize_space(title).lower()}|journal:{normalize_space(journal).lower()}|date:{published_date or ''}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class DailyReport(TimeStampedModel):
    report_date = models.DateField(unique=True, verbose_name="日报日期")
    title = models.CharField(max_length=200, verbose_name="日报标题")
    html_content = models.TextField(blank=True, verbose_name="HTML 内容")
    markdown_content = models.TextField(blank=True, verbose_name="Markdown 内容")
    paper_count = models.IntegerField(default=0, verbose_name="文献数量")

    class Meta:
        ordering = ["-report_date"]
        verbose_name = "日报"
        verbose_name_plural = "日报"

    def __str__(self) -> str:
        return self.title


class FetchLog(models.Model):
    STATUS_CHOICES = [
        ("success", "success"),
        ("failed", "failed"),
        ("partial", "partial"),
    ]

    source = models.ForeignKey(
        RssSource,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="fetch_logs",
        verbose_name="RSS 源",
    )
    source_name = models.CharField(max_length=200, blank=True, verbose_name="RSS 源名称")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, verbose_name="状态")
    message = models.TextField(blank=True, verbose_name="简要信息")
    error_detail = models.TextField(blank=True, verbose_name="错误详情")
    fetched_count = models.IntegerField(default=0, verbose_name="抓取总数")
    new_count = models.IntegerField(default=0, verbose_name="新增数量")
    duplicate_count = models.IntegerField(default=0, verbose_name="重复数量")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "抓取日志"
        verbose_name_plural = "抓取日志"

    def __str__(self) -> str:
        return f"{self.source_name} {self.status} {self.created_at:%Y-%m-%d %H:%M}"


class FetchTask(TimeStampedModel):
    STATUS_CHOICES = [
        ("pending", "pending"),
        ("running", "running"),
        ("success", "success"),
        ("failed", "failed"),
    ]

    task_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    worker_pid = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True)
    message = models.TextField(blank=True)
    error_detail = models.TextField(blank=True)
    source_total = models.IntegerField(default=0)
    success_sources = models.IntegerField(default=0)
    failed_sources = models.IntegerField(default=0)
    fetched_count = models.IntegerField(default=0)
    new_count = models.IntegerField(default=0)
    duplicate_count = models.IntegerField(default=0)
    report_date = models.DateField(null=True, blank=True)
    report_title = models.CharField(max_length=255, blank=True)
    paper_count = models.IntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Fetch Task"
        verbose_name_plural = "Fetch Tasks"

    def __str__(self) -> str:
        return f"{self.task_id} {self.status}"


class RescoreTask(TimeStampedModel):
    task_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    worker_pid = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=[
        ("pending", "等待中"), ("running", "运行中"), ("success", "完成"),
        ("partial", "部分失败"), ("failed", "失败"),
    ], default="pending", db_index=True)
    scope = models.CharField(max_length=8, choices=[("7", "最近 7 天"), ("30", "最近 30 天"), ("all", "全部")], default="all")
    target_count = models.PositiveIntegerField(default=0)
    processed_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    message = models.TextField(blank=True)
    error_detail = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "重新评分任务"
        verbose_name_plural = "重新评分任务"


class AbstractUpdateTask(TimeStampedModel):
    STATUS_CHOICES = [
        ("pending", "pending"),
        ("running", "running"),
        ("success", "success"),
        ("failed", "failed"),
    ]

    task_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    worker_pid = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True)
    message = models.TextField(blank=True)
    error_detail = models.TextField(blank=True)
    selected_date = models.DateField(null=True, blank=True, db_index=True)
    paper_ids = models.JSONField(default=list, blank=True)
    target_count = models.IntegerField(default=0)
    checked = models.IntegerField(default=0)
    updated = models.IntegerField(default=0)
    not_found = models.IntegerField(default=0)
    failed = models.IntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Abstract Update Task"
        verbose_name_plural = "Abstract Update Tasks"

    def __str__(self) -> str:
        return f"{self.task_id} {self.status}"


class ZoteroConfig(TimeStampedModel):
    LIBRARY_CHOICES = [
        ("user", "个人文献库"),
        ("group", "群组文献库"),
    ]

    name = models.CharField(max_length=80, default="default", unique=True, verbose_name="配置名称")
    library_type = models.CharField(max_length=12, choices=LIBRARY_CHOICES, default="user", verbose_name="文献库类型")
    user_id = models.CharField(max_length=80, blank=True, verbose_name="Zotero User ID")
    group_id = models.CharField(max_length=80, blank=True, verbose_name="Zotero Group ID")
    api_key = models.CharField(max_length=255, blank=True, verbose_name="Zotero Access Key")
    enabled = models.BooleanField(default=True, verbose_name="启用")

    class Meta:
        verbose_name = "Zotero 配置"
        verbose_name_plural = "Zotero 配置"

    def __str__(self) -> str:
        return "Zotero 配置"

    @classmethod
    def get_active(cls) -> "ZoteroConfig | None":
        return cls.objects.filter(enabled=True).order_by("-updated_at").first()


class SystemSetting(TimeStampedModel):
    key = models.CharField(max_length=120, unique=True, db_index=True, verbose_name="配置键")
    value = models.JSONField(default=dict, blank=True, verbose_name="配置值")
    description = models.TextField(blank=True, verbose_name="说明")

    class Meta:
        ordering = ["key"]
        verbose_name = "系统配置"
        verbose_name_plural = "系统配置"

    def __str__(self) -> str:
        return self.key


class ZoteroSyncState(TimeStampedModel):
    STATUS_CHOICES = [
        ("idle", "未运行"),
        ("running", "运行中"),
        ("success", "成功"),
        ("failed", "失败"),
    ]
    MODE_CHOICES = [
        ("quick", "快速同步"),
        ("full", "全量校准"),
    ]

    name = models.CharField(max_length=80, default="default", unique=True)
    library_version = models.IntegerField(default=0)
    item_count = models.IntegerField(default=0)
    collection_count = models.IntegerField(default=0)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    sync_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="idle", db_index=True)
    sync_mode = models.CharField(max_length=20, choices=MODE_CHOICES, default="quick")
    sync_started_at = models.DateTimeField(null=True, blank=True)
    sync_finished_at = models.DateTimeField(null=True, blank=True)
    sync_error = models.TextField(blank=True)

    class Meta:
        verbose_name = "Zotero 同步状态"
        verbose_name_plural = "Zotero 同步状态"

    def __str__(self) -> str:
        return f"Zotero sync v{self.library_version}"


class ZoteroCollection(TimeStampedModel):
    key = models.CharField(max_length=120, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    parent_key = models.CharField(max_length=120, blank=True, db_index=True)
    item_count = models.IntegerField(default=0)
    zotero_version = models.IntegerField(default=0)
    raw = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Zotero Collection"
        verbose_name_plural = "Zotero Collections"

    def __str__(self) -> str:
        return self.name


class ZoteroItem(TimeStampedModel):
    key = models.CharField(max_length=120, unique=True, db_index=True)
    identity_key = models.CharField(max_length=320, blank=True, db_index=True)
    title = models.TextField(blank=True)
    creator = models.TextField(blank=True)
    creators = models.JSONField(default=list, blank=True)
    doi = models.CharField(max_length=255, blank=True, db_index=True)
    journal = models.CharField(max_length=255, blank=True)
    date = models.CharField(max_length=80, blank=True)
    url = models.URLField(blank=True, max_length=1000)
    item_type = models.CharField(max_length=80, blank=True)
    abstract = models.TextField(blank=True)
    publisher = models.CharField(max_length=255, blank=True)
    volume = models.CharField(max_length=80, blank=True)
    issue = models.CharField(max_length=80, blank=True)
    pages = models.CharField(max_length=80, blank=True)
    language = models.CharField(max_length=80, blank=True)
    issn = models.CharField(max_length=120, blank=True)
    isbn = models.CharField(max_length=120, blank=True)
    archive = models.CharField(max_length=255, blank=True)
    library_catalog = models.CharField(max_length=255, blank=True)
    extra = models.TextField(blank=True)
    date_added = models.CharField(max_length=80, blank=True)
    date_modified = models.CharField(max_length=80, blank=True)
    access_date = models.CharField(max_length=80, blank=True)
    tags = models.JSONField(default=list, blank=True)
    collections = models.JSONField(default=list, blank=True)
    zotero_version = models.IntegerField(default=0)
    raw = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["title"]
        verbose_name = "Zotero Item"
        verbose_name_plural = "Zotero Items"

    def __str__(self) -> str:
        return self.title[:120] or self.key


def normalize_doi(value: str | None) -> str:
    text = str(value or "").strip()
    text = text.removeprefix("https://doi.org/").removeprefix("http://doi.org/")
    text = text.removeprefix("doi:")
    return text.strip().lower()


def normalize_space(value: str | None) -> str:
    return " ".join(str(value or "").split())


def normalized_title_hash(value: str | None) -> str:
    title = normalize_space(value).lower()
    return hashlib.sha256(title.encode("utf-8")).hexdigest() if title else ""
