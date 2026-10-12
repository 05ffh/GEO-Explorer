"""Platform capability policy (adapter runtime config, 2026-09-24 去重叠瘦身).

只放 adapter 能力开关（运行配置，adapters/base.py 消费）。信源调性知识
（主信源/内容形式/铺放目标）唯一源 = `platform_source_profile.yaml`
（industry_knowledge loader 加载，信源调研 / P4 落地消费）——两份文件各管一域，不再重叠。

Platforms may change capabilities over time.
"""

PLATFORM_CAPABILITY_POLICY = {
    "deepseek": {"supports_search_enabled": True},
    "kimi": {"supports_search_enabled": True},
    "doubao": {"supports_search_enabled": False},
    "wenxin": {"supports_search_enabled": False},
}


def platform_supports_search(platform: str) -> bool:
    return PLATFORM_CAPABILITY_POLICY.get(platform, {}).get("supports_search_enabled", False)
