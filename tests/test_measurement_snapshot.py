"""测量版本快照测试：版本 = 采集（full/remeasure），回填修订最新快照不新增版本。"""
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.collector.gt_entry import create_collection_run, get_or_create_brand, write_measurement
from src.models.measurement_snapshot import MeasurementSnapshot
from src.models.organization import Organization


def _mk_measurement(overall, plats):
    return {
        "brand": "香格里拉",
        "city": "福州",
        "collected_at": "2026-08-30T10:00:00",
        "platforms": {p: {"judgments": [], "platform_rate": {"hit_rate": r}} for p, r in plats.items()},
        "overall": {"overall_hit_rate": overall, "platform_hit_rates": plats},
    }


async def _snapshots(db, run_id):
    return (
        await db.execute(
            select(MeasurementSnapshot)
            .where(MeasurementSnapshot.collection_run_id == run_id)
            .order_by(MeasurementSnapshot.snapshot_no)
        )
    ).scalars().all()


@pytest.mark.asyncio
async def test_full_then_remeasure_then_backfill(db_session):
    org = Organization(name="快照测试")
    db_session.add(org)
    await db_session.flush()
    brand = await get_or_create_brand(db_session, "香格里拉", org.id)
    run = await create_collection_run(db_session, org.id, brand.id, "福州", None)

    # ① 全量测量 → v1
    v1 = _mk_measurement(0.354, {"deepseek": 0.44, "kimi": 0.60, "doubao": 0.33, "wenxin": 0.0417})
    await write_measurement(db_session, run.id, v1, snapshot_type="full")
    snaps = await _snapshots(db_session, run.id)
    assert len(snaps) == 1
    assert snaps[0].snapshot_no == 1 and snaps[0].snapshot_type == "full"

    # ② 补测豆包 → v2（不覆盖 v1）
    v2 = _mk_measurement(0.3104, {"deepseek": 0.44, "kimi": 0.60, "doubao": 0.16, "wenxin": 0.0417})
    await write_measurement(db_session, run.id, v2, snapshot_type="remeasure")
    snaps = await _snapshots(db_session, run.id)
    assert len(snaps) == 2
    assert snaps[1].snapshot_no == 2 and snaps[1].snapshot_type == "remeasure"
    assert snaps[0].measurement_json["overall"]["overall_hit_rate"] == 0.354  # 历史保留
    assert snaps[1].measurement_json["overall"]["overall_hit_rate"] == 0.3104

    # ③ 回填 → 不新增版本，更新最新快照判定 + backfilled_at
    v2b = _mk_measurement(0.3104, {"deepseek": 0.44, "kimi": 0.60, "doubao": 0.16, "wenxin": 0.0417})
    v2b["status"] = "complete"
    await write_measurement(db_session, run.id, v2b, snapshot_type="backfill")
    snaps = await _snapshots(db_session, run.id)
    assert len(snaps) == 2  # 版本不膨胀
    assert snaps[1].backfilled_at is not None
    assert snaps[1].measurement_json.get("status") == "complete"
    assert snaps[0].backfilled_at is None          # v1 不受回填影响
    assert snaps[0].measurement_json.get("status") is None
    assert run.measurement_json.get("status") == "complete"  # measurement_json = 最新


@pytest.mark.asyncio
async def test_draft_then_judge_then_rejudge(db_session):
    """spec ⑫ 版本生命周期：采集=draft（不开快照）→ 判定=judge 新快照 → 重判=rejudge 又新快照，历史保留。"""
    org = Organization(name="版本架构测试")
    db_session.add(org)
    await db_session.flush()
    brand = await get_or_create_brand(db_session, "香格里拉", org.id)
    run = await create_collection_run(db_session, org.id, brand.id, "福州", None)

    # ① 采集 draft → 只写活数据，不开快照
    draft = _mk_measurement(0.0, {"deepseek": 0.0})
    draft["status"] = "partial"
    await write_measurement(db_session, run.id, draft, snapshot_type="draft")
    snaps = await _snapshots(db_session, run.id)
    assert len(snaps) == 0
    assert run.measurement_json["status"] == "partial"

    # ② 判定 judge → v1 快照
    judged = _mk_measurement(0.33, {"deepseek": 0.6, "kimi": 0.56, "doubao": 0.16, "wenxin": 0.0})
    judged["status"] = "complete"
    await write_measurement(db_session, run.id, judged, snapshot_type="judge")
    snaps = await _snapshots(db_session, run.id)
    assert len(snaps) == 1
    assert snaps[0].snapshot_no == 1 and snaps[0].snapshot_type == "judge"

    # ③ 重判 rejudge → v2 快照（不覆盖 v1，历史保留——0.32/0.33 各留一版）
    rejudged = _mk_measurement(0.35, {"deepseek": 0.6, "kimi": 0.6, "doubao": 0.16, "wenxin": 0.0})
    await write_measurement(db_session, run.id, rejudged, snapshot_type="rejudge")
    snaps = await _snapshots(db_session, run.id)
    assert len(snaps) == 2
    assert snaps[1].snapshot_no == 2 and snaps[1].snapshot_type == "rejudge"
    assert snaps[0].measurement_json["overall"]["overall_hit_rate"] == 0.33  # v1 保留
    assert snaps[1].measurement_json["overall"]["overall_hit_rate"] == 0.35


@pytest.mark.asyncio
async def test_backfill_without_snapshot_is_noop(db_session):
    """无任何快照时回填 → 不新建空版本。"""
    org = Organization(name="快照测试2")
    db_session.add(org)
    await db_session.flush()
    brand = await get_or_create_brand(db_session, "香格里拉", org.id)
    run = await create_collection_run(db_session, org.id, brand.id, "福州", None)

    await write_measurement(db_session, run.id, _mk_measurement(0.1, {"deepseek": 0.1}), snapshot_type="backfill")
    snaps = await _snapshots(db_session, run.id)
    assert len(snaps) == 0
    assert run.measurement_json["overall"]["overall_hit_rate"] == 0.1


@pytest.mark.asyncio
async def test_snapshot_no_unique_constraint(db_session):
    """数据库兜底：同一 run 的 snapshot_no 唯一，重复号被拒绝（防并发/自动触发撞号）。"""
    org = Organization(name="快照测试3")
    db_session.add(org)
    await db_session.flush()
    brand = await get_or_create_brand(db_session, "香格里拉", org.id)
    run = await create_collection_run(db_session, org.id, brand.id, "福州", None)

    await write_measurement(db_session, run.id, _mk_measurement(0.1, {"deepseek": 0.1}), snapshot_type="full")
    # 手动插入同 run 同 snapshot_no=1 → 唯一约束拒绝
    db_session.add(MeasurementSnapshot(
        collection_run_id=run.id, snapshot_no=1, snapshot_type="full",
        collected_at="x", measurement_json={},
    ))
    with pytest.raises(IntegrityError):
        await db_session.flush()
