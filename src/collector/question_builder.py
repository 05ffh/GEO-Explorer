"""问题实例化 — 把 question_templates.yaml 的模板填变量，变成问四个 AI 平台的具体问题。

与 query_builder.py 的区别：query_builder 生成搜索词喂搜索引擎（P2 采 GT），
本模块生成问题喂 AI 平台（P3 测命中率）。可选片段用 [方括号] 标记，内含变量缺值时整段删除。
"""
from __future__ import annotations

import logging
import re

from src.collector.tier import TIER_BUDGET, TIER_WORD
from src.industry_knowledge.loader import get_knowledge_loader

logger = logging.getLogger(__name__)

_OPTIONAL = re.compile(r"\[([^\]]*)\]")

# 完整店名词：归因题点名竞对时，已带这类后缀视为"完整店名"（一般已含地区），不再补 {城市}
_REGION_FULL_NAME_TOKENS = ("酒店", "饭店", "宾馆", "大厦", "度假", "中心", "山庄", "民宿", "客栈")


def _qualify_region(name: str, city: str) -> str:
    """归因题点名甲方/竞对时补地区限定（2026-09-13 用户发现）：对比题不点地区 → AI 回答漂移，
    拿不到有价值的归因内容。已含城市名或已是完整店名（如"福建外贸中心悦华酒店"）不动，裸品牌名补 {城市}。
    # ponytail: "省前缀+完整店名"靠完整店名词豁免；若竞对名形态更杂，应改在 write_competitor
    # 入口统一规范化店名（含地区），此处只做轻量兜底。
    """
    if not name or not city:
        return name
    c = city.rstrip("市")
    if c in name:
        return name
    if any(t in name for t in _REGION_FULL_NAME_TOKENS):
        return name
    return f"{city}{name}"


def build_questions(
    brand: str,
    city: str,
    tier: str | None = None,
    competitor: str | None = None,
    attraction: str | None = None,
    budget: str | None = None,
    scenario_competitors: dict | None = None,
    system: str = "A",
) -> list[dict]:
    """实例化命中层 + 归因层问题（spec 3.1.2 两套体系）。

    `system`：
      - **"A"（默认）**：甲方未指定关键词 → 命中层用内置通用模板（`question_templates.yaml`，25 题变量化）。
      - **"B"**：甲方指定关键词 → 命中层用甲方专属预设（`question_templates_client.yaml`，硬编码）；
        **归因层两套共用** `question_templates.yaml` 的归因层（10 题）。

    返回 [{"id", "persona", "slot", "layer", "question"}, ...]。
    - 档位词题（含 {档次词}）：tier 未定则跳过（定位失败，问不出正确档位）——仅体系A 命中层含此。
    - 归因层题：竞品未识别则跳过（无对比对象）。
    - **场景匹配竞对（P1-②，2026-09-10）**：scenario_competitors = {场景(persona): 竞对名}，
      归因题按该场景头号对手注入（从最终确认竞对里选）；该场景无映射回退单主竞对 competitor。
    """
    tier_word = TIER_WORD.get(tier) if tier else None
    if budget is None and tier:
        budget = TIER_BUDGET.get(tier)  # 未显式传预算时，从档位推导价格带上限
    if not brand or not city:
        raise ValueError("brand 和 city 必填（诊断单元 = 品牌 + 地区）")
    values = {
        "城市": city,
        "档次词": tier_word,
        "景点": attraction,
        "预算": budget,
        "甲方": brand,
        "竞品": competitor,
    }

    kb = get_knowledge_loader()
    if system == "B":
        # 体系B：命中层 = 甲方指定（client 文件）；归因层共用体系A 文件的归因层
        items = list(kb.load_category("question_templates_client")) + [
            it for it in kb.load_category("question_templates")
            if it.get("layer", "hit") == "attribution"
        ]
    else:
        items = kb.load_category("question_templates")

    questions: list[dict] = []
    for item in items:
        tmpl = item["template"]
        layer = item.get("layer", "hit")

        if "{档次词}" in tmpl and tier_word is None:
            logger.warning("档位未定，跳过档位词题 %s", item["id"])
            continue
        item_values = values
        if layer == "attribution":
            comp = (scenario_competitors or {}).get(item.get("persona")) or competitor
            if not comp:
                logger.warning("竞品未识别，跳过归因题 %s", item["id"])
                continue
            # 归因题点名甲方+竞对都带地区限定（2026-09-13）：否则 AI 对比回答漂移、归因无价值
            item_values = {
                **values,
                "甲方": _qualify_region(brand, city),
                "竞品": _qualify_region(comp, city),
            }

        questions.append({
            "id": item["id"],
            "persona": item.get("persona"),
            "slot": item.get("slot"),
            "layer": layer,
            "question": _instantiate(tmpl, item_values),
        })
    return questions


def fingerprint(questions: list[dict]) -> list[str]:
    """问法指纹：排序后的 "id::question" 列表。

    基线变更检测的依据——问法集（题目 id + 实例化后文本）任一变化指纹即变。
    存进 measurement_json["question_fingerprint"]，run_measure 用它判断本次测量
    属于现有 run 的基线（复用，快照累积）还是新基线（新开 run + 复制 P2）。
    """
    return sorted(f"{q['id']}::{q['question']}" for q in questions)


def _instantiate(template: str, values: dict) -> str:
    """填变量。可选片段 [..] 内变量缺值则删整段，否则替换变量并保留。"""
    def _optional(m: re.Match) -> str:
        seg = m.group(1)
        for key, val in values.items():
            if f"{{{key}}}" in seg and not val:
                return ""
        return seg

    template = _OPTIONAL.sub(_optional, template)
    for key, val in values.items():
        if val is not None:
            template = template.replace(f"{{{key}}}", str(val))
    return template
