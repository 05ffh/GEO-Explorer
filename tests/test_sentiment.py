"""负面率计算测试：否定命中、空文本、URL 去重、分母为 0、写结果环环相扣。"""

import pytest

from src.collector.sentiment import classify_negative, combine_negative_rate, compute_negative_rate
from src.collector.gt_entry import create_collection_run, get_or_create_brand, write_sentiment
from src.models.organization import Organization


def test_classify_negative_hit():
    hits = classify_negative("房间有异味，床单脏")
    themes = {h.theme for h in hits}
    assert "hygiene" in themes
    assert all(not h.negated for h in hits)  # 无否定词 → 不标 negated


def test_classify_negative_negation_signal():
    hits = classify_negative("房间无异味")
    hygiene = [h for h in hits if h.theme == "hygiene"]
    assert hygiene
    assert hygiene[0].negated is True


def test_classify_negative_empty():
    assert classify_negative("") == []


def test_classify_negative_rating_summary_suppressed():
    # 评分摘要/好评页（评分维度 + 无强负面词）→ 不误判（2026-09-01 细筛优化）
    assert classify_negative("环境和清洁度 8.8 设施 8.4 位置 8.6 评分 5/5 惊艳") == []
    assert classify_negative("超棒 4.7/5 卫生 4.8 服务 4.7 推荐入住") == []
    # 但含强负面词（辱骂）→ 不抑制，正常分类
    hits = classify_negative("评分 1 星 辱骂 押金不退")
    assert {h.theme for h in hits} == {"service"}


def test_combine_negative_rate_8_2():
    assert combine_negative_rate(0.0, 0.0) == 0.0
    assert combine_negative_rate(0.5, 0.5) == 0.5
    assert combine_negative_rate(0.1, 0.2) == round(0.8 * 0.1 + 0.2 * 0.2, 4)
    assert combine_negative_rate(0.0, 1.0) == 0.2  # 门店 0 负面时，品牌 100% 只占 0.2


def test_compute_negative_rate_dedup_and_zero():
    assert compute_negative_rate([])["rate"] == 0.0
    results = [
        {"url": "https://a.com/1", "snippet": "态度差"},
        {"url": "https://a.com/1", "snippet": "态度差"},  # 重复 URL 去重
        {"url": "https://a.com/2", "snippet": "房间很好"},
        {"url": "https://a.com/3", "snippet": "态度差 且 床单脏"},  # 多主题
    ]
    out = compute_negative_rate(results)
    assert out["total"] == 3          # 去重后
    assert out["negative_count"] == 2
    assert out["rate"] == round(2 / 3, 4)
    assert out["themes"] == {"service": 2, "hygiene": 1}


@pytest.mark.asyncio
async def test_write_sentiment(db_session):
    org = Organization(name="测试机构")
    db_session.add(org)
    await db_session.flush()
    brand = await get_or_create_brand(db_session, "香格里拉", org.id)
    run = await create_collection_run(db_session, org.id, brand.id, "广州", None)
    assert run.sentiment_json == {}

    sentiment = {
        "store_level": {"total": 10, "negative_count": 1, "rate": 0.1, "themes": {"service": 1}},
        "brand_level": {"total": 5, "negative_count": 0, "rate": 0.0, "themes": {}},
    }
    await write_sentiment(db_session, run.id, sentiment)
    assert run.sentiment_json == sentiment


@pytest.mark.asyncio
async def test_write_sentiment_preserves_themes_on_finalize(db_session):
    """主 agent 终判（write_sentiment 覆盖 rate/negative_count/status）保留 themes/total（深合并）。"""
    org = Organization(name="终判保留")
    db_session.add(org)
    await db_session.flush()
    brand = await get_or_create_brand(db_session, "香格里拉", org.id)
    run = await create_collection_run(db_session, org.id, brand.id, "福州", None)
    await db_session.flush()

    # 粗筛落库（带 themes）
    await write_sentiment(db_session, run.id, {
        "store_level": {"rate": 0.1286, "total": 70, "negative_count": 9,
                        "themes": {"service": 7, "hygiene": 2}, "status": "preliminary"},
    })
    # 主 agent 终判：只改 rate/negative_count/status
    await write_sentiment(db_session, run.id, {
        "store_level": {"rate": 0.10, "negative_count": 7, "status": "confirmed"},
    })
    s = run.sentiment_json["store_level"]
    assert s["rate"] == 0.10 and s["status"] == "confirmed"
    assert s["total"] == 70 and s["themes"] == {"service": 7, "hygiene": 2}  # themes 保留
