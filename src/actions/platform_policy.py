"""Platform knowledge source policy (P0-1).

AI platform knowledge sources are configurable assumptions, NOT hardcoded facts.
Platforms may change their ingestion sources over time.
"""

PLATFORM_KNOWLEDGE_SOURCE_POLICY = {
    "deepseek": {
        "assumed_sources": ["brand_website", "public_web"],
        "supports_search_enabled": True,
        "primary_content_formats": ["webpage", "schema_jsonld"],
        "publish_targets": ["brand_website"],
        "auto_publish_possible": True,
        "confidence": "medium",
        "last_verified_at": None,
        "notes": "Web crawler — depends on search_enabled/model mode",
    },
    "kimi": {
        "assumed_sources": ["brand_website", "public_web"],
        "supports_search_enabled": True,
        "primary_content_formats": ["webpage", "schema_jsonld"],
        "publish_targets": ["brand_website"],
        "auto_publish_possible": True,
        "confidence": "medium",
        "last_verified_at": None,
        "notes": "Web crawler — depends on search_enabled/model mode",
    },
    "doubao": {
        "assumed_sources": ["toutiao", "douyin", "baike", "public_web"],
        "supports_search_enabled": False,
        "primary_content_formats": ["toutiao_article", "baike_card"],
        "publish_targets": ["toutiao", "baike"],
        "auto_publish_possible": False,
        "confidence": "medium",
        "last_verified_at": None,
        "notes": "ByteDance ecosystem — no public API for content publishing",
    },
    "wenxin": {
        "assumed_sources": ["baidu_baike", "baijiahao", "brand_website", "public_web"],
        "supports_search_enabled": False,
        "primary_content_formats": ["baidu_baike_entry", "baijiahao_article", "webpage"],
        "publish_targets": ["baidu_baike", "baijiahao", "brand_website"],
        "auto_publish_possible": False,
        "confidence": "medium",
        "last_verified_at": None,
        "notes": "Baidu ecosystem — baike/baijiahao require manual publishing",
    },
}

PLATFORM_CONTENT_ADAPTERS = {
    "deepseek": {"enabled": True, "targets": ["brand_website"]},
    "kimi": {"enabled": True, "targets": ["brand_website"]},
    "doubao": {"enabled": True, "targets": ["toutiao", "baike"]},
    "wenxin": {"enabled": True, "targets": ["baidu_baike", "baijiahao", "brand_website"]},
}


def get_platform_targets(platform: str) -> list[str]:
    return PLATFORM_CONTENT_ADAPTERS.get(platform, {}).get("targets", [])


def get_platform_sources(platform: str) -> list[str]:
    return PLATFORM_KNOWLEDGE_SOURCE_POLICY.get(platform, {}).get("assumed_sources", [])


def platform_supports_auto_publish(platform: str) -> bool:
    return PLATFORM_KNOWLEDGE_SOURCE_POLICY.get(platform, {}).get("auto_publish_possible", False)
