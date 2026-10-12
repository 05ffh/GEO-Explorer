"""Mock platform adapter — 8 modes for validating engine logic without real API calls.

Modes: success, rate_limited, timeout, auth_failed, quota_exhausted,
       empty_response, parse_failed, mixed

Returns real AIResponse data structures matching OpenAICompatibleAdapter.
"""

import asyncio
import random
from src.adapters.base import PlatformAdapter, AIResponse, Citation


class MockPlatformAdapter(PlatformAdapter):
    """Mock adapter for testing collector engine without consuming real API quota.

    Usage:
        adapter = MockPlatformAdapter(platform="deepseek", mode="success")
        adapter = MockPlatformAdapter(platform="kimi", mode="rate_limited")
        adapter = MockPlatformAdapter(platform="doubao", mode="mixed")
    """

    platform_name: str = "mock"
    default_model: str = "mock-v1"

    def __init__(self, platform: str = "mock", mode: str = "success",
                 latency_range: tuple[int, int] = (10, 50)):
        super().__init__()
        self.platform_name = platform
        self.mode = mode
        self.latency_range = latency_range
        self._call_count = 0

    def _pick_mode(self) -> str:
        self._call_count += 1
        r = random.random()
        if r < 0.35:
            return "success"
        elif r < 0.45:
            return "rate_limited"
        elif r < 0.55:
            return "timeout"
        elif r < 0.62:
            return "empty_response"
        elif r < 0.69:
            return "auth_failed"
        elif r < 0.76:
            return "network_error"
        else:
            return random.choice(["quota_exhausted", "parse_failed"])

    def _get_mode(self) -> str:
        return self._pick_mode() if self.mode == "mixed" else self.mode

    async def query(self, prompt: str, system_prompt: str = "", **kwargs) -> AIResponse:
        mode = self._get_mode()
        latency = random.randint(*self.latency_range)
        model = kwargs.get("model", self.default_model)
        await asyncio.sleep(latency / 1000.0)

        if mode == "success":
            return AIResponse(
                platform=self.platform_name, question=prompt,
                answer_text=f"[MOCK {self.platform_name}] {prompt[:60]}",
                citations=[Citation(url=f"https://mock.{self.platform_name}.com/1",
                                    type="official", context="mock context")],
                model_name=model, model_version="mock-v1.0",
                raw_response={"mock": True, "mode": "success"},
                latency_ms=latency, error_code=None,
            )

        if mode == "rate_limited":
            return AIResponse(
                platform=self.platform_name, question=prompt, answer_text="",
                model_name=model, latency_ms=latency,
                error="[MOCK] 429 Too Many Requests",
                error_code="platform_rate_limited",
                error_message="Rate limit exceeded", retryable=True,
            )

        if mode == "timeout":
            return AIResponse(
                platform=self.platform_name, question=prompt, answer_text="",
                model_name=model, latency_ms=latency * 5,
                error="[MOCK] Request timed out",
                error_code="platform_timeout",
                error_message="Connection timeout", retryable=True,
            )

        if mode == "auth_failed":
            return AIResponse(
                platform=self.platform_name, question=prompt, answer_text="",
                model_name=model, latency_ms=latency,
                error="[MOCK] 401 Unauthorized",
                error_code="platform_auth_failed",
                error_message="Invalid API key", retryable=False,
            )

        if mode == "quota_exhausted":
            return AIResponse(
                platform=self.platform_name, question=prompt, answer_text="",
                model_name=model, latency_ms=latency,
                error="[MOCK] Quota exhausted",
                error_code="platform_quota_exhausted",
                error_message="Daily quota exhausted", retryable=False,
            )

        if mode == "empty_response":
            return AIResponse(
                platform=self.platform_name, question=prompt, answer_text="",
                model_name=model, latency_ms=latency,
                error="[MOCK] Empty response",
                error_code="platform_empty_response",
                error_message="Content filtered", retryable=False,
            )

        if mode == "network_error":
            return AIResponse(
                platform=self.platform_name, question=prompt, answer_text="",
                model_name=model, latency_ms=latency,
                error="[MOCK] Network connection error",
                error_code="platform_network_error",
                error_message="Network connection failed", retryable=True,
            )

        if mode == "parse_failed":
            return AIResponse(
                platform=self.platform_name, question=prompt, answer_text="",
                model_name=model, latency_ms=latency,
                error="[MOCK] JSON parse error",
                error_code="platform_parse_failed",
                error_message="Failed to parse response", retryable=False,
            )

        return AIResponse(
            platform=self.platform_name, question=prompt, answer_text="",
            model_name=model, latency_ms=latency,
            error=f"[MOCK] Unknown mode: {mode}",
            error_code="platform_unknown_error",
            error_message=f"Unknown mock mode: {mode}", retryable=False,
        )

    async def extract_citations(self, response: str) -> list[Citation]:
        return [Citation(url="https://mock.example.com", type="official", context=response[:100])]


# Backward compat alias — accepts platform_name= kwarg
class _MockAdapterCompat(MockPlatformAdapter):
    def __init__(self, platform_name: str = "mock", **kwargs):
        super().__init__(platform=platform_name, **kwargs)

MockAdapter = _MockAdapterCompat
