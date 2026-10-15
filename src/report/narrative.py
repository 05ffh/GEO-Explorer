"""报告业务叙述：规范（实质指导）+ lint（可机械检查的那半）。

**边界（第一性原理）：系统 generate（确定性）→ 主 agent 判定（语义）→ 系统 apply。**
- `_NARRATIVE_SPEC` 写「讲什么话」——**不可机械检查**，给写作者（主 agent）；lint 失败时打印到使用点。
- `lint_narrative` 只查**表征层**（结构齐 / 数字等值 / 引述存在 / 技术词）——是**下限 lint**
  （挡已知机械坑），**不是**「报告对了」的验证。语义正确性（数字用没用在点上、结论立不立得住）
  永远由主 agent 读——脚本给不了这个保证。
"""
from __future__ import annotations

import re

# ── 规范（实质上，给主 agent）──────────────────────────────────────────
_NARRATIVE_SPEC = """报告业务叙述规范（主 agent 撰写，机器不校验实质，只兜底表征）

【受众/基调】甲方管理层；稳中求进为主 + 一点竞对危机感。
【语言】全篇业务语言，**不出现实现细节**（脚本/字段/快照/接口/口径/渲染…）。
【结构】exec_summary（结论+亮点+风险+优先方向）/ hit_rate_explain / scenes（四场景各 summary+quotes）/
        competitors（summary+band_note+source_note）/ sentiment.summary / assets.summary /
        attribution.key_quotes / directions / method。缺项会渲染成空白 → lint 拦。
【数字口径】出现「综合命中率 / 有效可见度 / 负面率 / N 个高频问题 / N 条事实」时，
        必须与本次数据一致（lint 查已标注指标名的数字；未标指标名的数字 lint 判不了，自己核）。
【AI 原话】scenes[*].quotes 与 attribution.key_quotes 取自本次 AI 回答的原文**内容**；
        **允许忠实拼接/重排**（把 AI 几处原话合成一句，如「餐厅在2楼」+「米其林一星」合写），
        但不得改变内容或新增事实。lint 分段核对（归一去 markdown/空白/标点），命中不了只 **warn**
        （脚本分不清「忠实拼接」与「编造」→ 交主 agent 确认）。
【免责】数字口径声明：基于甲方指定 N 个问题 × 4 个 AI；**换问法会变，结论仅对这些问题成立**。
        正文与附录各一处。
【换客户】本规范通用；narrative 每客户新建，数据源换 run，模板/口径/lint 不动。
"""
# ────────────────────────────────────────────────────────────────────

_REQUIRED_KEYS = ("exec_summary", "hit_rate_explain", "scenes", "competitors",
                  "sentiment", "assets", "attribution", "directions", "method")

# 技术词（启发式词表，非定义——词表外的新词漏；故只 warn）
_TECH_WORDS = ("脚本", "JSON", "字段", "measurement", "judgment", "快照", "run_id",
               "API", "CLI", "Jinja", "后端", "渲染", "schema", "pipeline", "接口")

# **只查「已标注指标名」的数字**（未标注的脚本判不了：同一个数可能挂在错的标签上）
_METRIC_PCT = (("综合命中率", "hit_rate"), ("有效可见度", "effective_visibility"),
               ("负面率", "negative_rate"))
_METRIC_COUNT = (("个高频问题", "hit_question_count"), ("条事实", "gt_facts_count"))


def _iter_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _iter_strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _iter_strings(v)


def _pct_str(v) -> str | None:
    return f"{v * 100:.1f}%" if isinstance(v, (int, float)) else None


# 引述比对归一：只留汉字/字母/数字（去 markdown、空白、标点、引号——叙述用全角「」“”，
# AI 原文用半角 ""，标点差异≠改写；保证=「非编造」，非「标点逐字」）
_QSTRIP = re.compile(r"[^0-9A-Za-z一-鿿]+")


def _qkey(s: str) -> str:
    return _QSTRIP.sub("", s or "")


# 引述分段边界：省略号 / 中英文标点 / 括号引号（允许忠实拼接——各段分别命中即可）
_QSPLIT = re.compile(r"…|\.{3}|[「」『』（）()【】\[\]“”\"'’，。；、：？！]+")


def answer_corpus(measurement: dict) -> list[str]:
    """sealed measurement 的 AI 回答原文语料（引述逐字比对源）。**逐条**归一（不拼接，
    防跨回答边界误拼）。"""
    return [k for k in (_qkey(j.get("answer") or "")
                        for p in (measurement.get("platforms") or {}).values()
                        for j in p.get("judgments") or []) if k]


def _quote_found(quote: str, answers: list[str]) -> bool:
    """引述核对：按省略号/标点/括号分段，**每段**归一无标点后须在某条回答里出现。
    分段 = 允许**忠实拼接**（把 AI 几处原话重排成一句，各段仍可分别命中）。"""
    for seg in _QSPLIT.split(quote or ""):
        k = _qkey(seg)
        if k and not any(k in a for a in answers):
            return False
    return True


def lint_narrative(data: dict, narrative: dict, answers: list[str]) -> list[dict]:
    """报告 lint。返回 [{"level": "error"|"warn", "code", "msg"}]；error 阻断、warn 提示。"""
    out: list[dict] = []

    def add(level, code, msg):
        out.append({"level": level, "code": code, "msg": msg})

    # 1) 结构完整性（error，零误报）
    for k in _REQUIRED_KEYS:
        if not narrative.get(k):
            add("error", "structure", f"叙述缺「{k}」")
    for sc in (data.get("scenes") or []):
        if sc.get("name") and sc["name"] not in (narrative.get("scenes") or {}):
            add("error", "structure", f"场景「{sc['name']}」缺叙述")

    # 2) 引述核对（**warn**，非阻断）：忠实拼接允许；但脚本分不清「忠实拼接」与「编造」
    #    → 命中不了只提示，由主 agent 确认。保证=「提示核对」，非「判定造假」。
    quotes = [q for sc in (narrative.get("scenes") or {}).values() for q in (sc.get("quotes") or [])]
    quotes += list((narrative.get("attribution") or {}).get("key_quotes") or [])
    for q in quotes:
        if not _quote_found(q, answers):
            add("warn", "quote", f"引述未能分段命中 AI 原文（若为忠实拼接/压缩可接受，请确认）：「{q[:24]}」")

    # 3) 技术词（warn；词表启发式，排除 URL）
    for s in _iter_strings(narrative):
        if s.startswith("http"):
            continue
        for w in _TECH_WORDS:
            if w in s:
                add("warn", "techword", f"叙述含技术词「{w}」：…{s[:24]}…")

    # 4) 数字一致性（error；**只查已标注指标名的数字**）
    text = "\n".join(_iter_strings(narrative))
    for label, key in _METRIC_PCT:
        want = _pct_str(data.get(key))
        if want is None:
            continue
        for m in re.finditer(rf"{label}\D{{0,6}}?(\d+(?:\.\d+)?)%", text):
            if m.group(1) + "%" != want:
                add("error", "number", f"「{label}」写 {m.group(1)}%，本次数据为 {want}")
    for label, key in _METRIC_COUNT:
        want = data.get(key)
        if not isinstance(want, int):
            continue
        for m in re.finditer(rf"(\d+)\s*{label}", text):
            if int(m.group(1)) != want:
                add("error", "number", f"「{label}」写 {m.group(1)}，本次数据为 {want}")

    # 5) 头部数字在场（warn）
    head = _pct_str(data.get("hit_rate"))
    if head and head not in text:
        add("warn", "headline", f"叙述未出现综合命中率 {head}（封面已展示，非必错）")
    return out
