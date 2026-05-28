from src.adapters.base import OpenAICompatibleAdapter
from src.config import settings


class DeepSeekAdapter(OpenAICompatibleAdapter):
    platform_name = "deepseek"
    base_url = settings.deepseek_base_url
    default_model = settings.deepseek_model
    api_key = settings.deepseek_api_key
