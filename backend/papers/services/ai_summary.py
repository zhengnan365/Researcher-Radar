from __future__ import annotations

import hashlib
import requests
from django.utils import timezone

from papers.models import Paper
from papers.services.ai_config import AiConfigError, get_ai_config


class AiSummaryError(ValueError):
    pass


def summarize_paper(paper: Paper, *, force: bool = False) -> Paper:
    if not paper.abstract.strip():
        raise AiSummaryError("这篇文献没有原始摘要，无法可靠生成 AI 摘要。")
    content = f"标题：{paper.title}\n原始摘要：{paper.abstract[:12000]}"
    input_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if paper.ai_summary and paper.ai_summary_input_hash == input_hash and not force:
        return paper

    try:
        config = get_ai_config(include_key=True)
    except AiConfigError as exc:
        raise AiSummaryError(str(exc)) from exc
    api_key = config["api_key"]
    model = config["model"]
    if not api_key or not model:
        raise AiSummaryError("请先到系统管理 → AI 与 Zotero 设置中保存 API Key 和模型。")
    base_url = config["base_url"].rstrip("/")
    if not base_url.startswith("https://") and not base_url.startswith("http://localhost") and not base_url.startswith("http://127.0.0.1"):
        raise AiSummaryError("AI 接口地址必须使用 HTTPS（本机接口除外）。")
    response = requests.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": "你是严谨的文献速读助手。只能依据用户提供的标题和原始摘要，用中文提炼研究问题、方法、主要发现与局限。摘要未明确给出的信息写“原始摘要未说明”，不得推测数值、结论或全文内容。输出简洁纯文本。"},
                {"role": "user", "content": content},
            ],
        },
        timeout=45,
    )
    response.raise_for_status()
    try:
        summary = str(response.json()["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise AiSummaryError("AI 服务返回格式不正确。") from exc
    if not summary:
        raise AiSummaryError("AI 服务没有返回摘要。")
    paper.ai_summary = summary[:10000]
    paper.ai_summary_model = model
    paper.ai_summary_input_hash = input_hash
    paper.ai_summarized_at = timezone.now()
    paper.save(update_fields=["ai_summary", "ai_summary_model", "ai_summary_input_hash", "ai_summarized_at", "updated_at"])
    return paper
