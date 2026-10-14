"""舆情-only 刷新（轻路径）单测：只重采舆情 → 写 sentiment_json(preliminary) + 材料去重落库。"""
import pytest
from sqlalchemy import text

from scripts.refresh_sentiment import refresh_run_sentiment
from src.collector.gt_entry import create_collection_run, get_or_create_brand
from src.models.organization import Organization


@pytest.mark.asyncio
async def test_refresh_run_sentiment_writes_preliminary_and_dedups(db_session):
    org = Organization(name="舆情刷新")
    db_session.add(org)
    await db_session.flush()
    brand = await get_or_create_brand(db_session, "香格里拉", org.id)
    run = await create_collection_run(db_session, org.id, brand.id, "福州", None)
    run.sentiment_json = {"store_level": {"rate": 0.9, "status": "confirmed"}}  # 旧值，应被刷新覆盖

    calls = []

    async def fake_search(q):
        calls.append(q)
        return [{"url": "https://x/1", "title": "差评", "snippet": "设施老旧 投诉", "provider": "tavily"},
                {"url": "https://x/1", "title": "重复URL", "snippet": "投诉", "provider": "doubao_search"},
                {"url": "", "title": "无URL", "snippet": "x", "provider": "websearch"}]

    summary = await refresh_run_sentiment(db_session, run, fake_search)

    assert summary["materials"] > 0 and len(calls) >= 20        # 单档门店级 20 词（体系B）
    assert summary["written"] is True
    # 负面率写回（preliminary），覆盖旧 confirmed
    assert run.sentiment_json["store_level"]["status"] == "preliminary"
    assert 0.0 <= run.sentiment_json["store_level"]["rate"] <= 1.0
    assert "brand_level" not in run.sentiment_json               # 单档：无品牌级
    # 材料落库：每词 3 条但 URL 去重 → 每词落 2 行（https://x/1 + 空URL 1 行）
    rows = (await db_session.execute(
        text("SELECT count(*) FROM search_results WHERE collection_run_id=:r"), {"r": run.id})).scalar()
    assert rows == summary["new_rows"] > 0
    # 空 URL 只落 1 行/词（不被当重复），有 URL 的同 URL 去重
    assert rows < summary["materials"]


@pytest.mark.asyncio
async def test_refresh_sentiment_backend_failure_keeps_old(db_session):
    """两路后端全失败（0 材料）→ 不覆盖已有 confirmed 舆情（防数据丢失）。"""
    org = Organization(name="舆情后端失败")
    db_session.add(org)
    await db_session.flush()
    brand = await get_or_create_brand(db_session, "香格里拉", org.id)
    run = await create_collection_run(db_session, org.id, brand.id, "福州", None)
    run.sentiment_json = {"store_level": {"rate": 0.9, "status": "confirmed"}}

    async def dead_search(q):
        return []                                              # 两路后端全空

    summary = await refresh_run_sentiment(db_session, run, dead_search)
    assert summary["written"] is False
    assert run.sentiment_json["store_level"]["status"] == "confirmed"   # 旧值未被冲毁
