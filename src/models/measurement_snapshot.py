import uuid

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, UUIDMixin


class MeasurementSnapshot(Base, UUIDMixin, TimestampMixin):
    """测量快照：每次 AI 采集（全量 full / 补测 remeasure）生成一个版本。

    版本 = 采集状态的分界；回填（finalize_hit --apply 判定 / backfill）不新增版本，只修订最新快照
    （backfilled_at 记录修订时间）。对比可见度用 snapshot_no 定位，collected_at 展示。

    唯一约束 (collection_run_id, snapshot_no)：数据库兜底拒绝同一 run 重复版本号——
    即使未来并发/自动触发算出重复号，也报错而非静默覆盖，保证版本号始终唯一定位一个版本。
    """
    __tablename__ = "measurement_snapshots"
    __table_args__ = (
        UniqueConstraint("collection_run_id", "snapshot_no", name="uq_measurement_snapshot_run_no"),
    )

    collection_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collection_runs.id"), nullable=False, index=True
    )
    snapshot_no: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_type: Mapped[str] = mapped_column(String(20), nullable=False)  # full / remeasure
    collected_at: Mapped[str] = mapped_column(String(40), nullable=False)
    measurement_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    backfilled_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
