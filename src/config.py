from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")
    app_env: str = "development"
    secret_key: str = "change-me"
    database_url: str = "postgresql+asyncpg://geo:geo@localhost:5432/geo_explorer"
    test_database_url: str = "postgresql+asyncpg://geo_test:geo_test@localhost:5433/geo_explorer_test"
    redis_url: str = "redis://localhost:6379/0"

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"

    kimi_api_key: str = ""
    kimi_base_url: str = "https://api.moonshot.cn/v1"
    kimi_model: str = "kimi-k2.5"

    doubao_api_key: str = ""
    doubao_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    doubao_model: str = "doubao-seed-2-0-lite-260215"

    wenxin_api_key: str = ""
    wenxin_secret_key: str = ""
    wenxin_base_url: str = "https://aip.baidubce.com"
    wenxin_model: str = "ernie-4.0-turbo-128k"

    collector_concurrency: int = 4
    collector_timeout: int = 30
    collector_max_retries: int = 2

    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440


settings = Settings()
