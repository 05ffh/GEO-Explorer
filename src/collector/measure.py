"""测量编排（spec 3.0【1 测量】）：读定位 → 生成命中层题 → 提问 → 命中判定。

ask_fn 是可注入的提问函数（async，question -> AI 回答文本），
测试时 mock，真实诊断时接四平台 adapter（复用 PlatformRateLimiter 限流）。
"""
from __future__ import annotations

import asyncio

from src.collector.competitor import select_primary
from src.collector.hit_judge import prefill
from src.collector.judgment import LAYER_ATTRIBUTION, LAYER_HIT, new_judgment
from src.collector.question_builder import build_questions


def build_platform_questions(brand: str, city: str, positioning: dict, system: str = "A") -> list[dict]:
    """生成单平台**全量**题（命中+归因），measure_platform 与复测收敛的指纹共用——单一来源防指纹漂移。

    竞对解析（主竞对 / 场景竞对）收敛在这里，remeasure 算指纹必须和实际采集同一套题。
    `system` 透传 build_questions（两套体系，spec 3.1.2）：A=通用命中层 / B=甲方指定命中层。
    """
    tier = positioning.get("tier")
    competitors = positioning.get("competitors") or []
    personas = positioning.get("personas") or {}
    client_guest = max(personas, key=personas.get) if personas else None
    if competitors and isinstance(competitors[0], str):
        competitor = competitors[0]  # 兼容旧简单名单
    else:
        primary = select_primary(competitors, tier, client_adr=positioning.get("adr"), client_guest=client_guest)
        competitor = primary["name"] if primary else (competitors[0].get("name") if competitors else None)
    return build_questions(brand, city, tier=tier, competitor=competitor,
                           scenario_competitors=positioning.get("scenario_competitors") or {},
                           system=system)

_AGENT_TASK = (
    "命中语义判定：判 recommendation（推荐/提及/排除/未出现）+ scene（子场景维度/值/子场景内排名/数）"
    " + referred_content + has_hotel_recommendations + hotels_recommended[推荐名单] + hotels_mentioned[提及名单]。"
    "档位/竞对（same_tier_pushed/answer_tier_distribution）由系统查 brand_domains 派生，子 agent 不判。"
)

_ATTRIBUTION_TASK = (
    "归因劣势提取（P1-②）：读甲方 vs 竞品 对比回答，提取甲方劣势维度"
    "（服务/设施/价格/位置/品牌/其他，AI 认为甲方不如竞品/推竞品不推甲方的点），每条带证据（AI 原话引用）。"
)


async def measure_platform(
    brand: str,
    city: str,
    brand_en: str | None,
    positioning: dict,
    ask_fn,
    platform: str = "",
    layers: set[str] | None = None,
    qids: set[str] | None = None,
    system: str = "A",
) -> dict:
    """单平台测量：读定位 → 生成命中层+归因层题 → 提问 → 判定。

    positioning = collection_run.positioning_json（tier/competitors/scenario_competitors）。
    `system`（spec 3.1.2）：A=通用命中层 25 题 / B=甲方指定命中层（client 文件）；命中层进命中率分母；
    归因层 10 题两套共用（5 对比"选哪家为什么" + 5 平衡"各自优劣势"，按场景匹配竞对点名头号对手），
    不进命中率分母（compute_platform_rate 过滤 layer=attribution，spec 3.1.1）。

    layers：只采集指定层（如 {"attribution"}）——复测收敛分层用（稳定平台 DS/Kimi 只重采归因层，
    命中层沿用第 1 轮）；None = 全采。**指纹仍按全题集算**（build_questions 全集），
    只过滤"提问/判定"子集，保证同基线指纹不变（spec 复测收敛设计）。
    返回 {"questions", "judgments"}，judgments 每项 = judge 结果 + question/question_id。
    """
    questions = build_platform_questions(brand, city, positioning, system=system)
    if layers:
        questions = [q for q in questions if q["layer"] in layers]
    if qids:
        questions = [q for q in questions if q["id"] in qids]
    # ③ 归因题接线（2026-09-10）：命中层 + 归因层都问——归因层对比题（甲方 vs 主竞对）
    # 采"为什么推他不推我"的原始证据，不进命中率分母（spec 3.1.1）
    _LAYER_OF = {"hit": LAYER_HIT, "attribution": LAYER_ATTRIBUTION}

    async def _ask_one(q):
        # A-1.5 schema 骨架：语义字段（recommendation/scene/...）默认 None 待子 agent 判（A-2）
        j = new_judgment(q["id"], _LAYER_OF[q["layer"]], platform, question=q["question"])
        try:
            answer = await ask_fn(q["question"])
            j["answer"] = answer  # 存回答原文：子 agent 语义判定的依据
            p = prefill(answer, brand, brand_en)
            # 系统预判辅助（A-1）：形态 / 是否简单列表 / 甲方出现 / 位置参考
            j.update({
                "answer_form": p["answer_form"],
                "simple": p["simple"],
                "client_present": p["client_present"],
                "rank": p.get("client_rank"),
                "brand_count": p.get("item_count"),
            })
        except Exception as e:
            j["needs_agent"] = False
            j["reason"] = "error"
            j["error"] = str(e)
        return j

    # 平台内并发提问（ask_fn 内置限流 acquire_or_wait 控制并发，如 2-8）
    judgments = list(await asyncio.gather(*[_ask_one(q) for q in questions]))

    # 主 agent 介入点：命中层=语义判定（子 agent）；归因层=劣势提取（子 agent，P1-②）
    agent_tasks = [
        {
            "question_id": j["question_id"],
            "question": j["question"],
            "task": _AGENT_TASK if j["layer"] == LAYER_HIT else _ATTRIBUTION_TASK,
        }
        for j in judgments if j.get("needs_agent")
    ]

    return {
        "questions": questions,
        "judgments": judgments,
        "agent_tasks": agent_tasks,
        # 主 agent 介入点②：地区语境复核（judge 只看品牌名，别地区同名品牌会误判命中）
        "agent_notes": f"地区语境复核：judge 只看品牌名，AI 提「别地区的{'' if brand_en else brand}」可能误判命中；主 agent 复核所有 hit=True 的题，确认甲方是否在「{city}」语境被提到",
    }
