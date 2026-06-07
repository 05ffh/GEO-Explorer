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
    wenxin_base_url_v2: str = "https://qianfan.baidubce.com/v2"
    wenxin_model: str = "ernie-4.0-turbo-128k"

    # ── Test gates ───────────────────────────────────────────────────────
    collection_test_mode: str = "mock"     # "mock" | "real" — default mock for dev/CI
    enable_real_platform_tests: bool = False  # Default OFF — gate real API tests
    real_platform_test_mode: str = "single_platform_single_template"  # default minimal
    mock_platform_scenario: str = "all_success"  # default mock scenario

    # ── Collector v2 ──────────────────────────────────────────────────────────
    collector_platforms: list[str] = ["deepseek", "kimi", "doubao", "wenxin"]
    collector_platform_order: list[str] = ["deepseek", "kimi", "doubao", "wenxin"]

    # ── Global concurrency (WSL2-safe defaults) ──────────────────────────────
    global_max_concurrency: int = 6              # Global semaphore: max total concurrent HTTP requests

    # Per-platform concurrency (WSL2 dev: reduce to 2 each)
    collector_platform_concurrency: int = 2      # Dev default — production override to platform_rate_limits values

    collector_max_retries: int = 1               # Engine-level retries (SDK retries=0)
    collector_query_timeout_seconds: int = 60    # Single query timeout (asyncio.wait_for)
    collector_sdk_max_retries: int = 0           # SDK built-in retries disabled
    collector_max_requests_per_run: int = 200    # Hard budget: total HTTP calls
    collector_max_duration_seconds: int = 1200   # Raised for slow platforms (Kimi/Doubao)
    collector_max_failures_before_abort: int = 50  # Hard budget: failures
    analysis_min_coverage_ratio: float = 0.6     # Min coverage to trigger analysis
    collector_v2_enabled: bool = False           # Feature flag for v2 engine

    # --- 分析触发阈值 ---
    min_success_platforms_for_analysis: int = 2
    min_success_queries_for_analysis: int = 10

    # --- 平台级限流 (v2 RateLimiter) ---
    # Conservative initial settings per 2026-06-07 human review.
    # Kimi:   RPM 200 actual → start at 60.   TPM 2M → start at 800K.
    # Doubao: RPM 30K actual → start at 300.  TPM 5M → start at 1.5M.
    # Ramp up every 24h based on actual 429 rate.
    # WSL2 dev defaults (production: use higher values in .env or deploy config)
    platform_rate_limits: dict = {
        "deepseek": {
            "max_concurrent": 2, "min_interval_seconds": 0.1,
            "max_requests_per_minute": None, "max_tokens_per_minute": None,
            "cooldown_on_429_seconds": 300, "consecutive_429_threshold": 3,
            "max_retries": 2, "retry_after_respected": True,
            "backoff_base_seconds": 15, "backoff_max_seconds": 300,
        },
        "kimi": {
            "max_concurrent": 2, "min_interval_seconds": 0.3,
            "max_requests_per_minute": 60, "max_tokens_per_minute": 800000,
            "cooldown_on_429_seconds": 300, "consecutive_429_threshold": 3,
            "max_retries": 3, "retry_after_respected": True,
            "backoff_base_seconds": 30, "backoff_max_seconds": 900,
        },
        "doubao": {
            "max_concurrent": 2, "min_interval_seconds": 0.2,
            "max_requests_per_minute": 300, "max_tokens_per_minute": 1500000,
            "cooldown_on_429_seconds": 300, "consecutive_429_threshold": 3,
            "max_retries": 3, "retry_after_respected": True,
            "backoff_base_seconds": 30, "backoff_max_seconds": 900,
        },
        "wenxin": {
            "max_concurrent": 2, "min_interval_seconds": 0.5,
            "max_requests_per_minute": 30, "max_tokens_per_minute": 500000,
            "cooldown_on_429_seconds": 300, "consecutive_429_threshold": 3,
            "max_retries": 2, "retry_after_respected": True,
            "backoff_base_seconds": 15, "backoff_max_seconds": 300,
        },
    }
    # Backward compat for v1 engine
    @property
    def platform_concurrency_limits(self) -> dict:
        return {p: c["max_concurrent"] for p, c in self.platform_rate_limits.items()}
    @property
    def platform_retry_config(self) -> dict:
        return {p: {"max_retries": self.collector_max_retries, "backoff_seconds": [1, 2]}
                for p in self.platform_rate_limits}

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

    # --- Queue config (P1-5) ---
    celery_broker_visibility_timeout: int = 3600
    celery_result_expires: int = 86400
    celery_worker_prefetch_multiplier: int = 1
    redis_max_connections: int = 100

    queue_alert_thresholds: dict = {
        "queue_backlog_warning": 50,
        "queue_backlog_critical": 200,
        "dlq_backlog_warning": 20,
        "dlq_backlog_critical": 100,
        "retry_rate_warning": 0.30,
        "failure_rate_critical": 0.50,
        "task_timeout_rate_warning": 0.10,
    }

    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_reset_seconds: int = 300

    celery_task_soft_time_limit: int = 900
    celery_task_time_limit: int = 1200

    # ── Email (P0) ───────────────────────────────────────────────────────────
    email_provider: str = "mock"
    email_api_key: str = ""
    email_from: str = "no-reply@geoexplorer.local"
    email_from_name: str = "GEO Explorer"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""

    # ── Object Storage (P0) ──────────────────────────────────────────────────
    storage_backend: str = "local"
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_endpoint_url: str = ""

    # ── HTTPS / Cookie (P0) ──────────────────────────────────────────────────
    app_base_url: str = "http://localhost:8000"
    cookie_secure: bool = False
    cookie_domain: str = ""

    # ── Rate Limiting (P1) ───────────────────────────────────────────────────
    rate_limit_enabled: bool = True
    register_rate_limit_per_hour: int = 5
    login_rate_limit_per_minute: int = 10

    # ── Feature Toggles ──────────────────────────────────────────────────────
    dev_routes_enabled: bool = True
    self_registration_enabled: bool = True

    # ── Monitoring (P1) ──────────────────────────────────────────────────────
    sentry_dsn: str = ""

    # ── System Owner ─────────────────────────────────────────────────────────
    system_owner_initial_email: str = "admin@geoexplorer.local"
    system_owner_initial_password: str = "change-me"


settings = Settings()
