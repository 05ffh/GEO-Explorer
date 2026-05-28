import re
import time
import httpx
from src.adapters.base import PlatformAdapter, AIResponse, Citation
from src.config import settings


class WenxinAdapter(PlatformAdapter):
    platform_name = "wenxin"

    def __init__(self):
        self.api_key = settings.wenxin_api_key
        self.secret_key = settings.wenxin_secret_key
        self._access_token = None
        self._token_expiry = 0

    async def _get_access_token(self) -> str:
        now = time.time()
        if self._access_token and now < self._token_expiry:
            return self._access_token
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{settings.wenxin_base_url}/oauth/2.0/token",
                params={
                    "grant_type": "client_credentials",
                    "client_id": self.api_key,
                    "client_secret": self.secret_key,
                },
            )
            data = resp.json()
            self._access_token = data["access_token"]
            self._token_expiry = now + data.get("expires_in", 2592000) - 300
            return self._access_token

    async def query(self, prompt: str, system_prompt: str = "", **kwargs) -> AIResponse:
        start = time.time()
        model = kwargs.get("model", settings.wenxin_model)
        try:
            token = await self._get_access_token()
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{settings.wenxin_base_url}/rpc/2.0/ai_custom/v1/wenxinworkshop/"
                    f"chat/completions_pro?access_token={token}",
                    json={
                        "messages": [
                            {"role": "system", "content": system_prompt or "你是一个诚实的AI助手。"},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": kwargs.get("temperature", 0.3),
                        "max_output_tokens": kwargs.get("max_tokens", 2048),
                    },
                    timeout=settings.collector_timeout,
                )
                data = resp.json()
                latency = int((time.time() - start) * 1000)
                answer = data.get("result", "")
                return AIResponse(
                    platform=self.platform_name, question=prompt, answer_text=answer,
                    citations=await self.extract_citations(answer),
                    model_name=model, raw_response=data, latency_ms=latency,
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
