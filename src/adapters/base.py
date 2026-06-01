import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from openai import AsyncOpenAI


@dataclass
class Citation:
    url: str
    type: str       # official | third_party | wiki
    context: str


@dataclass
class AIResponse:
    platform: str
    question: str
    answer_text: str
    citations: list[Citation] = field(default_factory=list)
    model_name: str = ""
    model_version: str = ""
    raw_response: dict | None = None
    latency_ms: int = 0
    error: str | None = None           # Deprecated — use error_code + error_message
    error_code: str | None = None      # CollectorErrorCode value
    error_message: str | None = None
    retryable: bool = False
    answer_source: str = "content"     # "content" | "reasoning_content" | "empty"
    reasoning_fallback: bool = False   # True when answer came from reasoning_content


class PlatformAdapter(ABC):
    @abstractmethod
    async def query(self, prompt: str, system_prompt: str = "", **kwargs) -> AIResponse:
        ...

    @abstractmethod
    async def extract_citations(self, response: str) -> list[Citation]:
        ...


class OpenAICompatibleAdapter(PlatformAdapter):
    platform_name: str = ""
    base_url: str = ""
    default_model: str = ""
    api_key: str = ""
    default_temperature: float = 0.3

    def __init__(self):
        self._client = None

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            import httpx
            from src.config import settings
            self._client = AsyncOpenAI(
                api_key=self.api_key, base_url=self.base_url,
                max_retries=settings.collector_sdk_max_retries,
                timeout=httpx.Timeout(settings.collector_query_timeout_seconds, connect=10.0),
            )
        return self._client

    async def query(self, prompt: str, system_prompt: str = "", **kwargs) -> AIResponse:
        start = time.time()
        model = kwargs.get("model", self.default_model)
        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt or "你是一个诚实的AI助手。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=kwargs.get("temperature", self.default_temperature),
                max_tokens=kwargs.get("max_tokens", 2048),
            )
            latency = int((time.time() - start) * 1000)
            msg = response.choices[0].message
            content = (msg.content or "").strip()
            reasoning = (msg.reasoning_content or "").strip()
            if content:
                answer = content
                source = "content"
                fallback = False
            elif reasoning:
                answer = reasoning
                source = "reasoning_content"
                fallback = True
            else:
                answer = ""
                source = "empty"
                fallback = False
            return AIResponse(
                platform=self.platform_name,
                question=prompt,
                answer_text=answer,
                answer_source=source,
                reasoning_fallback=fallback,
                error_code=None if answer else "empty_response",
                citations=await self.extract_citations(answer),
                model_name=model,
                model_version=response.model or "",
                raw_response=response.model_dump(),
                latency_ms=latency,
            )
        except Exception as e:
            from src.collector.error_codes import CollectorErrorCode
            error_str = str(e)
            # Map to standard error codes
            if "429" in error_str or "rate_limit" in error_str.lower() or "RateLimitError" in type(e).__name__:
                code = CollectorErrorCode.RATE_LIMIT.value; retry = True
            elif "timeout" in error_str.lower() or "Timeout" in type(e).__name__:
                code = CollectorErrorCode.TIMEOUT.value; retry = True
            elif "401" in error_str or "403" in error_str or "auth" in error_str.lower() or "AuthenticationError" in type(e).__name__:
                code = CollectorErrorCode.AUTH_ERROR.value; retry = False
            elif "5" in error_str[:3] if len(error_str) > 3 else False:
                code = CollectorErrorCode.SERVER_ERROR.value; retry = True
            elif "connection" in error_str.lower() or "network" in error_str.lower():
                code = CollectorErrorCode.NETWORK_ERROR.value; retry = True
            else:
                code = CollectorErrorCode.UNKNOWN_ERROR.value; retry = False
            return AIResponse(
                platform=self.platform_name, question=prompt, answer_text="",
                model_name=model, latency_ms=int((time.time() - start) * 1000),
                error=error_str, error_code=code, error_message=error_str[:500], retryable=retry,
            )

    async def extract_citations(self, response: str) -> list[Citation]:
        citations = []
        for match in re.finditer(r'https?://[^\s\)\]】]+', response):
            url = match.group()
            ctx_start = max(0, match.start() - 50)
            ctx_end = min(len(response), match.end() + 50)
            ctx = response[ctx_start:ctx_end]
            citations.append(Citation(url=url, type="third_party", context=ctx))
        return citations
