"""DeepSeek adapter — deepseek-v4 原生支持 Responses API 服务端联网搜索。

联网搜索由 DeepSeek 服务器托管执行，只需 API Key，无需第三方搜索密钥。
走 Responses API（/v1/responses），tools=[{"type": "web_search"}]。
"""

import time

from src.adapters.base import OpenAICompatibleAdapter, AIResponse
from src.config import settings


class DeepSeekAdapter(OpenAICompatibleAdapter):
    platform_name = "deepseek"
    base_url = settings.deepseek_base_url
    default_model = settings.deepseek_model
    api_key = settings.deepseek_api_key
    # deepseek-v4 支持 Responses API web_search，默认联网
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
            # ponytail: DeepSeek web_search 融合结果但不返回引用 URL（annotations 恒为空），
            # 只能从回答文本里提取内嵌 URL（通常也没有）。引用溯源留待平台开放后再补。
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
