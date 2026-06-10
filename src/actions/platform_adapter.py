"""Platform content adaptation layer (P0-2, P0-10).

Orchestrates per-platform content variant generation from a ContentPackage's
base GT facts. Each platform gets independent generation.

Called from: _generate_content_packages() in pipeline.py
"""

import hashlib
import logging
from datetime import datetime, timezone

from src.actions.platform_policy import PLATFORM_CONTENT_ADAPTERS
from src.actions.platform_schemas import (
    build_web_variant, build_doubao_toutiao_variant,
    build_doubao_baike_card_variant, build_wenxin_baidu_baike_variant,
    build_wenxin_baijiahao_variant, build_publish_target,
)
from src.actions.platform_compliance import check_compliance

logger = logging.getLogger(__name__)


async def generate_platform_variants(
    brand_name: str, gt_facts: dict, theme: dict,
    fact_ids: list, evidence_ids: list,
) -> dict[str, list[dict]]:
    """Generate platform-specific content variants for one Content Theme.

    Args:
        brand_name: brand display name
        gt_facts: {field_name: value} from active GT
        theme: Content Theme dict {theme, content_type, fields, publish_target}
        fact_ids: GT field names used as fact sources
        evidence_ids: GroundTruthEvidence IDs backing these facts

    Returns:
        {platform_key: [variant_dict, ...]} keyed by platform name
    """
    variants = {}

    # DeepSeek/Kimi: web page variant
    web_adapter_enabled = (
        PLATFORM_CONTENT_ADAPTERS.get("deepseek", {}).get("enabled", True)
    )
    if web_adapter_enabled:
        variants["deepseek_kimi"] = await _generate_web_variants(
            brand_name, gt_facts, theme, fact_ids, evidence_ids,
        )

    # Doubao
    if PLATFORM_CONTENT_ADAPTERS.get("doubao", {}).get("enabled", True):
        variants["doubao"] = await _generate_doubao_variants(
            brand_name, gt_facts, theme, fact_ids, evidence_ids,
        )

    # Wenxin
    if PLATFORM_CONTENT_ADAPTERS.get("wenxin", {}).get("enabled", True):
        variants["wenxin"] = await _generate_wenxin_variants(
            brand_name, gt_facts, theme, fact_ids, evidence_ids,
        )

    return variants


def _compute_snapshot_hash(gt_facts: dict) -> str:
    raw = "|".join(f"{k}={v}" for k, v in sorted(gt_facts.items()) if v)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _build_facts_text(gt_facts: dict) -> str:
    return "\n".join(f"- {k}: {v}" for k, v in gt_facts.items() if v)


# ── Web variants (DeepSeek/Kimi) ──────────────────────────────────────────────


async def _generate_web_variants(brand_name: str, gt_facts: dict,
                                  theme: dict, fact_ids: list,
                                  evidence_ids: list) -> list[dict]:
    from src.actions.schema_generator import generate_jsonld
    from src.actions.executor import _generate_with_llm

    prompt = theme.get("prompt_template", "").format(
        brand=brand_name, facts=_build_facts_text(gt_facts),
    )
    content_body = await _generate_with_llm(prompt, theme.get("content_type", "Organization"))

    schema = generate_jsonld(brand_name, gt_facts, theme.get("content_type", "Organization"))

    variant = build_web_variant(
        theme=theme["theme"],
        title=f"{brand_name} - {theme['theme']}",
        slug=f"/{theme.get('publish_target','about').replace('/','')}",
        html=f"<article>{content_body}</article>",
        markdown=content_body,
        jsonld=schema.get("schemas", []),
        schema_types=[s.get("@type", "") for s in schema.get("schemas", [])],
        fact_ids=fact_ids,
        evidence_ids=evidence_ids,
    )
    variant["generated_at"] = datetime.now(timezone.utc).isoformat()
    variant["status"] = "generated"
    return [variant]


# ── Doubao variants ──────────────────────────────────────────────────────────


