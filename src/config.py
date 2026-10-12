from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")
    app_env: str = "development"
    metrics_enabled: bool = False  # Enable only when prometheus_client installed and scrape configured
    secret_key: str = "change-me"
    database_url: str = "postgresql+asyncpg://geo:geo@localhost:5432/geo_explorer"
    test_database_url: str = "postgresql+asyncpg://geo_test:geo_test@localhost:5433/geo_explorer_test"

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"

    kimi_api_key: str = ""
    kimi_base_url: str = "https://api.moonshot.cn/v1"
    kimi_model: str = "kimi-k2.6"  # 2026-09-04 修正：kimi-k2.5 已下线（404），k2.6 实测支持 $web_search 真实联网

    doubao_api_key: str = ""
    doubao_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    doubao_model: str = "doubao-seed-2-0-lite-260428"

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
    # 2026-08-28 联网查证后上调（仍保守，低于各平台真实上限）：
    # DeepSeek: 仅并发限制（无 RPM/TPM），v4-pro 并发 500 / v4-flash 2500 → 并发 8 安全
    # Kimi:   官方按充值分级；阿里云 K2 RPM 500 / TPM 1M → RPM 100 仍保守
    # Doubao: pro-32k RPM 10K / TPM 800K → RPM 1000 仍保守
    # Wenxin: 4.5 免费 QPS≤50；ERNIE-4.0 预置 RPM 120 → RPM 50 保守
    # 单品牌诊断 35 题（25 命中 + 10 归因，P1-②）不会被限流；批量诊断多品牌才需继续上调。
    platform_rate_limits: dict = {
        "deepseek": {
            "max_concurrent": 8, "min_interval_seconds": 0.1,
            "max_requests_per_minute": None, "max_tokens_per_minute": None,
            "cooldown_on_429_seconds": 300, "consecutive_429_threshold": 3,
            "max_retries": 2, "retry_after_respected": True,
            "backoff_base_seconds": 15, "backoff_max_seconds": 300,
        },
        "kimi": {
            "max_concurrent": 3, "min_interval_seconds": 0.2,
            "max_requests_per_minute": 100, "max_tokens_per_minute": 1000000,
            "cooldown_on_429_seconds": 300, "consecutive_429_threshold": 3,
            "max_retries": 3, "retry_after_respected": True,
            "backoff_base_seconds": 30, "backoff_max_seconds": 900,
        },
        "doubao": {
            "max_concurrent": 2, "min_interval_seconds": 0.2,
            "max_requests_per_minute": 1000, "max_tokens_per_minute": 1500000,
            "cooldown_on_429_seconds": 300, "consecutive_429_threshold": 3,
            "max_retries": 3, "retry_after_respected": True,
            "backoff_base_seconds": 30, "backoff_max_seconds": 900,
        },
        "wenxin": {
            "max_concurrent": 3, "min_interval_seconds": 0.3,
            "max_requests_per_minute": 50, "max_tokens_per_minute": 500000,
            "cooldown_on_429_seconds": 300, "consecutive_429_threshold": 3,
            "max_retries": 2, "retry_after_respected": True,
            "backoff_base_seconds": 15, "backoff_max_seconds": 300,
        },
    }

    @field_validator("platform_rate_limits")
    @classmethod
    def _validate_platform_rate_limits(cls, v: dict) -> dict:
        """Validate platform_rate_limits structure.

        Known platforms: deepseek, kimi, doubao, wenxin.
        Required keys per platform: max_concurrent, max_retries.
        Unknown platforms raise a warning via logging.
        """
        import logging
        _log = logging.getLogger(__name__)
        known_platforms = {"deepseek", "kimi", "doubao", "wenxin"}
        required_keys = {"max_concurrent", "max_retries"}

        for platform, cfg in v.items():
            if platform not in known_platforms:
                _log.warning(
                    "Unknown platform in platform_rate_limits: %s — config will be loaded but may be unused",
                    platform,
                )
            missing = required_keys - set(cfg.keys())
            if missing:
                raise ValueError(
                    f"platform_rate_limits['{platform}'] missing required keys: {missing}"
                )
            if not isinstance(cfg.get("max_concurrent"), int) or cfg["max_concurrent"] < 1:
                raise ValueError(
                    f"platform_rate_limits['{platform}'].max_concurrent must be int >= 1"
                )
            if not isinstance(cfg.get("max_retries"), int) or cfg["max_retries"] < 0:
                raise ValueError(
                    f"platform_rate_limits['{platform}'].max_retries must be int >= 0"
                )
        return v

    @model_validator(mode="after")
    def _check_secrets_not_default(self):
        """P3-3: Fail-fast in production if secrets are default values."""
        import logging
        _log = logging.getLogger(__name__)
        sensitive_defaults = ("change-me", "default", "please-change", "changeme")
        secret_fields = [
            ("secret_key", self.secret_key),
            ("deepseek_api_key", self.deepseek_api_key),
            ("kimi_api_key", self.kimi_api_key),
            ("doubao_api_key", self.doubao_api_key),
            ("wenxin_api_key", self.wenxin_api_key),
        ]
        for name, value in secret_fields:
            if value and any(d in value.lower() for d in sensitive_defaults):
                msg = (
                    f"Secret '{name}' is set to a default/placeholder value."
                    f" Set a real secret in .env or environment variable."
                )
                if self.app_env == "production":
                    raise ValueError(msg)
                else:
                    _log.warning(msg)
        return self

    # Backward compat for v1 engine
    @property
    def platform_concurrency_limits(self) -> dict:
        return {p: c["max_concurrent"] for p, c in self.platform_rate_limits.items()}
    @property
    def platform_retry_config(self) -> dict:
        return {p: {"max_retries": self.collector_max_retries, "backoff_seconds": [1, 2]}
                for p in self.platform_rate_limits}

    # --- GT Search Pipeline ---
    gt_search_tavily_enabled: bool = True
    gt_search_duckduckgo_enabled: bool = True
    gt_search_doubao_enabled: bool = True
    gt_search_cache_ttl_seconds: int = 86400  # 24h
    tavily_api_key: str = ""
    doubao_search_api_key: str = ""

    # --- Search backend reliability ---
    search_timeout_seconds: float = 20.0
    search_connect_timeout_seconds: float = 10.0
    search_read_timeout_seconds: float = 20.0
    search_max_retries: int = 2
    search_retry_backoff_seconds: float = 1.5
    search_disable_after_failures: int = 2
    tavily_independent_client: bool = True
    duckduckgo_auto_disable: bool = True

    # --- 搜索后端限流（三引擎并发采集，防 429/封禁）---
    # Tavily/Doubao 为 API（RPM 按套餐浮动），DDG 为爬取（无 key、最敏感，从严）
    search_rate_limits: dict = {
        "tavily": {
            "max_concurrent": 2, "min_interval_seconds": 0.2,
            "max_requests_per_minute": 15, "backoff_base_seconds": 5, "backoff_max_seconds": 60,
        },
        "doubao_search": {
            "max_concurrent": 2, "min_interval_seconds": 0.2,
            "max_requests_per_minute": 15, "backoff_base_seconds": 5, "backoff_max_seconds": 60,
        },
        "duckduckgo": {
            "max_concurrent": 1, "min_interval_seconds": 0.5,
            "max_requests_per_minute": 8, "backoff_base_seconds": 10, "backoff_max_seconds": 120,
        },
    }

    # --- Content safety ---
    content_safe_mode: bool = True

    # --- Action 触发阈值 ---
    action_thresholds: dict = {
        "citation_rate": 0.05,
        "accuracy_rate": 0.60,
        "completeness_rate": 0.50,
        "first_rec_rate": 0.10,
        "differentiation_rate": 0.30,
        "scenario_recall_rate": 0.20,
    }

    # --- GT Visibility Score 阈值 (0-100 scale) ---
    gt_visibility_high_threshold: float = 70.0
    gt_visibility_medium_threshold: float = 40.0
    gt_visibility_low_threshold: float = 20.0  # fixed: was 40 (== medium)
    gt_visibility_field_weights: dict = {
        "official_name": 0.20, "official_domains": 0.15,
        "industry": 0.10, "category": 0.05,
        "core_products": 0.10, "core_scenarios": 0.08,
        "target_users": 0.08, "target_competitors": 0.08,
        "positioning": 0.06, "key_differentiators": 0.05,
        "founded_year": 0.03, "headquarters": 0.02,
    }
    gt_visibility_platform_weights: dict = {
        "deepseek": 0.25, "kimi": 0.25, "doubao": 0.25, "wenxin": 0.25,
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
