"""IndustryKnowledgeLoader — load and query machine-readable hospitality knowledge bases.

Each knowledge base is a YAML file under src/industry_knowledge/travel_hospitality/.
Every item carries metadata: hallucination_sensitive, evidence_required, applicable_entity_types, etc.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_KNOWLEDGE_DIR = Path(__file__).resolve().parent / "travel_hospitality"

_CATEGORY_FILES = {
    "negative_theme_keywords": "negative_theme_keywords.yaml",
    "platform_source_profile": "platform_source_profile.yaml",
    "field_source_mapping": "field_source_mapping.yaml",
    "sentiment_query": "sentiment_query.yaml",
    "brand_domains": "brand_domains.yaml",
    "question_templates": "question_templates.yaml",
}

# brand_domains 档位合法枚举（与 platform_baseline.TIER_ORDER / tier._ORDER 一致）
_BRAND_TIERS = {"经济", "中端", "中高端", "高端", "豪华"}


def validate_brand_domains(items: list[dict]) -> list[str]:
    """brand_domains 结构性校验（brand_domains 信任②，2026-09-10）。

    返回错误列表（空 = 通过）。校验：zh/tier 必填、tier 合法枚举、id 唯一、
    adr_range=[lo,hi] 且 lo<=hi、region/domain_keywords 类型。
    tier_source 可选（缺省 manual = 主 agent 认定，见 YAML 头注释）。fail-fast 调用方决定抛错。
    """
    errors: list[str] = []
    seen_ids: dict = {}
    for i, item in enumerate(items):
        if not item.get("zh"):
            errors.append(f"[{i}] 缺 zh")
        tier = item.get("tier")
        if tier not in _BRAND_TIERS:
            errors.append(f"[{i}] {item.get('id', '?')} 非法 tier {tier!r}（合法：{sorted(_BRAND_TIERS)}）")
        iid = item.get("id")
        if iid in seen_ids:
            errors.append(f"重复 id {iid!r}（第 {seen_ids[iid]} 与第 {i} 项）")
        else:
            seen_ids[iid] = i
        adr = item.get("adr_range")
        if adr is not None:
            ok = (isinstance(adr, list) and len(adr) == 2
                  and isinstance(adr[0], (int, float)) and isinstance(adr[1], (int, float))
                  and adr[0] <= adr[1])
            if not ok:
                errors.append(f"[{i}] {iid} adr_range 非法 {adr!r}")
        if item.get("region") is not None and not isinstance(item.get("region"), str):
            errors.append(f"[{i}] {iid} region 必须 str")
        if item.get("domain_keywords") is not None and not isinstance(item.get("domain_keywords"), list):
            errors.append(f"[{i}] {iid} domain_keywords 必须 list")
    return errors


class IndustryKnowledgeLoader:
    """Singleton loader for travel_hospitality industry knowledge.

    Loads YAML knowledge bases on first access. Each item is a dict with
    required fields: id, zh, aliases, use_for_prompt, use_for_fact,
    evidence_required, hallucination_sensitive, applicable_entity_types, related_scenarios.
    """

    _instance: IndustryKnowledgeLoader | None = None
    _cache: dict[str, list[dict]] = {}

    def __new__(cls) -> IndustryKnowledgeLoader:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def load_category(self, category: str) -> list[dict]:
        """Load all items for a category. Returns empty list on unknown category."""
        if category not in _CATEGORY_FILES:
            logger.warning("Unknown knowledge category: %s", category)
            return []

        if category in self._cache:
            return self._cache[category]

        path = _KNOWLEDGE_DIR / _CATEGORY_FILES[category]
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            items = data.get("items", []) if isinstance(data, dict) else []
            if category == "brand_domains":
                # fail-fast：品牌表是档位/竞对判定的地基，结构错误必须炸出来，不静默带病运行
                errors = validate_brand_domains(items)
                if errors:
                    raise ValueError(
                        f"brand_domains 校验失败（{len(errors)} 项）：\n" + "\n".join(f"  {e}" for e in errors))
            self._cache[category] = items
            logger.debug("Loaded %d items from %s", len(items), path.name)
            return items
        except FileNotFoundError:
            logger.warning("Knowledge file not found: %s", path)
            return []
        except yaml.YAMLError:
            logger.exception("Failed to parse %s", path)
            return []

    def find_by_alias(self, term: str, category: str | None = None) -> list[dict]:
        """Find knowledge items matching a term by id, zh, or alias.

        If category is None, searches all categories.
        """
        term_lower = (term or "").strip().lower()
        if not term_lower:
            return []

        categories = [category] if category else _CATEGORY_FILES.keys()
        results: list[dict] = []

        for cat in categories:
            for item in self.load_category(cat):
                if self._term_matches(item, term_lower):
                    results.append(item)

        return results

    def filter_by_entity_type(self, entity_type: str, category: str | None = None) -> list[dict]:
        """Return items applicable to a given entity_type."""
        et = (entity_type or "").strip().lower()
        if not et:
            return []

        categories = [category] if category else _CATEGORY_FILES.keys()
        results: list[dict] = []

        for cat in categories:
            for item in self.load_category(cat):
                applicable = item.get("applicable_entity_types", [])
                if et in [a.lower() for a in applicable]:
                    results.append(item)

        return results

    def filter_by_scenario(self, scenario: str, category: str | None = None) -> list[dict]:
        """Return items related to a given scenario."""
        sc = (scenario or "").strip().lower()
        if not sc:
            return []

        categories = [category] if category else _CATEGORY_FILES.keys()
        results: list[dict] = []

        for cat in categories:
            for item in self.load_category(cat):
                related = item.get("related_scenarios", [])
                if sc in [r.lower() for r in related]:
                    results.append(item)

        return results

    def is_hallucination_sensitive(self, term: str) -> bool:
        """Check whether a term is marked as hallucination_sensitive in the knowledge base."""
        matches = self.find_by_alias(term)
        for item in matches:
            if item.get("hallucination_sensitive") is True:
                return True
        return False

    def get_hallucination_rules(self, entity_type: str | None = None) -> list[dict]:
        """Return hallucination detection rules, optionally filtered by entity_type."""
        rules = self.load_category("hallucination_rules")
        if entity_type:
            et = entity_type.strip().lower()
            rules = [r for r in rules if et in [a.lower() for a in r.get("applicable_entity_types", [])]]
        return rules

    def clear_cache(self) -> None:
        """Clear the in-memory cache (useful for testing)."""
        self._cache.clear()

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------

    @staticmethod
    def _term_matches(item: dict, term_lower: str) -> bool:
        if item.get("id", "").lower() == term_lower:
            return True
        if term_lower in item.get("zh", "").lower():
            return True
        if term_lower in [a.lower() for a in item.get("aliases", [])]:
            return True
        # Also check detection_keywords for hallucination rules
        for kw in item.get("detection_keywords", []):
            if term_lower in kw.lower():
                return True
        return False


# Convenience singleton accessor
_kb: IndustryKnowledgeLoader | None = None


def get_knowledge_loader() -> IndustryKnowledgeLoader:
    global _kb
    if _kb is None:
        _kb = IndustryKnowledgeLoader()
    return _kb
