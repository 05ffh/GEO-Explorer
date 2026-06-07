"""GTSearchService — Tavily-first GT search orchestration (P0-1/2/3/6/9).

Core flow:
  1. generate_queries() — auto-generate search queries per field from brand name/aliases
  2. search() — call enabled adapters, merge results, URL dedup, source tier classification
  3. generate_candidate() — create GroundTruthCandidate (pending_review) + GroundTruthEvidence
"""

import hashlib
import logging
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.brand import Brand
from src.models.gt_candidate import GroundTruthCandidate
from src.models.gt_evidence import GroundTruthEvidence
from src.search.search_adapter import SearchAdapter, EnhancedSearchResult

logger = logging.getLogger(__name__)

# ── Query generation templates per field type ─────────────────────────────────

FIELD_QUERY_TEMPLATES = {
    "official_name": [
        "{brand} 公司全称", "{brand} 官方网站", "{brand} official name",
    ],
    "official_domains": [
        "{brand} 官网", "{brand} 官方网站地址", "{brand} official website",
    ],
    "official_website": [
        "{brand} 官网", "{brand} 官方网站", "{brand} official website",
    ],
    "industry": [
        "{brand} 是什么行业", "{brand} 行业分类", "{brand} 属于什么行业",
    ],
    "category": [
        "{brand} 产品类别", "{brand} 分类", "{brand} category",
    ],
    "positioning": [
        "{brand} 品牌定位", "{brand} 市场定位",
    ],
    "core_products": [
        "{brand} 核心产品", "{brand} 主要产品", "{brand} 产品列表", "{brand} products",
    ],
    "target_users": [
        "{brand} 目标用户", "{brand} 用户群体", "{brand} target users",
    ],
    "key_differentiators": [
        "{brand} 核心竞争力", "{brand} 差异化优势", "{brand} differentiators",
    ],
    "core_scenarios": [
        "{brand} 使用场景", "{brand} 应用场景",
    ],
    "target_competitors": [
        "{brand} 竞争对手", "{brand} 竞品分析", "{brand} competitors",
    ],
    "founded_year": [
        "{brand} 成立时间", "{brand} 公司历史", "{brand} founded",
    ],
    "headquarters": [
        "{brand} 总部", "{brand} 总部地址", "{brand} headquarters",
    ],
    "store_count": [
        "{brand} 门店数量", "{brand} 店铺数量",
    ],
    "pricing": [
        "{brand} 价格", "{brand} 定价", "{brand} pricing",
    ],
    "aliases": [
        "{brand} 别名", "{brand} 别称", "{brand} also known as",
    ],
}

DEFAULT_FIELD_TEMPLATES = [
    "{brand} {field_label}", "{brand} {field_label} 官方", "{brand} {field_label} 权威来源",
]


