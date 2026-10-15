from __future__ import annotations

import base64
import hashlib
import os
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

from papers.models import SystemSetting


CONFIG_KEY = "ai_summary_provider"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-flash"


class AiConfigError(ValueError):
    pass


def _cipher() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest())
    return Fernet(key)


def _validate_base_url(value: str) -> str:
    url = value.strip().rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}):
        raise AiConfigError("AI 接口地址须使用 HTTPS，本机 localhost 或 127.0.0.1 可使用 HTTP。")
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise AiConfigError("AI 接口地址格式不正确。")
    if url.endswith("/chat/completions"):
        raise AiConfigError("请填写接口基础地址，不要包含 /chat/completions。")
    return url


def get_ai_config(*, include_key: bool = False) -> dict:
    row = SystemSetting.objects.filter(key=CONFIG_KEY).first()
    if row:
        value = row.value or {}
        encrypted = value.get("api_key_encrypted", "")
        result = {
            "provider": value.get("provider", "deepseek"),
            "base_url": value.get("base_url", DEEPSEEK_BASE_URL),
            "model": value.get("model", DEEPSEEK_MODEL),
            "has_api_key": bool(encrypted),
            "source": "saved",
            "updated_at": row.updated_at,
        }
        if include_key:
            try:
                result["api_key"] = _cipher().decrypt(encrypted.encode("ascii")).decode("utf-8") if encrypted else ""
            except (InvalidToken, ValueError) as exc:
                raise AiConfigError("已保存的 AI Key 无法读取，请在系统管理中重新设置。") from exc
        return result

    env_key = os.getenv("LITERATURE_AI_API_KEY", "").strip()
    env_model = os.getenv("LITERATURE_AI_MODEL", "").strip()
    env_url = os.getenv("LITERATURE_AI_BASE_URL", "").strip()
    result = {
        "provider": "custom" if env_key or env_model else "deepseek",
        "base_url": env_url or ("https://api.openai.com/v1" if env_key else DEEPSEEK_BASE_URL),
        "model": env_model or DEEPSEEK_MODEL,
        "has_api_key": bool(env_key),
        "source": "environment" if env_key or env_model else "none",
        "updated_at": None,
    }
    if include_key:
        result["api_key"] = env_key
    return result


def save_ai_config(data: dict) -> dict:
    provider = str(data.get("provider") or "deepseek").strip()
    if provider not in {"deepseek", "custom"}:
        raise AiConfigError("不支持的 AI 服务类型。")
    base_url = _validate_base_url(str(data.get("base_url") or ""))
    model = str(data.get("model") or "").strip()
    if not model or len(model) > 120:
        raise AiConfigError("请填写有效的模型名称（最多 120 个字符）。")
    row = SystemSetting.objects.filter(key=CONFIG_KEY).first()
    previous = row.value if row else {}
    previous = previous or {}
    encrypted = previous.get("api_key_encrypted", "")
    if data.get("clear_api_key") is True:
        encrypted = ""
    incoming_key = str(data.get("api_key") or "").strip()
    if incoming_key:
        encrypted = _cipher().encrypt(incoming_key.encode("utf-8")).decode("ascii")
    if not encrypted:
        raise AiConfigError("首次保存 AI 设置时请填写 API Key。")
    value = {"provider": provider, "base_url": base_url, "model": model, "api_key_encrypted": encrypted}
    if row:
        row.value = value
        row.save(update_fields=["value", "updated_at"])
    else:
        SystemSetting.objects.create(key=CONFIG_KEY, value=value, description="AI 速读服务配置")
    return get_ai_config()
