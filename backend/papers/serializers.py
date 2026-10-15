from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import DailyReport, FetchLog, Keyword, Paper, ResearchDirection, RssSource

User = get_user_model()


class ResearchDirectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResearchDirection
        fields = "__all__"
        extra_kwargs = {
            "name": {"required": False},
            "name_cn": {"required": False},
            "direction_weight": {
                "label": "研究相关度",
                "help_text": "1-5，表示该方向与长期科研兴趣的匹配程度，参与文献推荐评分。",
            },
            "priority": {
                "label": "关注优先级",
                "help_text": "1-5，用于日报和列表排序，不直接改变文献相关性评分。",
            },
        }

    def validate(self, attrs):
        name = attrs.get("name")
        name_cn = attrs.get("name_cn")
        if name and name_cn and name != name_cn:
            raise serializers.ValidationError({"name_cn": "中文名称与兼容名称必须一致。"})
        if name_cn:
            attrs["name"] = name_cn
        elif name:
            attrs["name_cn"] = name
        elif self.instance is None:
            raise serializers.ValidationError({"name_cn": "请填写中文名称。"})
        return attrs


class KeywordSerializer(serializers.ModelSerializer):
    direction_name = serializers.CharField(source="direction.name", read_only=True)

    def validate(self, attrs):
        direction = attrs.get("direction", getattr(self.instance, "direction", None))
        if direction is None:
            raise serializers.ValidationError({"direction": "请选择研究方向。"})
        return attrs

    class Meta:
        model = Keyword
        fields = "__all__"


class RssSourceSerializer(serializers.ModelSerializer):
    def validate(self, attrs):
        mode = attrs.get("fetch_mode", getattr(self.instance, "fetch_mode", "rss"))
        url = attrs.get("url", getattr(self.instance, "url", ""))
        issn = attrs.get("openalex_issn", getattr(self.instance, "openalex_issn", ""))
        if mode in {"rss", "both"} and not url:
            raise serializers.ValidationError({"url": "RSS 抓取方式需要填写 URL。"})
        if mode in {"openalex", "both"} and not issn:
            raise serializers.ValidationError({"openalex_issn": "OpenAlex 抓取方式需要填写 ISSN。"})
        return attrs

    class Meta:
        model = RssSource
        fields = "__all__"


class PaperSerializer(serializers.ModelSerializer):
    keywords = KeywordSerializer(many=True, read_only=True)
    directions = ResearchDirectionSerializer(many=True, read_only=True)
    keyword_ids = serializers.PrimaryKeyRelatedField(
        source="keywords",
        queryset=Keyword.objects.all(),
        many=True,
        write_only=True,
        required=False,
    )
    direction_ids = serializers.PrimaryKeyRelatedField(
        source="directions",
        queryset=ResearchDirection.objects.all(),
        many=True,
        write_only=True,
        required=False,
    )
    source_name_display = serializers.CharField(source="source.name", read_only=True)
    matched_keywords = serializers.SerializerMethodField()
    matched_directions = serializers.SerializerMethodField()
    is_daily_candidate = serializers.SerializerMethodField()
    is_key_paper = serializers.SerializerMethodField()

    class Meta:
        model = Paper
        read_only_fields = ("ai_summary", "ai_summary_model", "ai_summarized_at", "system_recommend_score", "relevance_override")
        fields = [
            "id",
            "title",
            "authors",
            "journal",
            "published_date",
            "doi",
            "url",
            "abstract",
            "ai_summary",
            "ai_summary_model",
            "ai_summarized_at",
            "source",
            "source_name",
            "source_name_display",
            "source_url",
            "keywords",
            "directions",
            "keyword_ids",
            "direction_ids",
            "raw_keywords",
            "is_favorite",
            "zotero_imported",
            "zotero_imported_at",
            "zotero_collection_key",
            "zotero_collection_name",
            "recommend_score",
            "system_recommend_score",
            "relevance_override",
            "recommend_level",
            "matched_fields",
            "score_detail",
            "scored_at",
            "is_archived",
            "is_soft_deleted",
            "matched_keywords",
            "matched_directions",
            "is_daily_candidate",
            "is_key_paper",
            "created_at",
            "updated_at",
        ]

    def get_matched_keywords(self, obj):
        return [item.keyword for item in obj.keywords.all()]

    def get_matched_directions(self, obj):
        return [item.name for item in obj.directions.all()]

    def get_is_daily_candidate(self, obj):
        from .services.runtime_settings import get_runtime_rules

        rules = get_runtime_rules()
        if obj.is_archived or obj.is_soft_deleted:
            return False
        if obj.recommend_score < int(rules["report_min_score"]):
            return False
        if not rules["show_weak_related"] and obj.recommend_level in {"weak", "low"}:
            return False
        return True

    def get_is_key_paper(self, obj):
        from .services.runtime_settings import get_runtime_rules

        rules = get_runtime_rules()
        return not obj.is_archived and not obj.is_soft_deleted and obj.recommend_score >= int(rules["key_threshold"])


class DailyReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyReport
        fields = "__all__"


class FetchLogSerializer(serializers.ModelSerializer):
    source_display = serializers.CharField(source="source.name", read_only=True)

    class Meta:
        model = FetchLog
        fields = "__all__"


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "is_staff",
            "is_superuser",
            "last_login",
            "date_joined",
            "password",
        ]
        read_only_fields = ["id", "last_login", "date_joined"]

    def validate(self, attrs):
        if self.instance is None and not attrs.get("password"):
            raise serializers.ValidationError({"password": "新建用户时请填写初始密码。"})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password", "")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", "")
        for key, value in validated_data.items():
            setattr(instance, key, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance
