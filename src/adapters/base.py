import re
import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from openai import AsyncOpenAI
import httpx

logger = logging.getLogger(__name__)


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
    error: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False
    answer_source: str = "content"
    reasoning_fallback: bool = False


class PlatformAdapter(ABC):
    @abstractmethod
    async def query(self, prompt: str, system_prompt: str = "", **kwargs) -> AIResponse:
        ...

    @abstractmethod
    async def extract_citations(self, response: str) -> list[Citation]:
        ...


# ── HTTP client factory (fork-safe: no global state at import time) ──────────
# P0 fix: Celery prefork causes fork() — child processes MUST NOT inherit
# parent's httpx connection pool (sockets/SSL/event loop break after fork).
# Solution: lazy per-process caching via os.getpid() key, never at import time.

import os as _os

_PER_PROCESS_HTTP_CLIENTS: dict[int, httpx.AsyncClient] = {}
_PER_PROCESS_OPENAI_CLIENTS: dict[str, AsyncOpenAI] = {}


def _create_http_client() -> httpx.AsyncClient:
    """Create a NEW httpx.AsyncClient. Cached per OS process (fork-safe)."""
    pid = _os.getpid()
    if pid not in _PER_PROCESS_HTTP_CLIENTS:
        _PER_PROCESS_HTTP_CLIENTS[pid] = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=20.0,
                read=90.0,
                write=20.0,
                pool=20.0,
            ),
            limits=httpx.Limits(
                max_connections=20,
                max_keepalive_connections=10,
            ),
        )
    return _PER_PROCESS_HTTP_CLIENTS[pid]


def _create_openai_client(api_key: str, base_url: str) -> AsyncOpenAI:
    """Create an AsyncOpenAI client. Cached per (process, key, url) — fork-safe."""
    pid = _os.getpid()
    cache_key = f"{pid}:{api_key[:20]}@{base_url}"
    if cache_key not in _PER_PROCESS_OPENAI_CLIENTS:
        _PER_PROCESS_OPENAI_CLIENTS[cache_key] = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            max_retries=0,
            http_client=_create_http_client(),
        )
    return _PER_PROCESS_OPENAI_CLIENTS[cache_key]


def _close_process_clients() -> None:
    """Close all HTTP clients for the current process (worker shutdown hook)."""
    pid = _os.getpid()
    for key in list(_PER_PROCESS_OPENAI_CLIENTS.keys()):
        if str(pid) in key:
            _PER_PROCESS_OPENAI_CLIENTS.pop(key, None)
    client = _PER_PROCESS_HTTP_CLIENTS.pop(pid, None)
    if client:
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(client.aclose())
        except Exception:
            pass


class OpenAICompatibleAdapter(PlatformAdapter):
    platform_name: str = ""
    base_url: str = ""
    default_model: str = ""
    api_key: str = ""
    default_temperature: float = 0.3

    @property
    def client(self) -> AsyncOpenAI:
        return _create_openai_client(self.api_key, self.base_url)

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
                extra_headers=kwargs.get("extra_headers"),
            )
            latency = int((time.time() - start) * 1000)
            msg = response.choices[0].message
            content = (msg.content or "").strip()
            reasoning = (msg.reasoning_content or "").strip()
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
                model_name=model, model_version=response.model or "",
                raw_response=response.model_dump(), latency_ms=latency,
            )
        except Exception as e:
            error_str = str(e)
            error_type = type(e).__name__
            code, retry = self._classify_error(error_str, error_type, e)
            return AIResponse(
                platform=self.platform_name, question=prompt, answer_text="",
                model_name=model, latency_ms=int((time.time() - start) * 1000),
                error=error_str, error_code=code, error_message=error_str[:500],
                retryable=retry,
            )

    def _classify_error(self, error_str: str, error_type: str, exc: Exception) -> tuple[str, bool]:
        """Classify platform errors. Returns (error_code, retryable)."""
        error_lower = error_str.lower()

        if "429" in error_str or "rate_limit" in error_lower or "RateLimitError" in error_type:
            return "platform_rate_limited", True
        if "timeout" in error_lower or "Timeout" in error_type or "timed out" in error_lower:
            return "platform_timeout", True
        if "401" in error_str or "403" in error_str or "auth" in error_lower or "AuthenticationError" in error_type:
            return "platform_auth_failed", False
        if "quota" in error_lower or "exhausted" in error_lower:
            return "platform_quota_exhausted", False
        if "empty" in error_lower or "content_filter" in error_lower:
            return "platform_empty_response", False
        if "connection" in error_lower or "network" in error_lower or "ConnectError" in error_type:
            return "platform_network_error", True
        if "5" in error_str[:3] if len(error_str) > 3 else False:
            return "server_error", True
        if "parse" in error_lower or "json" in error_lower:
            return "platform_parse_failed", False
        return "platform_unknown_error", False

    async def extract_citations(self, response: str) -> list[Citation]:
        citations = []
        for match in re.finditer(r'https?://[^\s\)\]】]+', response):
            url = match.group()
            ctx_start = max(0, match.start() - 50)
            ctx_end = min(len(response), match.end() + 50)
            ctx = response[ctx_start:ctx_end]
            citations.append(Citation(url=url, type="third_party", context=ctx))
        return citations