class GTSearchService:
    """Orchestrates multi-provider GT search + candidate/evidence creation."""

    def __init__(self, adapters: list[SearchAdapter], db: AsyncSession):
        self._adapters = adapters
        self._db = db

    # ── Provider status ───────────────────────────────────────────────────

    def get_available_providers(self) -> dict:
        return {
            a.name: {
                "status": a.status,
                "is_available": a.is_available(),
                "is_fallback": getattr(a, "is_fallback", False),
            }
            for a in self._adapters
        }

    # ── Query generation (P1-1) ────────────────────────────────────────────

    def generate_queries(self, brand: Brand, field_name: str,
                         manual_query: str | None = None) -> list[str]:
        """Generate search queries for a GT field using brand name + aliases."""
        if manual_query:
            return [manual_query]

        from src.schemas.gt_field_registry import GT_FIELD_REGISTRY
        field_def = GT_FIELD_REGISTRY.get(field_name)
        field_label = field_def.label if field_def else field_name

        templates = FIELD_QUERY_TEMPLATES.get(field_name, DEFAULT_FIELD_TEMPLATES)
        brand_names = [brand.name]
        if brand.aliases:
            brand_names.extend(brand.aliases)

        queries = []
        for tmpl in templates:
            # Try primary brand name first, then 1-2 aliases
            candidates = brand_names[:3]
            for bn in candidates:
                q = tmpl.replace("{brand}", bn)
                # Also replace legacy template variables if present
                q = q.replace("{field_label}", field_label)
                if q not in queries:
                    queries.append(q)
            if len(queries) >= 9:
                break
        return queries[:9]  # Cap at 9 queries per field

    # ── Search orchestration ──────────────────────────────────────────────

    async def search(
        self, brand: Brand, field_name: str,
        manual_query: str | None = None, limit: int = 10,
    ) -> list[EnhancedSearchResult]:
        """Auto-generate queries, search all enabled providers, merge + dedup."""
        queries = self.generate_queries(brand, field_name, manual_query)
        all_results = []

        for adapter in self._adapters:
            if not adapter.is_available():
                logger.debug("Skipping %s (status=%s)", adapter.name, adapter.status)
                continue
            for q in queries[:3]:  # Limit to 3 queries per provider
                try:
                    items = await adapter.search(q, limit=limit)
                    all_results.extend(items)
                except Exception as exc:
                    logger.warning(
                        "Search failed for %s query=%s: %s",
                        adapter.name, q[:80], exc,
                    )

        # URL dedup: normalize and keep first occurrence
        seen = set()
        deduped = []
        for r in all_results:
            norm_url = self._normalize_url(r.url)
            if norm_url not in seen:
                seen.add(norm_url)
                deduped.append(r)
        return deduped

    # ── Candidate generation (P0-1/2/3) ────────────────────────────────────

    async def generate_candidate(
        self,
        brand_id: uuid.UUID,
        org_id: uuid.UUID,
        field_name: str,
        proposed_value: str,
        extraction_method: str,
        search_results: list[EnhancedSearchResult],
        user_id: str,
    ) -> GroundTruthCandidate:
        """Create GTCandidate (pending_review) + GroundTruthEvidence from search results.

        P0-1: SearchResult → Evidence → Candidate. Never write directly to GT.
        P0-2: proposed_value required, must be from extraction or human editing.
        P0-3: Multiple evidence items linked to one candidate.
        """
        if not proposed_value or not proposed_value.strip():
            raise ValueError("proposed_value is required and cannot be empty")

        from src.schemas.gt_field_registry import GT_FIELD_REGISTRY
        field_def = GT_FIELD_REGISTRY.get(field_name)
        value_type = field_def.field_type if field_def else "string"

        candidate = GroundTruthCandidate(
            id=uuid.uuid4(),
            organization_id=org_id,
            brand_id=brand_id,
            candidate_json={
                "field_name": field_name,
                "proposed_value": proposed_value,
                "value_type": value_type,
                "extraction_method": extraction_method,
                "evidence_ids": [],
                "primary_evidence_id": None,
                "requires_human_review": True,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "generated_by": user_id,
            },
            confidence_summary={"source_count": 0, "tiers": {}},
            overall_confidence="low",
            status="pending_review",
        )
        self._db.add(candidate)
        await self._db.flush()

        # Create GroundTruthEvidence rows for each search result
        evidence_ids = []
        primary_id = None
        tier_counts = {}

        for i, sr in enumerate(search_results):
            ev = GroundTruthEvidence(
                id=uuid.uuid4(),
                candidate_id=candidate.id,
                field_name=field_name,
                value=sr.snippet,
                source_type="search_result",
                source_name=sr.provider,
                source_url=sr.url,
                excerpt=sr.snippet,
                source_tier=sr.source_tier,
                source_quality="high" if sr.source_tier in ("S", "A") else
                              "medium" if sr.source_tier == "B" else "low",
                confidence="high" if sr.source_tier in ("S", "A") else
                           "medium" if sr.source_tier == "B" else "low",
                review_status="pending",
                collected_at=datetime.now(timezone.utc),
            )
            self._db.add(ev)
            evidence_ids.append(str(ev.id))
            if primary_id is None:
                primary_id = str(ev.id)
            tier_counts[sr.source_tier] = tier_counts.get(sr.source_tier, 0) + 1

        # Update candidate with evidence links
        candidate.candidate_json["evidence_ids"] = evidence_ids
        candidate.candidate_json["primary_evidence_id"] = primary_id
        candidate.confidence_summary = {
            "source_count": len(search_results),
            "tiers": tier_counts,
        }

        await self._db.flush()
        await self._db.commit()

        return candidate

    # ── URL normalization (P1-2) ───────────────────────────────────────────

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Normalize URL for dedup: lowercase host, strip www, trailing slash,
        remove utm/fragment, normalize http/https."""
        if not url:
            return ""
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        netloc = netloc.lstrip("www.")
        path = parsed.path.rstrip("/") or "/"
        # Remove common mobile subdomain prefixes
        if netloc.startswith("m."):
            netloc = netloc[2:]
        # Reconstruct: https://netloc + path
        return f"https://{netloc}{path}"

    # ── Fallback: DuckDuckGo when Tavily unavailable ──────────────────────

    async def has_results_from_primary(self, brand: Brand, field_name: str) -> bool:
        """Check if primary adapter (Tavily) returns any results for a field."""
        queries = self.generate_queries(brand, field_name)[:1]
        for adapter in self._adapters:
            if not adapter.is_available():
                continue
            if getattr(adapter, "is_fallback", False):
                continue
            for q in queries:
                results = await adapter.search(q, limit=1)
                if results:
                    return True
        return False
