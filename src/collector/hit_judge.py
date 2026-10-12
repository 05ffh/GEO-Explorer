"""命中判定器：判 AI 回答里甲方是否在前 N 位（N=min(8, 品牌数)，spec 决策 7 动态自适应）。

列表式（有序号，如"1. 香格里拉 2. 希尔顿"）→ 确定性解析：按序号分割成项，
数项数 = 品牌数，N=min(8, 项数)，甲方在前 N 项 = 命中。
自然段式（无序号，如"推荐希尔顿、万豪，还有香格里拉"）→ 返回 needs_agent=True，
主 agent 判「提到几个品牌 + 甲方第几个被提到」后回填 hit/rank/brand_count。

命中铁律（spec 3.1）：只有 AI 主动提甲方才算命中；这里只判「提没提 + 排第几」，
「是否点名甲方」由调用方按题目 layer 过滤（归因层不进命中率分母）。
"""
from __future__ import annotations

import re

# 列表标记：数字序号(1. / 1、) / Markdown标题序号(### 1.) / 圆圈序号(①) / 项目符号(- / • / ·)
# 真实 AI 回答常见 "### 1. 香格里拉"（Markdown 标题+序号）和 "- 香格里拉"（项目符号），
# 只认 "1. " 会把它们误判成自然段式 → 漏判命中（2026-08-29 真实测试发现）。
# 2026-09-04 补 markdown 粗体序号「**1. 香格里拉**」——真实 Q6 用粗体序号列推荐，
# 原正则不认 ** 前缀，甲方整段被吞、静默漏判（hit=False 不触发主 agent）。
_LIST_MARKER = re.compile(
    r'(?:^|\n)[ \t]*(?:\*\*)?(?:#{1,6}[ \t]+)?(?:\d+[.、．)）]|[①-⑩]|[-•·][ \t]+)(?:\*\*)?'
)

# Markdown 表格行（| xxx | xxx |）——结构化对比，排名语义需主 agent 判。
# judge 若把它当列表行分割会武断误判（2026-08-29 真实测试发现 Kimi 用表格推荐）。
_TABLE_LINE = re.compile(r'^\s*\|.*\|\s*$', re.MULTILINE)

# 酒店特征词：简单列表（每项以酒店名开头）的判别信号。
# 注意"福州香格里拉"这类纯品牌名不带这些词——由 _is_simple_list 的兜底分支保守处理。
_HOTEL_TERMS = ("大酒店", "酒店", "宾馆", "饭店", "旅馆", "民宿", "客栈", "山庄", "度假", "公寓", "青旅")

# 分块式 item 的标签词：AI 按属性/场景/区域标题 + 描述组织时，item 以这类词开头
# （如"景点密集**：""交通便利**：""市区逛景点首选：""位置："）而非酒店名。
_BLOCK_LABELS = (
    "位置", "优势", "亮点", "适合", "首选", "推荐", "交通", "景点", "吃饭", "商圈",
    "环境", "安静", "价格", "特色", "综合", "亲子", "温泉", "服务", "体验", "便利",
    "氛围", "江景", "湖景", "景观", "私密", "热闹", "网红", "打卡", "出片", "安全",
    "性价比", "老牌", "设施", "房型", "空间", "面积", "隔音", "早餐", "卫生", "停车",
    "追求", "主打", "地处", "紧邻", "毗邻",
)


def _is_simple_list(items: list[str]) -> bool:
    """判断列表是否"简单列表"（每项以酒店名开头）。

    分块式回答（AI 按属性/场景/区域标题组织，2026-09-04 四份 md 审计：DeepSeek Q8
    前 3 项是"景点密集/交通便利/吃饭方便"属性标题，甲方实为"交通便利"块内首推却被
    扁平数成 rank4）也会被 _split_numbered 拆成 items，但其 item 开头是标签词而非
    酒店名——扁平 rank 因标题占位必然错。分块式 → needs_agent，交主 agent 判 scene。
    规则：前 4 个 item 中 ≥2 个含酒店特征词 → 简单列表；否则若 ≥2 个以标签词开头
    → 分块式；都不满足（如纯品牌名短列表"1. 香格里拉 2. 希尔顿"）→ 按简单列表
    保守处理（保 2026-08-29 起的确定性路径，不因启发式误伤）。
    # ponytail: 区域分块式（如"五四路/鼓楼区"区域名 + 块内酒店）可能漏网——区域名
    # 既不匹配标签词也不匹配酒店词，块内酒店凑齐 hotel_hits≥2 会误判 simple。
    # 当前四份 md 未触发有害场景（甲方未出现）；若换地区遇区域分块 + 甲方出现，
    # rank 仍可能错——届时由子 agent 的 scene 判定兜底（A-2），不在此启发式上堆规则。
    """
    head = items[:4]
    hotel_hits = sum(1 for it in head if any(t in it[:16] for t in _HOTEL_TERMS))
    if hotel_hits >= 2:
        return True
    label_hits = sum(1 for it in head if any(t in it[:12] for t in _BLOCK_LABELS))
    return label_hits < 2


