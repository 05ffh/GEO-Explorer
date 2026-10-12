"""judgment 结构 schema（A-1.5，spec 11.9 命中判定重构）。

judgment = 对一道题 AI 回答的判定记录，是**多处消费的契约**：
- A-2 子 agent 判定工具：generate 出骨架（new_judgment + prefill 合并），子 agent 填语义字段，apply 写回
- A-3 hit_rate 重构：读 hit/recommendation/scene/has_hotel_recommendations/same_tier_pushed/answer_tier_distribution
- 平台画像聚合：跨题聚合 answer_tier_distribution
- 内容资产聚合：跨题聚合 referred_content
- A-4 迁移/校准：旧 judgment → 新结构；100 条人工审核对齐（scene 粒度）

judgment 完整字段（v2，2026-09-04）：
{
  # 标识
  "question_id": str, "layer": "hit|attribution", "platform": str,
  # 保留（measure 写，子 agent 判定的依据）
  "question": str, "answer": str,
  # 系统预判（A-1 prefill 产出，A-2 合并）
  "answer_form": "list|prose|table", "simple": bool|None, "client_present": bool,
  # 语义判定（子 agent 填，spec 11.9 五字段语义 + 推荐/提及名单拆分，2026-09-10 修正）——
  # recommendation 全子 agent 判；档位/竞对（same_tier_pushed/answer_tier_distribution）系统派生，子 agent 不判
  "recommendation": "recommend|mention|exclude|absent",
  "scene": {"dim": SCENE_DIM, "val": str, "rank_in_scene": int, "in_scene_count": int} | None,
  "referred_content": [str, ...],
  "has_hotel_recommendations": bool|None,
  "hotels_recommended": [str, ...],   # 推荐名单：AI 作为候选/推荐对象列出的酒店（真劣势/同档判定唯一输入）
  "hotels_mentioned": [str, ...],     # 提及名单：AI 顺嘴提到的酒店（背景/范围说明，不进推荐判定）
  # 派生（apply 算，系统查 brand_domains）
  "same_tier_pushed": bool|None,
  "answer_tier_distribution": {档位: 数} | None,
  "hit": bool|None, "judge_source": "system|agent", "reason": str|None,
  # 兼容（measure/finalize_measurement 仍用）
  "needs_agent": bool, "rank": int|None, "brand_count": int|None,
}

# ⚠️ 口径：命中/首推/均排一律用 scene.rank_in_scene（子场景内排名，spec 11.9 新口径）；
# 顶层 "rank"/"brand_count" 是 A-1 简单列表的旧位置参考（prefill.client_rank/item_count），
# 仅供子 agent 判定参考，A-3 计算时不得用顶层 rank 当命中排名。
# scene 复合场景局限：AI 分块常是复合的（"市区高端商务"= 区域+档位+话题），子 agent 只记
# 一个主维度（最贴合甲方语境的），跨题聚合按 dim 分桶、val 归并（聚合层处理，A-3 之后）。
"""
from __future__ import annotations

# 命中层 / 归因层（spec 3.1.1：归因层不进命中率分母）
LAYER_HIT = "hit"
LAYER_ATTRIBUTION = "attribution"
LAYER_VALUES = (LAYER_HIT, LAYER_ATTRIBUTION)

# recommendation 二分四值（spec 11.9 决策点 1：hit = recommend）。
# 语义判定，子 agent 判——"被列入列表"不等于"被推荐"（排最后的顺带项 = mention，
# 2026-09-04 豆包 Q1 甲方仅结尾顺带一句、人工判未命中的教训）。
RECOMMEND = "recommend"    # AI 明确推荐甲方（含明确"首选/推荐"语境）
MENTION = "mention"        # 提到但非推荐（"也不错，但更推荐 X"）
EXCLUDE = "exclude"        # 明确排除/指出不合适（"虽五星但早餐另付费"）
ABSENT = "absent"          # 完全没提
RECOMMENDATION_VALUES = (RECOMMEND, MENTION, EXCLUDE, ABSENT)

# scene 维度（spec 11.9 决策点 2：scene 结构化 维度×值，跨题可聚合）
SCENE_DIM_REGION = "region"        # 区域：鼓楼区 / 福州站附近
SCENE_DIM_TIER = "tier"            # 档位：高端 / 豪华
SCENE_DIM_TOPIC = "topic"          # 话题/场景：温馨出片 / 商务会客
SCENE_DIM_CATEGORY = "category"    # 品类：温泉度假 / 设计精品
SCENE_DIM_BUDGET = "budget"        # 预算档：百元 / 200-300（豆包常按预算分块）
SCENE_DIMS = (SCENE_DIM_REGION, SCENE_DIM_TIER, SCENE_DIM_TOPIC, SCENE_DIM_CATEGORY, SCENE_DIM_BUDGET)

