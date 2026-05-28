from src.adapters.base import OpenAICompatibleAdapter
from src.config import settings


class DoubaoAdapter(OpenAICompatibleAdapter):
    platform_name = "doubao"
    base_url = settings.doubao_base_url
    default_model = settings.doubao_model
    api_key = settings.doubao_api_key
