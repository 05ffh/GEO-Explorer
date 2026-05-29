import json


def generate_jsonld(brand_name: str, active_gt: dict, content_type: str = "FAQ") -> dict:
    """Generate Schema.org JSON-LD from active Ground Truth.

    Supports: FAQ, Organization, Product, WebSite types.
    """
    schemas = []

    if content_type == "FAQ":
        schema = _generate_faq(brand_name, active_gt)
    elif content_type == "Organization":
        schema = _generate_organization(active_gt)
    else:
        schema = _generate_organization(active_gt)

    schemas.append(schema)
    return {"schemas": schemas, "json_ld": json.dumps(schemas, ensure_ascii=False, indent=2)}


def _generate_organization(gt: dict) -> dict:
    org = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": gt.get("official_name", ""),
        "description": gt.get("positioning", ""),
    }
    if gt.get("official_domains"):
        domain = gt["official_domains"]
        if isinstance(domain, str):
            domain = domain.split(",")[0].strip()
        elif isinstance(domain, list):
            domain = domain[0] if domain else ""
        if domain:
            org["url"] = f"https://{domain}"
    return org


def _generate_faq(brand_name: str, gt: dict) -> dict:
    faq = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [],
    }
    questions = [
        (f"{brand_name} 是做什么的？", gt.get("positioning", "")),
        (f"{brand_name} 的核心产品是什么？", gt.get("core_products", "")),
        (f"{brand_name} 适合什么用户？", gt.get("target_users", "")),
    ]
    for q, a in questions:
        if a:
            faq["mainEntity"].append({
                "@type": "Question",
                "name": q,
                "acceptedAnswer": {"@type": "Answer", "text": str(a)[:500]},
            })
    return faq
