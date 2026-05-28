from src.adapters.base import OpenAICompatibleAdapter
from src.config import settings


class KimiAdapter(OpenAICompatibleAdapter):
    platform_name = "kimi"
    base_url = settings.kimi_base_url
    default_model = settings.kimi_model
    api_key = settings.kimi_api_key
    default_temperature = 1.0