async def _generate_doubao_variants(brand_name: str, gt_facts: dict,
                                     theme: dict, fact_ids: list,
                                     evidence_ids: list) -> list[dict]:
    from src.actions.executor import _generate_with_llm

    variants = []
    facts_text = _build_facts_text(gt_facts)

    # Toutiao article
    toutiao_prompt = (
        f"你是一个品牌内容专家。基于以下品牌事实，撰写一篇面向头条号的 SEO 优化文章。\n\n"
        f"要求：\n"
        f"- 标题吸引点击，包含\"{brand_name}\"和核心卖点\n"
        f"- 1200-2000 字，分 3-5 个小节，每节有小标题\n"
        f"- 含 FAQ 段落（至少 2 个问答）\n"
        f"- 适合字节跳动生态的 SEO 规则\n"
        f"- 只使用提供的事实，不编造\n"
        f"- 语调专业但接地气\n\n"
        f"品牌: {brand_name}\n"
        f"主题: {theme['theme']}\n"
        f"事实:\n{facts_text}\n"
    )
    toutiao_body = await _generate_with_llm(toutiao_prompt, "toutiao_article")
    toutiao_variant = build_doubao_toutiao_variant(
        theme=theme["theme"],
        seo_title=f"{brand_name} 是什么？一文了解 {brand_name} 的{theme['theme']}",
        summary=f"基于官方事实的 {brand_name} {theme['theme']} 介绍",
        body_markdown=toutiao_body,
        tags=[brand_name] + theme.get("fields", []),
        faq=[],
        word_count=len(toutiao_body),
        fact_ids=fact_ids,
        evidence_ids=evidence_ids,
    )
    toutiao_variant["generated_at"] = datetime.now(timezone.utc).isoformat()
    variants.append(toutiao_variant)

    # Baike card
    baike_card = build_doubao_baike_card_variant(
        theme=theme["theme"],
        fields={f: str(gt_facts.get(f, ""))[:200] for f in fact_ids},
        references=[str(gt_facts.get("official_domains", ""))],
        fact_ids=fact_ids,
    )
    baike_card["generated_at"] = datetime.now(timezone.utc).isoformat()
    variants.append(baike_card)

    return variants


# ── Wenxin variants ──────────────────────────────────────────────────────────


async def _generate_wenxin_variants(brand_name: str, gt_facts: dict,
                                     theme: dict, fact_ids: list,
                                     evidence_ids: list) -> list[dict]:
    from src.actions.executor import _generate_with_llm

    variants = []
    facts_text = _build_facts_text(gt_facts)

    # Baidu Baike entry
    baike_prompt = (
        f"你是一个品牌百科编辑专家。基于以下品牌事实，撰写百度百科词条内容。\n\n"
        f"要求：\n"
        f"- 包含 Infobox 信息\n"
        f"- 正文分节：品牌简介、发展历程、核心业务\n"
        f"- 每段 100-200 字，客观中立\n"
        f"- 禁止使用\"领先\"\"第一\"\"最大\"\"最好\"\"唯一\"\"最强\"\"顶级\"\"绝对\"等表述\n"
        f"- 只使用提供的事实\n\n"
        f"品牌: {brand_name}\n"
        f"主题: {theme['theme']}\n"
        f"事实:\n{facts_text}\n"
    )
    baike_body = await _generate_with_llm(baike_prompt, "baidu_baike_entry")

    infobox = {}
    for k in ("official_name", "founded_year", "headquarters", "official_domains",
              "industry", "category"):
        if k in gt_facts:
            infobox[k] = str(gt_facts[k])[:100]

    baike_variant = build_wenxin_baidu_baike_variant(
        entry_name=brand_name,
        infobox=infobox,
        sections=[
            {"title": "品牌简介", "content": baike_body[:500]},
            {"title": "核心业务", "content": baike_body[500:1000] if len(baike_body) > 500 else ""},
        ],
        references=[str(gt_facts.get("official_domains", ""))],
        compliance_flags=[],
        fact_ids=fact_ids,
        evidence_ids=evidence_ids,
    )
    baike_variant["generated_at"] = datetime.now(timezone.utc).isoformat()
    baike_variant["status"] = "needs_review"

    # Compliance check
    compliance = check_compliance(baike_variant, "baidu_baike")
    baike_variant["compliance_flags"] = compliance["flags"]
    baike_variant["claim_check_status"] = "passed" if compliance["passed"] else "needs_review"
    if compliance["status"] == "blocked":
        baike_variant["status"] = "needs_review"
    variants.append(baike_variant)

    # Baijiahao article
    bjh_prompt = (
        f"你是一个品牌内容专家。基于以下品牌事实，撰写一篇面向百家号的 SEO 长文。\n\n"
        f"要求：\n"
        f"- 标题包含\"{brand_name}\"\n"
        f"- 1000-2000 字\n"
        f"- SEO 友好\n"
        f"- 只使用提供的事实\n"
        f"- 客观专业\n\n"
        f"品牌: {brand_name}\n"
        f"主题: {theme['theme']}\n"
        f"事实:\n{facts_text}\n"
    )
    bjh_body = await _generate_with_llm(bjh_prompt, "baijiahao_article")

    bjh_variant = build_wenxin_baijiahao_variant(
        theme=theme["theme"],
        title=f"{brand_name} — {theme['theme']} | 品牌介绍",
        body_markdown=bjh_body,
        tags=[brand_name],
        word_count=len(bjh_body),
        fact_ids=fact_ids,
        evidence_ids=evidence_ids,
    )
    bjh_variant["generated_at"] = datetime.now(timezone.utc).isoformat()
    bjh_variant["status"] = "needs_review"
    variants.append(bjh_variant)

    return variants
