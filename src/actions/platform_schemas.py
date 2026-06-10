"""Platform variant schemas — stable JSON contracts for Web/Doubao/Wenxin variants.

P0-5: Each platform variant type has a defined schema. Not arbitrary dicts.
P0-11: PlatformVariant (content) separate from PublishTarget (delivery state).
"""

from dataclasses import dataclass, field


# ── Variant status machine (P0-3) ────────────────────────────────────────────

VARIANT_STATUSES = [
    "draft", "generated", "needs_review", "approved",
    "ready_to_publish", "manual_publish_required",
    "published", "publish_failed", "outdated", "archived",
]

PUBLISH_TARGET_STATUSES = [
    "pending", "generating", "needs_review", "approved",
    "ready", "manual_publish_required",
    "published", "failed", "outdated",
]


# ── Web variant (DeepSeek/Kimi) ──────────────────────────────────────────────


def build_web_variant(theme: str, title: str, slug: str, html: str,
                      markdown: str, jsonld: list, schema_types: list,
                      fact_ids: list, evidence_ids: list) -> dict:
    return {
        "platform": "deepseek_kimi",
        "target": "brand_website",
        "format": "webpage",
        "theme": theme,
        "title": title,
        "slug": slug,
        "html": html,
        "markdown": markdown,
        "jsonld": jsonld,
        "schema_types": schema_types,
        "input_fact_ids": fact_ids,
        "evidence_ids": evidence_ids,
        "unsupported_claims": [],
        "claim_check_status": "pending",
        "version": 1,
        "generated_at": None,
        "status": "generated",
    }


# ── Doubao variants ──────────────────────────────────────────────────────────


def build_doubao_toutiao_variant(theme: str, seo_title: str, summary: str,
                                  body_markdown: str, tags: list, faq: list,
                                  word_count: int, fact_ids: list,
                                  evidence_ids: list) -> dict:
    return {
        "platform": "doubao",
        "target": "toutiao",
        "format": "toutiao_article",
        "theme": theme,
        "seo_title": seo_title,
        "summary": summary,
        "body_markdown": body_markdown,
        "tags": tags,
        "faq": faq,
        "word_count": word_count,
        "input_fact_ids": fact_ids,
        "evidence_ids": evidence_ids,
        "unsupported_claims": [],
        "claim_check_status": "pending",
        "version": 1,
        "generated_at": None,
        "status": "needs_review",
    }


def build_doubao_baike_card_variant(theme: str, fields: dict,
                                     references: list, fact_ids: list) -> dict:
    return {
        "platform": "doubao",
        "target": "baike",
        "format": "baike_card",
        "theme": theme,
        "fields": fields,
        "references": references,
        "input_fact_ids": fact_ids,
        "evidence_ids": [],
        "unsupported_claims": [],
        "claim_check_status": "pending",
        "version": 1,
        "generated_at": None,
        "status": "needs_review",
    }


# ── Wenxin variants ──────────────────────────────────────────────────────────


def build_wenxin_baidu_baike_variant(entry_name: str, infobox: dict,
                                      sections: list, references: list,
                                      compliance_flags: list,
                                      fact_ids: list, evidence_ids: list) -> dict:
    return {
        "platform": "wenxin",
        "target": "baidu_baike",
        "format": "baidu_baike_entry",
        "entry_name": entry_name,
        "infobox": infobox,
        "sections": sections,
        "references": references,
        "compliance_flags": compliance_flags,
        "input_fact_ids": fact_ids,
        "evidence_ids": evidence_ids,
        "unsupported_claims": [],
        "claim_check_status": "pending",
        "version": 1,
        "generated_at": None,
        "status": "needs_review",
    }


def build_wenxin_baijiahao_variant(theme: str, title: str, body_markdown: str,
                                    tags: list, word_count: int,
                                    fact_ids: list, evidence_ids: list) -> dict:
    return {
        "platform": "wenxin",
        "target": "baijiahao",
        "format": "baijiahao_article",
        "theme": theme,
        "title": title,
        "body_markdown": body_markdown,
        "tags": tags,
        "word_count": word_count,
        "input_fact_ids": fact_ids,
        "evidence_ids": evidence_ids,
        "unsupported_claims": [],
        "claim_check_status": "pending",
        "version": 1,
        "generated_at": None,
        "status": "needs_review",
    }


# ── PublishTarget (P0-11) ────────────────────────────────────────────────────


def build_publish_target(variant_id: str, platform: str, target: str) -> dict:
    return {
        "target_id": None,
        "variant_id": variant_id,
        "platform": platform,
        "target": target,
        "status": "needs_review",
        "published_url": None,
        "published_at": None,
        "indexed_status": "unknown",
        "ai_visibility_status": "unknown",
        "citation_detected": False,
        "last_checked_at": None,
        "last_error": None,
    }