def prefill(answer: str, brand_zh: str, brand_en: str | None = None) -> dict:
    """系统预判骨架（2026-09-04，供 A-2 子 agent 判定工具 + judgment 初始字段）。

    返回 {"answer_form", "simple", "client_present", "client_rank", "item_count"}：
    - answer_form: list / prose / table（回答形态）
    - simple: 列表是否"简单列表"（每项以酒店名开头）；非列表为 None
    - client_present: 甲方名字符串是否出现在回答（粗匹配，含子串）
    - client_rank: 简单列表内甲方位置（第几项）；非简单列表/未出现为 None
    - item_count: 列表项数；非列表为 None

    与 judge 的分工：prefill 只做**确定性结构解析**，不产出 hit/rank 语义判定；
    判定（recommendation/scene/同档等）由子 agent 完成。judge 复用 prefill 推导现有返回。
    """
    aliases = [brand_zh] + ([brand_en] if brand_en else [])

    def present(ans: str) -> bool:
        return any(a.lower() in ans.lower() for a in aliases)

    if _is_table(answer):
        return {"answer_form": "table", "simple": None, "client_present": present(answer),
                "client_rank": None, "item_count": None}
    items = _split_numbered(answer)
    if items is None:
        return {"answer_form": "prose", "simple": None, "client_present": present(answer),
                "client_rank": None, "item_count": None}
    if not _is_simple_list(items):
        return {"answer_form": "list", "simple": False, "client_present": present(answer),
                "client_rank": None, "item_count": len(items)}
    rank = None
    for i, item in enumerate(items, start=1):
        if any(a.lower() in item.lower() for a in aliases):
            rank = i
            break
    return {"answer_form": "list", "simple": True, "client_present": present(answer),
            "client_rank": rank, "item_count": len(items)}


def judge(answer: str, brand_zh: str, brand_en: str | None = None) -> dict:
    """判甲方命中 + 排名。

    返回 {"needs_agent", "hit", "rank", "brand_count", "reason"}。
    - 列表式（数字/项目符号）：needs_agent=False，hit/rank/brand_count 确定性给出。
    - 表格/自然段/分块式：needs_agent=True，主 agent 判「品牌数 + 甲方排名」后回填。

    哲学（2026-08-29 真实测试确立）：judge 宁可 needs_agent（主 agent 兜底），
    也不武断判定——武断误判（如表格判 miss）是静默错误，不触发主 agent，压低可见度。
    判定推导复用于 prefill（单一解析源），返回结构与 v1 完全一致。
    """
    p = prefill(answer, brand_zh, brand_en)
    if p["answer_form"] == "table":
        return {"needs_agent": True, "hit": None, "rank": None, "brand_count": None, "reason": "table"}
    if p["answer_form"] == "prose":
        return {"needs_agent": True, "hit": None, "rank": None, "brand_count": None, "reason": "natural"}
    if not p["simple"]:
        return {"needs_agent": True, "hit": None, "rank": None, "brand_count": p["item_count"], "reason": "blocked"}
    if p["client_rank"] is None:
        return {"needs_agent": False, "hit": False, "rank": None, "brand_count": p["item_count"]}
    n = min(8, p["item_count"])
    return {"needs_agent": False, "hit": p["client_rank"] <= n, "rank": p["client_rank"], "brand_count": p["item_count"]}


def _split_numbered(answer: str) -> list[str] | None:
    """按列表标记分割成项。无列表标记 → 自然段式，返回 None。

    - 数字/Markdown 序号：≥1 个就算列表式（「### 1. 香格里拉」「1. 香格里拉」）。
    - 项目符号（- / • / ·）：≥2 个才算列表式；只有 1 个可能是破折号，视为自然段式。
    - 「1. 香格里拉」单序号也算列表式（AI 只列一家 = 强烈推荐 = 命中 rank 1）。
    """
    matches = list(_LIST_MARKER.finditer(answer))
    if not matches:
        return None
    dash = sum(1 for m in matches if m.group().rstrip()[-1] in ("-", "•", "·"))
    if len(matches) == 1 and dash == 1:
        return None  # 只有 1 个项目符号，可能是破折号
    items: list[str] = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(answer)
        text = answer[start:end].strip()
        if text:
            items.append(text)
    return items or None


def _is_table(answer: str) -> bool:
    """检测 Markdown 表格（连续 ≥2 行 '| xxx |'）。表格排名语义需主 agent 判。"""
    table_lines = [l for l in answer.splitlines() if _TABLE_LINE.match(l)]
    return len(table_lines) >= 2
