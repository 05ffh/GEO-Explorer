import uuid
from sqlalchemy import String, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin


class CollectionRun(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "collection_runs"
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False, index=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)    # 诊断单元·城市 "广州"
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)  # 诊断单元·地区/商圈 "天河区"
    positioning_json: Mapped[dict] = mapped_column(JSONB, default=dict)     # 定位结果：tier/personas/competitors（主 agent 推断产出）
    sentiment_json: Mapped[dict] = mapped_column(JSONB, default=dict)       # 测量结果：负面率 store_level/brand_level（主 agent 调度产出）
    measurement_json: Mapped[dict] = mapped_column(JSONB, default=dict)     # 测量结果：命中率 judgments + 四切面（P3 产出，主 agent 判自然段式后回填）
    gt_facts_json: Mapped[dict] = mapped_column(JSONB, default=dict)        # 结构化 GT 事实清单（方案 C，主 agent 联网查证整理）
    cdp_facts_json: Mapped[dict] = mapped_column(JSONB, default=dict)       # CDP 多平台事实清单（中间处理层产出，主 agent 判断；核验后并入 gt_facts_json）
    report_json: Mapped[dict] = mapped_column(JSONB, default=dict)          # 报告产物溯源：出生快照号/数据版本/产物 sha256/lint/交付记录（报告层写侧接入，append 历史）
