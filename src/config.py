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

    # --- 分析触发阈值 ---
    min_success_platforms_for_analysis: int = 2
    min_success_queries_for_analysis: int = 10

    # --- 平台级并发 ---
    platform_concurrency_limits: dict = {
        "kimi": 2,
        "deepseek": 4,
        "doubao": 4,
        "wenxin": 2,
    }

    # --- 平台级重试 ---
    platform_retry_config: dict = {
        "kimi": {"max_retries": 2, "backoff_seconds": [2, 4]},
        "deepseek": {"max_retries": 2, "backoff_seconds": [1, 2]},
        "doubao": {"max_retries": 2, "backoff_seconds": [1, 2]},
        "wenxin": {"max_retries": 2, "backoff_seconds": [2, 4]},
    }

    # --- 搜索配置 ---
    google_search_api_key: str = ""
    google_search_cx: str = ""
    brave_search_api_key: str = ""

    # --- Action 触发阈值 ---
    action_thresholds: dict = {
        "citation_rate": 0.05,
        "accuracy_rate": 0.60,
        "completeness_rate": 0.50,
        "first_rec_rate": 0.10,
        "differentiation_rate": 0.30,
        "scenario_recall_rate": 0.20,
    }

    # --- GT 必填字段 ---
    gt_required_fields: list = [
        "official_name", "aliases", "industry", "category",
        "positioning", "core_products", "target_users",
        "core_scenarios", "key_differentiators",
        "official_domains", "source_of_truth_by_field",
    ]

    # --- GT 高风险字段 ---
    gt_high_risk_fields: list = [
        "official_name", "category", "positioning",
        "target_competitors", "forbidden_claims",
        "proof_points", "pricing", "certifications",
        "customers", "awards", "funding", "legal_sensitive_claims",
    ]

    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440


settings = Settings()
