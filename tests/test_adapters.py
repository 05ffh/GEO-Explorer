import pytest
from src.adapters import (
    DeepSeekAdapter, KimiAdapter, DoubaoAdapter, WenxinAdapter,
    MockAdapter, get_adapter, AIResponse,
)


def test_deepseek_platform_name():
    adapter = DeepSeekAdapter()
    assert adapter.platform_name == "deepseek"


def test_kimi_platform_name():
    adapter = KimiAdapter()
    assert adapter.platform_name == "kimi"


def test_kimi_not_inherit_deepseek():
    """Kimi must inherit OpenAICompatibleAdapter directly, not DeepSeek."""
    from src.adapters.base import OpenAICompatibleAdapter
    assert issubclass(KimiAdapter, OpenAICompatibleAdapter)
    assert not issubclass(KimiAdapter, DeepSeekAdapter)


def test_doubao_platform_name():
    adapter = DoubaoAdapter()
    assert adapter.platform_name == "doubao"


def test_wenxin_platform_name():
    adapter = WenxinAdapter()
    assert adapter.platform_name == "wenxin"


@pytest.mark.asyncio
async def test_mock_adapter_query():
    adapter = MockAdapter(platform_name="deepseek")
    result = await adapter.query("什么是TestBrand？")
    assert result.platform == "deepseek"
    assert "TestBrand" in result.answer_text
    assert result.model_name == "mock-deepseek-v1"
    assert result.latency_ms == 50
    assert result.error is None


@pytest.mark.asyncio
async def test_mock_adapter_unknown_platform():
    adapter = MockAdapter(platform_name="unknown")
    result = await adapter.query("test")
    assert result.platform == "unknown"
    assert result.error is None


def test_get_adapter_returns_correct_type():
    deepseek = get_adapter("deepseek")
    assert isinstance(deepseek, DeepSeekAdapter)

    kimi = get_adapter("kimi")
    assert isinstance(kimi, KimiAdapter)


def test_ai_response_dataclass():
    resp = AIResponse(platform="test", question="q", answer_text="a")
    assert resp.platform == "test"
    assert resp.citations == []
    assert resp.error is None
