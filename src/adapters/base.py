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
    error: str | None = None


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
            self._client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
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
            answer = response.choices[0].message.content or ""
            return AIResponse(
                platform=self.platform_name,
                question=prompt,
                answer_text=answer,
                citations=await self.extract_citations(answer),
                model_name=model,
                model_version=response.model or "",
                raw_response=response.model_dump(),
                latency_ms=latency,
            )
        except Exception as e:
            return AIResponse(
                platform=self.platform_name,
                question=prompt,
                answer_text="",
                model_name=model,
                latency_ms=int((time.time() - start) * 1000),
                error=str(e),
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
