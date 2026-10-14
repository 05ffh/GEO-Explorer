import uuid
from datetime import datetime, timezone
from sqlalchemy import String, ForeignKey, Integer, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, UUIDMixin


class SearchResultRecord(Base, UUIDMixin):
    """原始材料层：三大搜索引擎返回结果的持久化（补"绝不编造"证据链空白）。

    对应内存对象 EnhancedSearchResult（src/search/search_adapter.py）。
    source_tier 沿用现有 S/A/B/C/D，P1 事实可信度层统一迁移到 T0-T4。
    """
    __tablename__ = "search_results"
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    collection_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("collection_runs.id"), nullable=True, index=True)
    search_backend: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # tavily/doubao_search/cdp
    query: Mapped[str] = mapped_column(Text, default="")
    title: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(Text, default="")
    snippet: Mapped[str] = mapped_column(Text, default="")
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)  # 正文（过滤后基准事实，下游消费用）
    raw_content: Mapped[str | None] = mapped_column(Text, nullable=True)  # 抓取的页面原文（重处理原料，不对下游暴露）
    content_layer: Mapped[str] = mapped_column(String(20), default="fact")  # fact=甲方事实 / opinion=第三方观点（UGC/点评，不进 content_text）
    rank: Mapped[int] = mapped_column(Integer, default=0)
    source_tier: Mapped[str] = mapped_column(String(10), default="T3")  # T0-T4（spec 6.1 事实信源分级）
    published_at: Mapped[str | None] = mapped_column(String(100), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
