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

        # Auto-detect auth mode from key format
        self._mode: str = self._detect_mode()
        self._base_url: str = self._resolve_base_url()
        self._model: str = settings.wenxin_model

        # Legacy OAuth state
        self._access_token: str | None = None
        self._token_expiry: float = 0.0

    def _detect_mode(self) -> str:
        """qianfan_v2_bearer if API Key starts with bce-v3/ALTAK-; otherwise legacy_oauth."""
        if self.api_key.startswith("bce-v3/ALTAK-"):
            return "qianfan_v2_bearer"
        return "legacy_oauth"

    def _resolve_base_url(self) -> str:
        if self._mode == "qianfan_v2_bearer":
            return settings.wenxin_base_url_v2 or "https://qianfan.baidubce.com/v2"
        return settings.wenxin_base_url or "https://aip.baidubce.com"

    async def _get_access_token(self) -> str:
        """Obtain OAuth access token (legacy_oauth mode only)."""
        if self._mode != "legacy_oauth":
            raise RuntimeError(
                f"Wenxin is in {self._mode} mode — OAuth token not applicable. "
                f"Bear token (API Key) is used directly in Authorization header."
            )
        now = time.time()
        if self._access_token and now < self._token_expiry:
            return self._access_token
        if not self.secret_key:
            raise RuntimeError(
                "Wenxin legacy_oauth mode requires both API Key and Secret Key. "
                "If you have a bce-v3/ALTAK- key, set WENXIN_API_STYLE=qianfan_v2_bearer "
                "or ensure the key starts with bce-v3/ALTAK- for auto-detection."
            )
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
            if "error" in data:
                err = data.get("error", "")
                desc = data.get("error_description", "")
                if "invalid_client" in err:
                    if self.api_key.startswith("bce-v3"):
                        raise RuntimeError(
                            f"Wenxin OAuth rejected bce-v3 key as invalid_client. "
                            f"This key format requires qianfan_v2_bearer mode (Bearer auth). "
                            f"Ensure the key starts with 'bce-v3/ALTAK-' for auto-detection. "
                            f"Error: {err} — {desc}"
                        )
                    raise RuntimeError(
                        f"Wenxin OAuth failed: {err} — {desc}. "
                        f"Key may be expired or Secret Key mismatch."
                    )
                raise RuntimeError(f"Wenxin OAuth error: {err} — {desc}")
            if "access_token" not in data:
                raise RuntimeError(f"Wenxin OAuth token missing: {str(data)[:200]}")
            self._access_token = data["access_token"]
            self._token_expiry = now + data.get("expires_in", 2592000) - 300
            return self._access_token

    async def query(self, prompt: str, system_prompt: str = "", **kwargs) -> AIResponse:
        start = time.time()
        model = kwargs.get("model", self._model)
        try:
            if self._mode == "qianfan_v2_bearer":
                return await self._query_qianfan_v2(prompt, system_prompt, model, start)
            else:
                return await self._query_legacy(prompt, system_prompt, model, start)
        except Exception as e:
            error_str = str(e)
            error_code = "platform_unknown_error"
            if "invalid_client" in error_str or "auth_mode_error" in error_str.lower():
                error_code = "auth_mode_error"
            elif "401" in error_str or "403" in error_str or "auth" in error_str.lower() or "unauthorized" in error_str.lower():
                error_code = "platform_auth_failed"
            elif "429" in error_str or "rate_limit" in error_str.lower():
                error_code = "platform_rate_limited"
            elif "quota" in error_str.lower():
                error_code = "platform_quota_exhausted"
            elif "model" in error_str.lower() and ("not found" in error_str.lower() or "not enabled" in error_str.lower()):
                error_code = "model_not_enabled"

            return AIResponse(
                platform=self.platform_name, question=prompt, answer_text="",
                model_name=model, latency_ms=int((time.time() - start) * 1000),
                error=error_str, error_code=error_code, error_message=error_str[:500],
                retryable=error_code in ("platform_rate_limited",),
            )

    async def _query_qianfan_v2(self, prompt: str, system_prompt: str, model: str, start: float) -> AIResponse:
        """Call Qianfan ModelBuilder v2 API with Bearer token."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt or "你是一个诚实的AI助手。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_output_tokens": 2048,
        }

        timeout = httpx.Timeout(settings.collector_query_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{self._base_url}/chat/completions",
                json=body,
                headers=headers,
            )
            data = resp.json()
            latency = int((time.time() - start) * 1000)

            # Check for API-level errors
            if "error" in data:
                err = data["error"]
                err_code = err.get("code", "")
                err_msg = err.get("message", str(err))
                error_code = "platform_unknown_error"
                if "invalid_client" in err_code.lower() or "authentication" in err_code.lower():
                    error_code = "platform_auth_failed"
                elif "rate" in err_code.lower() or "429" in err_code.lower():
                    error_code = "platform_rate_limited"
                elif "quota" in err_code.lower():
                    error_code = "platform_quota_exhausted"
                elif "model" in err_code.lower():
                    error_code = "model_not_enabled"
                raise RuntimeError(f"[{error_code}] {err_code}: {err_msg}")

            # Extract answer
            choices = data.get("choices", [])
            if not choices:
                raise RuntimeError("platform_empty_response — no choices in response")
            message = choices[0].get("message", {})
            answer = (message.get("content") or "").strip()

            if not answer:
                reasoning = (message.get("reasoning_content") or "").strip()
                answer = reasoning

            usage = data.get("usage", {})
            return AIResponse(
                platform=self.platform_name, question=prompt, answer_text=answer,
                citations=await self.extract_citations(answer),
                model_name=model, raw_response=data, latency_ms=latency,
                error_code=None if answer else "empty_response",
            )

    async def _query_legacy(self, prompt: str, system_prompt: str, model: str, start: float) -> AIResponse:
        """Legacy OAuth-based Wenxin API call."""
        token = await self._get_access_token()
        timeout = httpx.Timeout(settings.collector_query_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{settings.wenxin_base_url}/rpc/2.0/ai_custom/v1/wenxinworkshop/"
                f"chat/completions_pro?access_token={token}",
                json={
                    "messages": [
                        {"role": "system", "content": system_prompt or "你是一个诚实的AI助手。"},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_output_tokens": 2048,
                },
            )
            data = resp.json()
            latency = int((time.time() - start) * 1000)
            if "error_msg" in data:
                raise RuntimeError(f"Wenxin API error: {data.get('error_msg', '')[:200]}")
            answer = data.get("result", "")
            if not answer:
                raise RuntimeError("Wenxin returned empty result")
            return AIResponse(
                platform=self.platform_name, question=prompt, answer_text=answer,
                citations=await self.extract_citations(answer),
                model_name=model, raw_response=data, latency_ms=latency,
            )

    async def extract_citations(self, response: str) -> list[Citation]:
        citations = []
        for match in re.finditer(r'https?://[^\s\)\]】]+', response):
            url = match.group()
            ctx = response[max(0, match.start() - 50):min(len(response), match.end() + 50)]
            citations.append(Citation(url=url, type="third_party", context=ctx))
        return citations
