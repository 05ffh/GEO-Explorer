"""Kimi (Moonshot) adapter — kimi-k2.5 原生支持 $web_search 联网搜索。

$web_search 是 Kimi 内置函数：模型自己发起搜索并阅读网页，调用方只需
把 tool_call 的 arguments 原样回传，模型会自行完成搜索并生成最终回答。
这测的是 AI 真实的联网认知，不是"先搜再喂"的操控。
"""

import time

from src.adapters.base import OpenAICompatibleAdapter, AIResponse
from src.config import settings


class KimiAdapter(OpenAICompatibleAdapter):
    platform_name = "kimi"
    base_url = settings.kimi_base_url
    default_model = settings.kimi_model
    api_key = settings.kimi_api_key
    default_temperature = 0.6
    # kimi-k2.5 原生支持 $web_search，默认开启联网搜索
    default_search_enabled = True

    async def query(self, prompt: str, system_prompt: str = "", **kwargs) -> AIResponse:
        search_enabled = kwargs.get("search_enabled", self.default_search_enabled)
        if not search_enabled:
            return await super().query(prompt, system_prompt, **kwargs)

        start = time.time()
        model = kwargs.get("model", self.default_model)
        try:
            messages = [
                {"role": "system", "content": system_prompt or "你是一个诚实的AI助手。"},
                {"role": "user", "content": prompt},
            ]
            tools = [{"type": "builtin_function", "function": {"name": "$web_search"}}]

            choice = None
            # 最多 3 轮（第 1 轮 tool_calls → 第 2 轮 stop），防死循环
            for _ in range(3):
                response = await self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=tools,
                    temperature=kwargs.get("temperature", self.default_temperature),
                    max_tokens=kwargs.get("max_tokens", 2048),
                    # kimi-k2.5/k2.6 联网搜索时建议禁用 thinking
                    extra_body={"thinking": {"type": "disabled"}},
                )
                choice = response.choices[0]
                if choice.finish_reason != "tool_calls":
                    break

                messages.append(choice.message)
                for tool_call in choice.message.tool_calls:
                    if tool_call.function.name == "$web_search":
                        # 原样回传 arguments，Kimi 模型自己执行搜索
                        result = tool_call.function.arguments
                    else:
                        result = '{"error": "unknown tool"}'
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_call.function.name,
                        "content": result,
                    })

            latency = int((time.time() - start) * 1000)
            msg = choice.message if choice else None
            content = (msg.content or "").strip() if msg else ""
            reasoning = (getattr(msg, "reasoning_content", "") or "").strip() if msg else ""

            if content:
                answer, source, fallback = content, "content", False
            elif reasoning:
                answer, source, fallback = reasoning, "reasoning_content", True
            else:
                answer, source, fallback = "", "empty", False

            return AIResponse(
                platform=self.platform_name, question=prompt, answer_text=answer,
                answer_source=source, reasoning_fallback=fallback,
                error_code=None if answer else "platform_empty_response",
                citations=await self.extract_citations(answer),
                model_name=model, model_version=getattr(response, "model", "") or "",
                raw_response=response.model_dump(), latency_ms=latency,
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
