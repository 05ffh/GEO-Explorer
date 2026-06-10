"""Platform content compliance checker (P0-6).

Detects absolute claims, unsupported superlatives, ad tone,
sensitive claims, and reference requirements in platform variants.
"""

ABSOLUTE_CLAIM_PATTERNS = [
    "领先", "第一", "最大", "最好", "唯一",
    "最强", "顶级", "绝对", "独家", "首创",
]

AD_TONE_PATTERNS = [
    "立即购买", "马上咨询", "限时优惠", "折扣",
    "免费试用", "火爆", "抢购", "不容错过",
]

SENSITIVE_PATTERNS = {
    "medical": ["治愈", "治疗", "疗效", "康复", "根治"],
    "financial": ["稳赚", "保本", "高收益", "无风险"],
    "efficacy": ["保证有效", "100%有效", "绝对有效"],
}


def check_compliance(variant: dict, target_type: str) -> dict:
    """Check a platform variant for compliance issues.

    Returns: {status, flags, passed}
      status: "passed" | "needs_review" | "blocked"
      flags: list of {type, text, severity, location}
      passed: bool
    """
    flags = []

    # Check based on format type
    body = variant.get("body_markdown") or variant.get("markdown") or ""
    infobox = variant.get("infobox") or {}
    sections = variant.get("sections") or []

    # Collect all text to check
    texts = [body]
    if infobox:
        texts.extend(str(v) for v in infobox.values())
    for s in sections:
        texts.append(s.get("title", "") + " " + s.get("content", ""))

    full_text = " ".join(texts)

    # 1. Absolute claims
    for pattern in ABSOLUTE_CLAIM_PATTERNS:
        if pattern in full_text:
            flags.append({
                "type": "absolute_claim",
                "text": pattern,
                "severity": "high",
                "location": "body",
            })

    # 2. Ad tone
    for pattern in AD_TONE_PATTERNS:
        if pattern in full_text:
            flags.append({
                "type": "ad_tone",
                "text": pattern,
                "severity": "medium",
                "location": "body",
            })

    # 3. Sensitive claims
    for category, patterns in SENSITIVE_PATTERNS.items():
        for pattern in patterns:
            if pattern in full_text:
                flags.append({
                    "type": f"sensitive_{category}",
                    "text": pattern,
                    "severity": "high",
                    "location": "body",
                })

    # 4. Reference check for baike/encyclopedia content
    if target_type in ("baidu_baike", "baike_card", "baike"):
        refs = variant.get("references", [])
        if not refs:
            flags.append({
                "type": "reference_required",
                "text": "百科类内容缺少参考资料",
                "severity": "high",
                "location": "references",
            })

    # Determine overall status
    high_flags = [f for f in flags if f["severity"] == "high"]
    if high_flags:
        status = "blocked"
        passed = False
    elif flags:
        status = "needs_review"
        passed = False
    else:
        status = "passed"
        passed = True

    return {
        "status": status,
        "passed": passed,
        "flags": flags,
        "flags_count": len(flags),
        "high_count": len(high_flags),
    }
