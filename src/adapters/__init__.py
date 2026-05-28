from src.adapters.base import PlatformAdapter, OpenAICompatibleAdapter, AIResponse, Citation
from src.adapters.deepseek import DeepSeekAdapter
from src.adapters.kimi import KimiAdapter
from src.adapters.doubao import DoubaoAdapter
from src.adapters.wenxin import WenxinAdapter
from src.adapters.mock import MockAdapter, MOCK_RESPONSES

ADAPTERS = {
    "deepseek": DeepSeekAdapter,
    "kimi": KimiAdapter,
    "doubao": DoubaoAdapter,
    "wenxin": WenxinAdapter,
}


def get_adapter(platform: str) -> PlatformAdapter:
    return ADAPTERS[platform]()


__all__ = [
    "PlatformAdapter", "OpenAICompatibleAdapter", "AIResponse", "Citation",
    "DeepSeekAdapter", "KimiAdapter", "DoubaoAdapter", "WenxinAdapter",
    "MockAdapter", "MOCK_RESPONSES", "ADAPTERS", "get_adapter",
]
