import re
import time
from src.adapters.base import PlatformAdapter, AIResponse, Citation
from src.config import settings


class DoubaoAdapter(PlatformAdapter):
    platform_name = "doubao"

    def __init__(self):
        try:
            from volcenginesdkarkruntime import Ark
            self.client = Ark(
                base_url=settings.doubao_base_url,
                api_key=settings.doubao_api_key,
            )
        except ImportError:
            self.client = None

    async def query(self, prompt: str, system_prompt: str = "", **kwargs) -> AIResponse:
        start = time.time()
        model = kwargs.get("model", settings.doubao_model)
        if self.client is None:
            return AIResponse(
                platform=self.platform_name, question=prompt, answer_text="",
                model_name=model, error="volcenginesdkarkruntime not installed",
            )
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt or "你是一个诚实的AI助手。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=kwargs.get("temperature", 0.3),
                max_tokens=kwargs.get("max_tokens", 2048),
            )
            latency = int((time.time() - start) * 1000)
            answer = response.choices[0].message.content or ""
            return AIResponse(
                platform=self.platform_name, question=prompt, answer_text=answer,
                citations=await self.extract_citations(answer),
                model_name=model, latency_ms=latency,
                raw_response={"model": model, "choices": [{"message": {"content": answer}}]},
            )
        except Exception as e:
            return AIResponse(
                platform=self.platform_name, question=prompt, answer_text="",
                model_name=model,
                latency_ms=int((time.time() - start) * 1000),
                error=str(e),
            )

    async def extract_citations(self, response: str) -> list[Citation]:
        citations = []
        for match in re.finditer(r'https?://[^\s\)\]】]+', response):
            url = match.group()
            ctx = response[max(0, match.start() - 50):min(len(response), match.end() + 50)]
            citations.append(Citation(url=url, type="third_party", context=ctx))
        return citations
