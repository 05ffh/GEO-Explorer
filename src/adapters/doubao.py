"""Doubao adapter — 火山方舟豆包大模型，联网搜索走 Responses API web_search 工具。

联网搜索由火山引擎服务端托管执行，需在控制台开通「联网搜索」插件
（console.volcengine.com/common-buy/CC_content_plugin），模型需支持 web_search。
"""

import time

from src.adapters.base import OpenAICompatibleAdapter, AIResponse
from src.config import settings


class DoubaoAdapter(OpenAICompatibleAdapter):
    platform_name = "doubao"
    base_url = settings.doubao_base_url
    default_model = settings.doubao_model
    api_key = settings.doubao_api_key
    default_search_enabled = True

    async def query(self, prompt: str, system_prompt: str = "", **kwargs) -> AIResponse:
        search_enabled = kwargs.get("search_enabled", self.default_search_enabled)
        if not search_enabled:
            return await super().query(prompt, system_prompt, **kwargs)

        start = time.time()
        model = kwargs.get("model", self.default_model)
        try:
            resp = await self.client.responses.create(
                model=model,
                instructions=system_prompt or "你是一个诚实的AI助手。",
                input=prompt,
                tools=[{"type": "web_search"}],
            )
            latency = int((time.time() - start) * 1000)

            answer = (resp.output_text or "").strip()
            citations = await self.extract_citations(answer)

            return AIResponse(
                platform=self.platform_name, question=prompt, answer_text=answer,
                answer_source="content" if answer else "empty",
                error_code=None if answer else "platform_empty_response",
                citations=citations,
                model_name=model, model_version=getattr(resp, "model", "") or "",
                raw_response=resp.model_dump(), latency_ms=latency,
            )
        except Exception as e:  # noqa: BLE001 — low-risk: graceful degradation
            error_str = str(e)
            code, retry = self._classify_error(error_str, type(e).__name__, e)
            return AIResponse(
                platform=self.platform_name, question=prompt, answer_text="",
                model_name=model, latency_ms=int((time.time() - start) * 1000),
                error=error_str, error_code=code, error_message=error_str[:500],
                retryable=retry,
            )
