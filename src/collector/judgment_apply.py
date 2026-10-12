"""judgment apply（A-2）：把子 agent 判定回填 measurement_json。

职责分工（spec 11.9 评审重捋 + 2026-09-10 推荐/提及拆分）：子 agent 只做**语义识别**
（recommendation / scene / referred_content / has_hotel_recommendations /
hotels_recommended[推荐名单] / hotels_mentioned[提及名单]）；
**档位派生**（answer_tier_distribution）由系统查 brand_domains 完成——子 agent 不靠常识判档位
（洲际=高端这类查表，确定性系统做，避免子 agent 凭感觉误判）。**真劣势锚定（same_tier_pushed）
不在 apply 阶段派生**——由 close_measurement 用钉住竞对（主/次）名匹配重算（apply 无竞对清单，
seal 处唯一派生）；只读**推荐名单**，提及名单只作背景、不触发真劣势。
"""
from __future__ import annotations

from src.collector.judgment import ABSENT, EXCLUDE, LAYER_ATTRIBUTION, MENTION, RECOMMEND, RECOMMENDATION_VALUES, SCENE_DIMS
from src.collector.tier import get_brand


def derive_tier_distribution(hotels: list[str], city: str | None = None) -> dict[str, int]:
    """酒店名单 → 档位分布（系统查 brand_domains）。

    表外酒店（get_brand 返回 None）不计入——档位未知不参与画像/same_tier 判定。
    """
    dist: dict[str, int] = {}
    for name in hotels or []:
        brand = get_brand(name, city=city)
        if brand:
            tier = brand["tier"]
            dist[tier] = dist.get(tier, 0) + 1
    return dist


def generate_pending(m: dict, include_all: bool = False) -> dict:
    """输出待判清单（含题目+回答+系统预判）。默认仅 recommendation=None 的题（error 跳过）。

    include_all=True（rejudge 场景）：全部非 error 题都输出，并附 current（当前语义判定值）——
    子 agent 复核/修正推荐·提及名单拆分，apply(force) 回填。spec ⑫ rejudge 工作流。
    """
    out: dict = {"platforms": {}}
    for p, info in m.get("platforms", {}).items():
        pend = {}
        for j in info.get("judgments", []):
            # 归因题走 finalize_attribution/finalize_v4（劣势提取），不混进命中判定
            # （2026-09-13 对抗审查：归因题 recommendation=None 会被误当待判命中题漏进清单）
            if j.get("layer") == LAYER_ATTRIBUTION:
                continue
            if j.get("reason") == "error":
                continue
            if not include_all and j.get("recommendation") is not None:
                continue
            item = {
                "question": j.get("question", ""),
                "answer": j.get("answer", ""),
                "prefill": {
                    "answer_form": j.get("answer_form"),
                    "simple": j.get("simple"),
                    "client_present": j.get("client_present"),
                    "rank": j.get("rank"),
                    "brand_count": j.get("brand_count"),
                },
            }
            if include_all and j.get("recommendation") is not None:
                item["current"] = {
                    "recommendation": j.get("recommendation"),
                    "scene": j.get("scene"),
                    "referred_content": j.get("referred_content"),
                    "has_hotel_recommendations": j.get("has_hotel_recommendations"),
                    "hotels_recommended": j.get("hotels_recommended"),
                    "hotels_mentioned": j.get("hotels_mentioned"),
                }
            pend[j["question_id"]] = item
        if pend:
            out["platforms"][p] = pend
    return out


def apply_patch(m: dict, patch: dict, city: str | None, client_tier: str | None, force: bool = False) -> int:
    """把子 agent 判定写回 judgment：六字段 + needs_agent=False + 系统派生档位 + 派生 hit。

    返回回填题数。防御（对抗审查 2026-09-04）：
    - recommendation / scene.dim 枚举校验，非法跳过并告警
    - has_hotel_recommendations 缺失（None）→ 跳过并告警（分母净化关键字段不留乐观默认，
      避免"AI 只答区域"的题漏填被当有效题稀释命中率）
    - 已判题（recommendation 非 None）默认跳过，防重复 apply 静默覆盖；force=True 才重判
    """
    applied = 0
    for p, info in m.get("platforms", {}).items():
        p_patch = patch.get(p, {})
        for j in info.get("judgments", []):
            qid = j.get("question_id")
            if j.get("layer") == LAYER_ATTRIBUTION:
                continue  # 归因题不走命中判定（防御：即使 patch 含归因题也跳过）
            val = p_patch.get(qid)
            if not val:
                continue
            if j.get("recommendation") is not None and not force:
                print(f"  跳过: [{p}] {qid} 已判定，需 force=True 重判")
                continue
            reco = val.get("recommendation")
            if reco not in RECOMMENDATION_VALUES:
                print(f"  警告: [{p}] {qid} recommendation 非法 {reco!r}，跳过")
                continue
            scene = val.get("scene")
            if scene and scene.get("dim") not in SCENE_DIMS:
                print(f"  警告: [{p}] {qid} scene.dim 非法 {scene.get('dim')!r}，跳过")
                continue
            # 自洽硬约束（2026-09-05）：非 recommend 却给 scene.rank_in_scene → 判定内部矛盾（
            # rank≥1 = 甲方在子场景被推荐 = 必须 recommend），拒绝防污染
            if reco in (MENTION, EXCLUDE, ABSENT) and (scene or {}).get("rank_in_scene", 0) >= 1:
                print(f"  警告: [{p}] {qid} {reco} 与 scene.rank_in_scene≥1 矛盾（rank 隐含被推荐），跳过")
                continue
            if val.get("has_hotel_recommendations") is None:
                print(f"  跳过: [{p}] {qid} 缺 has_hotel_recommendations（必填），未回填")
                continue
            # 子 agent 语义字段（hotels_recommended 名单也落库：竞对命中率聚合的输入）
            j["recommendation"] = reco
            j["scene"] = scene
            j["referred_content"] = val.get("referred_content") or []
            j["has_hotel_recommendations"] = val["has_hotel_recommendations"]
            j["hotels_recommended"] = val.get("hotels_recommended") or []   # 推荐名单（同档判定输入）
            j["hotels_mentioned"] = val.get("hotels_mentioned") or []       # 提及名单（背景，不进判定）
            # 系统派生档位（子 agent 报名单，系统查 brand_domains——不靠子 agent 常识判档位）
            dist = derive_tier_distribution(j["hotels_recommended"], city=city)
            j["answer_tier_distribution"] = dist
            # same_tier_pushed（真劣势锚定）由 close_measurement 用钉住竞对名匹配派生——
            # apply 阶段无竞对清单（seal 处唯一派生，spec ⑫ 收口）
            j["same_tier_pushed"] = None
            # 派生 hit（spec 11.9 决策点 1：hit = recommend）
            j["hit"] = reco == RECOMMEND
            j["needs_agent"] = False
            j["judge_source"] = "agent"
            j["reason"] = "agent_finalized"
            applied += 1
    return applied
