"""AI 推荐酒店提取（竞对候选来源，spec 3.1 竞对圈层·系统化承载）。

从命中层 judgments（含 AI 回答原文）提取 AI 实际推荐的酒店，作为竞对候选池补充。
**同场景共现（cooccurrence）** = AI 在提到甲方的题目里也提到该酒店的次数——
这是替代关系信号（消费者在甲方与它之间二选一），区别于总提及（含市场声量）。
提取的酒店进候选池后统一走 filter_competitors 判定；归一化去重由主 agent 复核。
"""
from __future__ import annotations

import re

_HOTEL_RE = re.compile(r"[一-鿿]{2,12}?(?:大酒店|大饭店|酒店|饭店|宾馆|度假村|民宿)")
# 非实体短语（AI 泛化的"这家酒店/推荐酒店/经济型酒店"等），忽略
_STOP = {
    "推荐酒店", "这家酒店", "那家酒店", "部分酒店", "高端酒店", "五星级酒店",
    "几家酒店", "其他酒店", "特色酒店", "亲子酒店", "情侣酒店", "网红酒店",
    "商务酒店", "平价酒店", "温泉酒店", "主题酒店", "星级酒店", "连锁酒店",
    "经济型酒店", "中档酒店", "豪华酒店",
}


# 指示词/连接词前缀（"推荐XX""和XX酒店"等非实体引导语），清洗掉。
# 注意不加"如/住/是"等——"如家酒店"是品牌，不能误剥。
_NOISE_PREFIX = ("推荐", "选择", "建议", "这家", "那家", "几家", "其他", "部分", "和", "与", "以及")


def _normalize(name: str, city: str | None = None) -> str:
    """去指示词/城市前缀 + 括号店名，得到核心名。

    city 由调用方传入（诊断城市），剥对应前缀保证跨地区通用（福州/广州通用）；
    保留福州/福建兼容历史测试数据（福州场景常见"福建外贸中心"字号）。
    """
    name = name.strip()
    for p in _NOISE_PREFIX:
        if name.startswith(p):
            name = name[len(p):]
            break
    if city and name.startswith(city):
        name = name[len(city):]
    elif name.startswith("福州"):
        name = name[2:]
    elif name.startswith("福建"):
        name = name[2:]
    for sep in ("（", "(", "·"):
        if sep in name:
            name = name.split(sep)[0]
    return name.strip()


def extract_hotels(judgments: list[dict], client_brand: str, city: str | None = None) -> dict:
    """从命中层 judgments 提取 AI 推荐酒店 + 与甲方同场景共现。

    judgments 每项含 question_id / question / answer（measure_platform 产出）。
    city = 诊断城市（剥城市前缀，保证跨地区归一化通用）。
    返回 {归一化酒店名: {"mentions", "cooccurrence", "question_ids"}}。
    cooccurrence = 提到甲方的题目里也提到该酒店的次数。
    """
    out: dict[str, dict] = {}
    for j in judgments:
        answer = j.get("answer") or ""
        qid = j.get("question_id", "")
        mentions_client = client_brand in answer
        for m in _HOTEL_RE.finditer(answer):
            name = _normalize(m.group(), city)
            if len(name) < 3 or name in _STOP:
                continue
            # 甲方品牌与其他酒店无标点混写（"香格里拉和广州花园酒店"）→
            # 整段含品牌会误排除；有连接词则剥离甲方后提取剩余
            if client_brand in name and any(s in name for s in ("和", "与", "、")):
                remainder = name.replace(client_brand, "").strip("和与、 ")
                if len(remainder) >= 3:
                    remainder = _normalize(remainder, city)
                    if len(remainder) >= 3 and remainder not in _STOP and client_brand not in remainder:
                        _record(out, remainder, qid, mentions_client)
                continue
            # 排除甲方自身（品牌名出现）
            if client_brand in name or name in client_brand:
                continue
            _record(out, name, qid, mentions_client)
    return out


def _record(out: dict, name: str, qid: str, mentions_client: bool) -> None:
    item = out.setdefault(name, {"mentions": 0, "cooccurrence": 0, "question_ids": []})
    item["mentions"] += 1
    if qid not in item["question_ids"]:
        item["question_ids"].append(qid)
    if mentions_client:
        item["cooccurrence"] += 1
