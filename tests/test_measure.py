"""测量编排测试：读定位 → 生成命中层题 → mock 提问 → 判定。"""
import pytest

from src.collector.measure import measure_platform


async def _ask(answers: dict):
    async def fn(question: str) -> str:
        return answers.get(question, "1. 其他酒店\n2. 别的酒店")
    return fn


@pytest.mark.asyncio
async def test_measure_hit_layer_only():
    # 命中层 25 题（tier 有值，无竞品 → 归因层跳过）
    positioning = {"tier": "高端", "competitors": []}
    ask = await _ask({})
    result = await measure_platform("香格里拉", "福州", None, positioning, ask)
    assert len(result["questions"]) == 25
    assert all(q["layer"] == "hit" for q in result["questions"])


@pytest.mark.asyncio
async def test_measure_judgments_flow():
    # 列表式回答含甲方 → judgment 记录系统预判（simple 列表 + 甲方位置参考），语义判定待子 agent
    positioning = {"tier": "高端", "competitors": []}
    answers = {
        "福州出差住哪家酒店方便": "1. 香格里拉\n2. 希尔顿\n3. 万豪",
    }
    result = await measure_platform("香格里拉", "福州", None, positioning, await _ask(answers))
    first = result["judgments"][0]
    assert first["question_id"] == "hit_business_generic"
    assert first["answer_form"] == "list"
    assert first["simple"] is True
    assert first["client_present"] is True
    assert first["rank"] == 1           # 位置参考（prefill.client_rank）
    assert first["recommendation"] is None   # 语义判定待子 agent（A-2）
    assert first["needs_agent"] is True


@pytest.mark.asyncio
async def test_measure_natural_paragraph_marks_agent():
    positioning = {"tier": "高端", "competitors": []}
    answers = {
        "福州出差住哪家酒店方便": "推荐希尔顿、万豪，还有香格里拉也不错",
    }
    result = await measure_platform("香格里拉", "福州", None, positioning, await _ask(answers))
    assert result["judgments"][0]["needs_agent"] is True
    assert result["judgments"][0]["answer_form"] == "prose"
    # 新口径：命中语义判定全子 agent → agent_tasks 覆盖全部命中层题
    assert len(result["agent_tasks"]) == 25
    assert result["agent_tasks"][0]["question_id"] == "hit_business_generic"
    # 介入点②：地区语境复核提示
    assert "地区语境复核" in result["agent_notes"]
    assert "福州" in result["agent_notes"]


@pytest.mark.asyncio
async def test_measure_tier_none_skips_tier_questions():
    # tier=None → 档位词题跳过，命中层 20 题
    positioning = {"tier": None, "competitors": []}
    result = await measure_platform("香格里拉", "福州", None, positioning, await _ask({}))
    assert len(result["questions"]) == 20


@pytest.mark.asyncio
async def test_measure_structured_competitors_emits_attribution():
    # ③ 归因题接线（2026-09-10）：有竞对 → 命中层 25 + 归因层 5 对比题（甲方 vs 主竞对）
    # 归因层不进命中率分母（compute_platform_rate 过滤 layer=attribution）
    positioning = {"tier": "高端", "competitors": [
        {"name": "福州世茂洲际酒店", "ring": "核心", "tier": "高端", "adr": 700},
        {"name": "福州三迪希尔顿酒店", "ring": "近邻", "tier": "高端", "adr": 850},
    ]}
    result = await measure_platform("香格里拉", "福州", None, positioning, await _ask({}))
    assert len(result["questions"]) == 35                      # 25 命中 + 10 归因（5 对比 + 5 平衡）
    assert sum(q["layer"] == "hit" for q in result["questions"]) == 25
    assert sum(q["layer"] == "attribution" for q in result["questions"]) == 10
    # 归因题点名主竞对（select_primary 取核心圈同档 → 世茂洲际）
    attr_q = [q for q in result["questions"] if q["layer"] == "attribution"]
    assert any("世茂洲际" in q["question"] for q in attr_q)


@pytest.mark.asyncio
async def test_measure_attribution_judgments_layer_and_task():
    # 归因层 judgment layer=attribution，agent_task 用劣势提取（非命中判定）
    positioning = {"tier": "高端", "competitors": ["福州世茂洲际酒店"]}
    result = await measure_platform("香格里拉", "福州", None, positioning, await _ask({}))
    attr_js = [j for j in result["judgments"] if j["layer"] == "attribution"]
    assert len(attr_js) == 10
    assert all(j["needs_agent"] is True for j in attr_js)
    attr_task = next(t["task"] for t in result["agent_tasks"]
                     if t["question_id"] in {j["question_id"] for j in attr_js})
    assert "劣势" in attr_task                          # 归因层任务是劣势提取


@pytest.mark.asyncio
async def test_measure_legacy_string_competitors_ok():
    # 兼容旧简单名单（纯字符串列表）→ 命中+归因照常，不 crash
    positioning = {"tier": "高端", "competitors": ["福州希尔顿"]}
    result = await measure_platform("香格里拉", "福州", None, positioning, await _ask({}))
    assert len(result["questions"]) == 35


@pytest.mark.asyncio
async def test_measure_guest_mix_from_personas_ok():
    # personas 主客群传入 select_primary（客群匹配），不 crash，命中+归因照常
    positioning = {"tier": "高端", "personas": {"商务差旅": 3, "亲子家庭": 1}, "competitors": [
        {"name": "福州世茂洲际酒店", "ring": "核心", "tier": "高端", "adr": 700,
         "guest_mix": ["商务差旅"], "ai_cooccurrence": 16},
    ]}
    result = await measure_platform("香格里拉", "福州", None, positioning, await _ask({}))
    assert len(result["questions"]) == 35