# 回答形态（A-1 prefill 产出）
ANSWER_FORM_LIST = "list"
ANSWER_FORM_PROSE = "prose"
ANSWER_FORM_TABLE = "table"
ANSWER_FORMS = (ANSWER_FORM_LIST, ANSWER_FORM_PROSE, ANSWER_FORM_TABLE)


def new_judgment(
    question_id: str,
    layer: str,
    platform: str,
    question: str = "",
    answer: str = "",
) -> dict:
    """生成 judgment 骨架（A-2 generate 用）：语义字段默认 None 待子 agent 填。

    系统预判（prefill）与位置派生由 A-2 合并（本模块不耦合 prefill——它属 A-1）。
    默认 needs_agent=True：recommendation 是语义判定，不默认。error 情况由调用方改
    needs_agent=False + reason=error。
    """
    return {
        "question_id": question_id,
        "layer": layer,
        "platform": platform,
        "question": question,
        "answer": answer,
        "answer_form": None,
        "simple": None,
        "client_present": False,
        "recommendation": None,
        "scene": None,
        "same_tier_pushed": None,
        "answer_tier_distribution": None,
        "referred_content": [],
        "has_hotel_recommendations": None,
        "hotels_recommended": [],
        "hotels_mentioned": [],
        "hit": None,
        "judge_source": "agent",
        "reason": None,
        "needs_agent": True,
        "rank": None,
        "brand_count": None,
        # 归因层专用（P1-②）：子 agent 劣势提取结果，仅 layer=attribution 的 judgment 有值
        "attribution_result": None,
    }


_HIT_SPEC = (
    "命中语义判定（spec 11.9）：对一道命中层题（不点名甲方），判 AI 回答是否推荐甲方、在哪个子场景、排名第几。\n"
    "**甲方** = 本清单诊断单元的品牌（输入 json 的 city/client_tier 定位，如福州高端=香格里拉）；"
    "识别推荐名单里甲方用其全名（hotels_recommended 出现甲方全名即被推荐）。\n"
    "输出每题（recommendation 与 scene 由子 agent 判；same_tier_pushed/answer_tier_distribution 系统派生，子 agent 不判）：\n"
    "1. recommendation：AI 是否推荐甲方——recommend=AI 明确推荐（列入推荐名单/建议选择/首选）；"
    "mention=提到但非推荐（\"也不错，但更推荐 X\"）；exclude=明确不推荐/排除；absent=完全没提。"
    "**命中 = recommend**（spec 11.9 决策点 1：hit = AI 主动推荐，不是位置截断）。\n"
    "2. scene（**recommend 时必填**，其他状态置 null）：\n"
    "   - dim ∈ region(区域:鼓楼区/福州站附近) / tier(档位:高端/豪华) / topic(话题场景:温馨出片/商务会客) "
    "/ category(品类:温泉度假/设计精品) / budget(预算档:千元/百元)——AI 按什么分块给甲方归属最贴合的主维度\n"
    "   - val = 子场景名（简洁，跨题可归并）\n"
    "   - rank_in_scene = 甲方在该子场景内排名（唯一=1），in_scene_count = 该子场景推荐酒店数\n"
    "   **⚠️ 结构是 dim+val，不是 name**（2026-09-18 修 spec 11.9 文档漂移：apply_patch 校验 scene.dim 枚举）\n"
    "3. referred_content：AI 提到甲方的具体内容（资产/事实，如\"江南灶米其林一星\"\"步行3分钟南门兜\"），甲方没被提 → []。\n"
    "4. hotels_recommended：AI 作为候选/推荐对象列出的酒店全名（含甲方）——**必须完整列出**（系统据此算同档竞对/真劣势/相对可见度，漏列会漏判）；"
    "hotels_mentioned：顺嘴提到的（背景，不判推荐）。\n"
    "5. has_hotel_recommendations：AI 是否推荐了任何酒店（含民宿/青旅/公寓）；回答无酒店推荐 → false。\n"
    "**判定铁律**：\n"
    "① 推荐列表内靠后 = recommend（排名不降级 mention）；exclude 只用于明确不推荐（推荐+缺点 ≠ exclude）。\n"
    "② 备选区域唯一列出 = 推荐：AI 分层（\"最推荐/备选/如果住 X\"）每层推荐列表都算推荐，甲方在任一推荐列表 = recommend。\n"
    "③ 自洽：recommendation=mention/exclude/absent 时 scene 必须 null（rank 隐含被推荐）。\n"
    "④ scene 用 AI 实际分块结构给名（禁题目筛选条件当场景）；rank_in_scene=子场景内排名（唯一=1），非子场景序号。"
    "AI 分块常是复合的（\"市区高端商务\"=区域+档位+话题），只记一个主维度（最贴合甲方语境的）。\n"
    "⑤ 命中独立于竞争关系与区域档位：甲方被列入推荐列表 = recommend，即使同列表其他酒店档位低于甲方。"
    "真劣势只在 absent + 同档竞对被推（same_tier_pushed）时成立，但 same_tier_pushed 由系统派生。\n"
)
