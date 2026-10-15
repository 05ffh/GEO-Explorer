from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    app_env: str = "development"        # 保留：_check_secrets_not_default 用（生产 fail-fast）
    secret_key: str = "change-me"       # 保留：同上

    database_url: str = "postgresql+asyncpg://geo:geo@localhost:5432/geo_explorer"
    test_database_url: str = "postgresql+asyncpg://geo_test:geo_test@localhost:5433/geo_explorer_test"

    # ── 四平台 AI（src/adapters/*）────────────────────────────────────────────
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

    collector_query_timeout_seconds: int = 60    # wenxin 适配器 httpx.Timeout 用

    # 报告交付目录（build_geo_report --deliver；留空 → ~/Desktop；WSL 示例：/mnt/c/Users/<user>/Desktop）
    geo_report_desktop: str = ""

    # --- 平台级限流 (rate_limiter) ---
    # 2026-08-28 联网查证后上调（仍保守，低于各平台真实上限）：
    # DeepSeek: 仅并发限制（无 RPM/TPM）→ 并发 8 安全
    # Kimi:   阿里云 K2 RPM 500 / TPM 1M → RPM 100 仍保守
    # Doubao: pro-32k RPM 10K / TPM 800K → RPM 1000 仍保守
    # Wenxin: ERNIE-4.0 预置 RPM 120 → RPM 50 保守
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
        """Known platforms: deepseek, kimi, doubao, wenxin. Required per platform: max_concurrent, max_retries."""
        import logging
        _log = logging.getLogger(__name__)
        known_platforms = {"deepseek", "kimi", "doubao", "wenxin"}
        required_keys = {"max_concurrent", "max_retries"}
        for platform, cfg in v.items():
            if platform not in known_platforms:
                _log.warning("Unknown platform in platform_rate_limits: %s — config will be loaded but may be unused", platform)
            missing = required_keys - set(cfg.keys())
            if missing:
                raise ValueError(f"platform_rate_limits['{platform}'] missing required keys: {missing}")
            if not isinstance(cfg.get("max_concurrent"), int) or cfg["max_concurrent"] < 1:
                raise ValueError(f"platform_rate_limits['{platform}'].max_concurrent must be int >= 1")
            if not isinstance(cfg.get("max_retries"), int) or cfg["max_retries"] < 0:
                raise ValueError(f"platform_rate_limits['{platform}'].max_retries must be int >= 0")
        return v

    # --- GT 搜索管线（两路：Tavily + 豆包搜索）---
    gt_search_tavily_enabled: bool = True
    gt_search_doubao_enabled: bool = True
    tavily_api_key: str = ""
    doubao_search_api_key: str = ""

    # --- 搜索后端可靠性 / 限流 ---
    search_max_retries: int = 2
    # Tavily/Doubao 为 API（RPM 按套餐浮动）；DDG 已于 2026-10-14 移除（端点不可达、拖慢采集）
    search_rate_limits: dict = {
        "tavily": {
            "max_concurrent": 2, "min_interval_seconds": 0.2,
            "max_requests_per_minute": 15, "backoff_base_seconds": 5, "backoff_max_seconds": 60,
        },
        "doubao_search": {
            "max_concurrent": 2, "min_interval_seconds": 0.2,
            "max_requests_per_minute": 15, "backoff_base_seconds": 5, "backoff_max_seconds": 60,
        },
    }

    @model_validator(mode="after")
    def _check_secrets_not_default(self):
        """生产环境密钥为默认值 → fail-fast。"""
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
                msg = f"Secret '{name}' is set to a default/placeholder value. Set a real secret in .env or environment variable."
                if self.app_env == "production":
                    raise ValueError(msg)
                _log.warning(msg)
        return self


settings = Settings()
