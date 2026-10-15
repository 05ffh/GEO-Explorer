"""归因劣势提取（P1-②，spec ⑪ 归因层 ②）：从归因对比/平衡题回答提取甲方劣势维度。

读 attribution 层 judgment（layer=attribution）：
- 对比题（attr_*，"甲方和竞品…哪家好，为什么"）→ AI 二选一 + 理由 = 劣势维度的直接证据
- 平衡题（attr_*_balance，"…各自有什么优劣势"）→ AI 列双方优劣 = 甲方劣势 + 优势

**提取 = 子 agent 语义判断**（自由文本措辞不可预测，确定性提取质量低）；系统做确定性部分
（结构校验/聚合/存储）。**接地（grounding，用户 2026-09-10 定）**：子 agent 输入附甲方真实属性
（P2 GT 采集 + 命中层 AI 引用 content_assets），把劣势维度分两类——这决定落地方案方向：
- type=true_disadvantage：甲方确实没有/弱于竞对该维度 → 对标竞对/补差异化
- type=client_has_unreferenced：甲方有该资产但 AI 未引用（可见度/内容问题）→ 铺内容/让 AI 引用
不接地会把"甲方有设施但 AI 没提"误判成"甲方设施弱"→ 方案做错方向。

提取结构（存 judgment.attribution_result）：
{
  "pick": "competitor|client|tie|no_choice",
  "client_disadvantage_dims": [{"dim": "服务|设施|价格|位置|品牌|其他", "type": "...", "evidence": "AI 原话"}],
  "client_advantage_dims":    [{"dim": "...", "evidence": "..."}],
}
聚合：measurement["attribution_dims"] = {dim: {disadvantage, advantage, evidence...}}，喂归因树竞争侧。
"""
from __future__ import annotations

import re

DIMS = ("服务", "设施", "价格", "位置", "品牌", "餐饮", "其他")
PICK_VALUES = ("competitor", "client", "tie", "no_choice")
# 接地分类（用户 2026-09-10 定）：决定落地方案方向
TYPE_TRUE_DISADVANTAGE = "true_disadvantage"          # 甲方真没有/确实弱 → 对标/补差异
TYPE_CLIENT_HAS_UNREFERENCED = "client_has_unreferenced"  # 甲方有但 AI 未引用 → 铺内容
TYPE_VALUES = (TYPE_TRUE_DISADVANTAGE, TYPE_CLIENT_HAS_UNREFERENCED)
# 比较判断维度：语料有价格/品牌介绍 ≠ 甲方不亏/更强 → 恒 true（2026-09-15 定）
ALWAYS_TRUE_DIMS = ("价格", "品牌")
# 资产存在性维度：每条候选劣势需 corpus_fact（2026-09-17 修，治跨 agent 判定方差）
ASSET_DIMS = ("设施", "餐饮", "服务", "位置", "其他")
CORPUS_FACT_VALUES = ("none", "refutes", "confirms")


def _derive_type(dim: str, corpus_fact: str | None) -> str:
    """type 确定性派生：价格/品牌恒 true；资产类维度仅 corpus_fact=refutes（语料有同属性直接反证）→ clie。

    第一性原理（2026-09-17）：语料（甲方自夸材料）能证伪「存在性」，结构上无法证伪「质量」——
    AI 的质量批评（旧/慢/一般/排队）仅凭「语料有该资产」不得翻 clie；只有「存在否定被反」
    或「同属性具体事实反驳」才说明 AI 说错/没引 → clie（铺内容）。
    """
    if dim in ALWAYS_TRUE_DIMS:
        return TYPE_TRUE_DISADVANTAGE
    return TYPE_CLIENT_HAS_UNREFERENCED if corpus_fact == "refutes" else TYPE_TRUE_DISADVANTAGE

_ATTRIBUTION_SPEC = (
    "归因劣势提取：读 甲方 vs 竞品 的对比/平衡回答，提取甲方劣势/优势维度（带接地分类）。\n"
    "输入含两级接地（2026-09-18 架构）：【甲方事实清单】（GT 权威清单，第一判决依据，来源等级优先）+"
    "【甲方页面内容】（原文佐证，第二依据）+【AI 引用过的甲方内容】+ 档位，用于判断「甲方到底有没有这资产」。\n"
    "输出每题：\n"
    "1. pick（仅对比题）：AI 最终推荐谁——competitor=竞品/client=甲方/tie=都提无明确偏向/no_choice=没给结论。\n"
    "   ⚠️ pick 必须读 AI 的**最终结论句**（\"更推荐/更合适/优先选/首选/综合选 X\"），"
    "不是\"如果...选 X\"的条件句（条件句=按需求分流=tie/按 AI 主倾向）。\n"
    "2. client_disadvantage_dims：AI 认为甲方不如竞品的维度（服务/设施/价格/位置/品牌/餐饮/其他），每条：\n"
    "   - dim：维度（必须从枚举里选最贴合的）\n"
    "   - evidence：**必须来自 AI 回答原话**（一句话内），禁止混入【甲方页面内容】或你自己的知识。"
    "AI 原文没说的维度 → 不记。\n"
    "     ⚠️ evidence 约束（2026-10-14 修订）：**核心 = 内容必须来自 AI 原话（可机械回查）**。"
    "①**改写/拼接/缩写（伪造 AI 没说过的话）→ 严禁**；"
    "②**\"维度名：\"前缀 / \"（…）\"补充注释（= 加工措辞，内容仍是 AI 原话）→ 允许**"
    "（系统落库时自动剥离前缀/注释，保机械可核验，子 agent 不必因此重判）。"
    "回答是表格 → 取单元格原文，不含表头维度名。\n"
    "   - corpus_fact（关键，先查【甲方事实清单】、无则回【甲方页面内容】检索；资产类维度 设施/餐饮/服务/位置/其他 **必填**）：\n"
    "     **对这条 AI 负面说法，语料有没有「针对同一属性的具体事实」直接反驳它？三选一：**\n"
    "     - none：没有能反驳的同属性事实。**⚠️ 仅有「甲方有该资产」不足以反驳质量评价**——AI 说"
    "\"早餐一般/服务慢/设施旧/要排队\"时，语料只有\"有自助早餐/有服务清单/2005年开业\"→ none。\n"
    "     - refutes：语料有**同一属性**的具体事实直接反驳 AI——三类：① AI 说甲方\"没有/缺 X\"而语料有 X；"
    "② AI 给的具体数字/属性被语料更优事实反驳（\"步行8-12分钟\"vs 语料\"步行3分钟\"）；"
    "③ AI 对比句隐含\"甲方 X 弱\"（如\"竞对亲子更好\"），而语料有 X 的具体资产（如芽宝乐园/亲子主题房）。\n"
    "     - confirms：语料有同属性事实但证实 AI（如语料\"2005年开业\"证实\"设施旧\"）。\n"
    "   - type（**系统按 corpus_fact 确定性派生，子 agent 不用输出**）：价格/品牌 → 恒 true_disadvantage；"
    "corpus_fact=refutes → client_has_unreferenced（甲方有、AI 没引/说错 → 铺内容）；"
    "corpus_fact=none 或 confirms → true_disadvantage（语料证不了 → AI 批评即市场认知 → 对标/补差异）。\n"
    "3. client_advantage_dims：AI 认为甲方占优的维度（平衡题必填，对比题有则填），同样 dim + evidence（AI 原话）。"
    "**优势维度主题全覆盖**：每个被 AI 点名的优势维度（设施/位置/餐饮/服务/品牌…）至少提取一条，"
    "**同维度合并成一条**（不逐句穷举，重复内容去重）；跨维度主题不许漏（如 AI 提了餐饮、服务两个主题都要有）。\n"
    "**存在性裁决顺序（2026-09-18 架构，防「子 agent 读错/过时信息」）**：判断「甲方有没有 X」"
    "→ ①先查【甲方事实清单】（来源等级优先：T0官网 > T1 OTA > T2 点评/百科 > T3 UGC）"
    "→ ②无则回【甲方页面内容】原文查 → ③两级都没有 → 标「未证实/时效待核」，**不判「甲方没有」**"
    "（语料无可能=漏抓或停业，两个方向都见过：网球场曾「官网无」实为漏抓、韩香馆「语料无」实为已停业）。\n"
    "**AI 声称甲方有 X 的处理（防幻觉，2026-09-18）**：事实清单+原文都无 → **不算甲方资产**（不铺这个内容，"
    "官网不认的不能当落地素材），但**不判「甲方绝对没有」**（标未证实，可能是漏抓）。\n"
    "**强制两级查询（治「不查接地直接判真劣势」根因）**：资产类维度每条候选劣势**必须先查【甲方事实清单】再回"
    "【甲方页面内容】**再定 corpus_fact；**禁止跳过检索直接判**；「AI 没提」≠「甲方没有」。"
    "价格/品牌为**比较判断**（语料有价格数字/品牌介绍 ≠ 甲方不亏/更强）→ 恒 true_disadvantage，无需 corpus_fact。\n"
    "**劣势判定铁律（2026-09-14 加，防竞对优势误挂甲方）**：\n"
    "   劣势 = **甲方在 X 维度相对吃亏**，evidence 必须是**对比句**——要么以甲方开头点出甲方弱/缺\n"
    "   （\"甲方无高空观景，楼层最高26层\"），要么同时提甲方和竞对形成对比\n"
    "   （\"甲方市中心无临湖遛娃场景，西湖大酒店房卡直入木栈道\"）。\n"
    "   **反例（不算劣势）**：只描述竞对优势（\"世茂洲际58层高空俯瞰\"\"西湖大酒店老牌国宾级五星\"）——\n"
    "   这只是竞对的优势，除非你把它写成\"甲方相对弱\"的对比句。\n"
    "   纯竞对特征、没让甲方在该维度落败的 → 不记劣势。\n"
    "**防错警告（2026-09-18 加，轮0/1/2 重判实证——共删 11 条此类误挂劣势）**：\n"
    "   ① **条件分流句 ≠ 劣势**：\"若更看重 X，选竞对更合适\"是 AI 的**选边条件**，不是\"甲方弱在哪\"——不提取。\n"
    "   ② **竞对优势 ≠ 劣势**：主语是竞对（世茂洲际/凯宾斯基/西湖）的优势描述\n"
    "      （\"亲子房型更丰富/设施比香格里拉更全\"）不算甲方劣势，除非写成\"甲方相对弱\"的对比句（甲方开头）。\n"
    "   ③ **禁同句重复**：同一句 evidence 不得重复挂多个 dim（凑数会污染聚合计数）。\n"
)


def render_gt_facts(facts: dict | None) -> list[str]:
    """gt_facts_json → 子 agent 可读甲方事实清单（第一判决依据，来源等级优先 + 可追溯）。

    2026-09-18 架构（用户拍板「协议+元数据」）：gt_facts_json 由「AI 共识+人核清单」定位调整为
    **官网当前页事实的结构化索引**——可信 = 可追溯（来源 URL + 采集时间戳），不是"被验证过"。
    来源等级：T0官网 > T1 OTA > T2 点评/百科 > T3 UGC；标「已停业/已改造」= 过时项，不算甲方资产。
    """
    if not isinstance(facts, dict):
        return []
    cats = facts.get("facts") if isinstance(facts, dict) else None
    if not isinstance(cats, dict):
        return []
    lines: list[str] = []
    for cat, items in cats.items():
        if not isinstance(items, list):
            continue
        for it in items:
            if not isinstance(it, dict):
                continue
            f = (it.get("fact") or "").strip()
            if not f:
                continue
            tier = it.get("source_tier") or ""
            src = it.get("source_url") or ""
            cap = it.get("captured_at") or ""
            kind = it.get("source_kind")
            tag = f"[{tier}]" if tier else ""
            meta = []
            if src:
                meta.append(f"来源:{src}")
            elif kind == "verified":
                meta.append("未单页溯源")
            if cap:
                meta.append(f"核验:{cap}")
            lines.append(f"{tag} {f}" + (f"（{' · '.join(meta)}）" if meta else ""))
    if not lines:
        return []
    return [(
        "【甲方事实清单（GT 权威清单；判决「甲方有没有 X」的**第一依据**。"
        "来源等级：T0官网 > T1 OTA > T2 点评/百科 > T3 UGC；标注「已停业/已改造」= 过时项，不算甲方资产。"
        "裁决顺序：①先查本清单 → ②无则回【甲方页面内容】原文 → ③两级都没有 → 标「未证实/时效待核」，"
        "**不判「甲方没有」**）】"
    ), *lines]


def build_client_context(
    m: dict,
    grounding_corpus: str | None = None,
    gt_facts: dict | None = None,
    client_tier: str | None = None,
) -> list[str]:
    """甲方已知属性（接地输入，两级，2026-09-18 架构）：事实清单（判决）+ 页面原文（佐证）+ AI 引用（补充）+ 档位。

    - **gt_facts_json（第一依据）**：官网当前页结构化事实索引，来源等级优先 + 可追溯（URL/时间戳）。
      替代「AI 共识+人核」当权威的旧定位（AI 是被测量对象，不能当事实源——韩香馆案例）。
    - **grounding_corpus（第二依据，原文佐证）**：甲方自己页面（官网/OTA）过滤后正文（P2 GT content_text），
      查细节/原话/清单未列的兜底；未提到≠没有（可能是漏抓或停业，两个方向都见过：网球场漏抓、韩香馆停业）。
    content_assets（AI 引用）仅作补充/交叉参考。
    """
    ctx: list[str] = []
    ctx.extend(render_gt_facts(gt_facts))
    if grounding_corpus:
        ctx.append("【甲方页面内容（原文佐证，第二依据：查细节/原话/事实清单未列的兜底。方括号标信源，"
                   "可信度：【T0 官网/官方】最权威 >【T1 OTA平台】次之 >【T2 点评媒体】>【T3 UGC】；"
                   "标记「游记/第三方」的是第三方口吻内容，只作参考、不能单独作为「甲方有 X」的依据。"
                   "本内容未提到的视为未证实——**未提到≠没有**（可能是漏抓或停业），不判「甲方没有」，"
                   "也不得因此判 AI 编造）】")
        ctx.append(grounding_corpus)
    ctx.append("【AI 引用过的甲方内容（补充参考，非事实标尺）】")
    for a in (m.get("content_assets") or [])[:15]:
        if a.get("content"):
            ctx.append(a["content"])
    # 档位来自 positioning_json（measurement_json 无该字段）——显式传入；缺了它档位从不送达子 agent
    tier = client_tier or m.get("tier")
    if tier:
        ctx.append(f"档位：{tier}")
    return [x for x in ctx if x]


def generate_attribution_pending(
    m: dict,
    client_context: list[str] | None = None,
    grounding_corpus: str | None = None,
    gt_facts: dict | None = None,
    force: bool = False,
    client_tier: str | None = None,
) -> dict:
    """输出归因层待提取清单：layer=attribution 且未提取的 judgment（题目+回答+甲方接地上下文）。

    硬防护（2026-09-11）：content_assets 必须已计算（命中判定后 finalize 产出）——接地是 type
    分类（真劣势 vs 甲方有未引用）的前提，缺了提取不可靠。content_assets key 不存在 =
    顺序错（先跑命中判定 + finalize，如 finalize_v4 hit），直接抛错拦截。
    grounding_corpus（2026-09-14 方案A）：甲方自己页面全文（GT content_text），作接地标尺。
    gt_facts（2026-09-18 架构）：collection_runs.gt_facts_json 结构化事实清单，第一判决依据。
    force=True：已提取的归因题也输出（接地语料变后重判 V5 归因用）。
    """
    if client_context is None and "content_assets" not in m:
        raise ValueError(
            "接地上下文缺失：content_assets 未计算。需先跑命中判定 + finalize_measurement"
            "（如 scripts/finalize_v4.py hit <run_id> <patch>），再生成归因待提取，否则 type 分类不可靠")
    ctx = client_context if client_context is not None else build_client_context(m, grounding_corpus, gt_facts, client_tier)
    # 判定规范随文件下发（2026-09-18 对抗审查修：归因 _ATTRIBUTION_SPEC 曾零消费者、主 agent 手贴
    # 易漂移——嵌进纯函数自包含，任何调用方都得 spec，防再漂移；对齐 _HIT_SPEC 固化）
    out: dict = {"platforms": {}, "client_context": ctx, "spec": _ATTRIBUTION_SPEC}
    for p, info in m.get("platforms", {}).items():
        pend = {}
        for j in info.get("judgments", []):
            if j.get("layer") != "attribution" or j.get("reason") == "error":
                continue
            if j.get("attribution_result") and not force:
                continue
            pend[j["question_id"]] = {
                "question": j.get("question", ""),
                "answer": j.get("answer", ""),
                "scenario": j.get("question_id", "").split("_", 1)[-1],
            }
        if pend:
            out["platforms"][p] = pend
    return out


_PREFIX_RE = re.compile(r'^([^：，。]{1,10})：')
_PAREN_RE = re.compile(r'[（(][^（）()]*[）)]')
_MD_KILL = re.compile(r'<br\s*/?>|[*#`|>_\s]+')     # markdown/空白归一（子 agent 复制时去掉 ** 等）


def _md_norm(s: str) -> str:
    return _MD_KILL.sub('', s or '')


def _strict_evidence(evidence: str, answer: str) -> str:
    """剥掉子 agent 自己加的「前缀/注释」（**内容仍是 AI 原话时**）→ 保 evidence 机械可核验（2026-10-14 方案A）。

    第一性原理：前缀/注释是「加工措辞」（内容仍原话）→ **允许存在**，但系统落库时归一化，
    使 evidence 恒可回到 AI 原文核对（防幻觉、可自动复核）。
    - 前缀「XX：」：**剥前缀后剩余在原文** → 前缀是自加 → 剥；若前缀本身也在原文（AI 自己写的标签）→ 保留。
    - 括号「（…）」：整段不在回答原文 → 自加注释 → 剥。
    - 比对前**归一去 markdown**（AI 原文的 `**`/表格符/`<br>` ≠ 改写）。
    - **改写/拼接**（正文对不上原文）无法机械修 → 原样返回（由复核/重判把关，勿静默改内容）。
    """
    e = (evidence or "").strip()
    a = _md_norm(answer)
    if _md_norm(e) in a:
        return e                                        # 逐字（模 markdown）→ 不动
    m = _PREFIX_RE.match(e)
    if m:
        rest = e[len(m.group(0)):].strip()
        if rest and _md_norm(rest) in a:
            e = rest                                    # 前缀自加、剩余是原文 → 剥前缀
    e = _PAREN_RE.sub(lambda mm: mm.group(0) if _md_norm(mm.group(0)) in a else "", e).strip()
    return e or evidence


def apply_attribution(m: dict, patch: dict) -> int:
    """把子 agent 劣势提取写回 judgment.attribution_result。返回回填题数。

    patch = {平台: {qid: {pick, client_disadvantage_dims, client_advantage_dims}}}。
    校验：pick 枚举、dim 合法、evidence 必填；资产类劣势维度必填 corpus_fact。非法跳过并告警。
    type 由 corpus_fact **确定性派生**（`_derive_type`，2026-09-17 修——收掉跨 agent 判定方差，
    治"AI 批评质量却被误判 client_has_unreferenced"的机械规则 misfire）。
    """
    applied = 0
    for p, info in m.get("platforms", {}).items():
        p_patch = patch.get(p, {})
        for j in info.get("judgments", []):
            qid = j.get("question_id")
            val = p_patch.get(qid)
            if not val or j.get("layer") != "attribution":
                continue
            pick = val.get("pick")
            if pick is not None and pick not in PICK_VALUES:
                print(f"  警告: [{p}] {qid} pick 非法 {pick!r}，跳过")
                continue
            dis = val.get("client_disadvantage_dims") or []
            adv = val.get("client_advantage_dims") or []
            bad = [d.get("dim") for d in dis
                   if d.get("dim") not in DIMS or not (d.get("evidence") or "").strip()
                   or (d.get("dim") in ASSET_DIMS and d.get("corpus_fact") not in CORPUS_FACT_VALUES)]
            if bad:
                print(f"  警告: [{p}] {qid} 劣势维度非法/缺 evidence 或缺 corpus_fact：{bad}，跳过")
                continue
            bad_adv = [d.get("dim") for d in adv
                       if d.get("dim") not in DIMS or not (d.get("evidence") or "").strip()]
            if bad_adv:
                print(f"  警告: [{p}] {qid} 优势维度非法/缺证据：{bad_adv}，跳过")
                continue
            _ans = j.get("answer") or ""
            dis = [dict(d, evidence=_strict_evidence(d["evidence"], _ans),
                        type=_derive_type(d["dim"], d.get("corpus_fact"))) for d in dis]
            adv = [dict(d, evidence=_strict_evidence(d["evidence"], _ans)) for d in adv]
            j["attribution_result"] = {
                "pick": pick,
                "client_disadvantage_dims": dis,
                "client_advantage_dims": adv,
            }
            j["needs_agent"] = False       # 劣势提取完成，不再待判
            j["reason"] = "attribution_extracted"
            applied += 1
    return applied


def aggregate_attribution(m: dict) -> dict:
    """聚合劣势/优势维度（跨平台/场景），喂归因树竞争侧。

    返回 {dim: {"disadvantage": 次数, "advantage": 次数,
                "true_disadvantage": 次数, "client_has_unreferenced": 次数, evidence...}}。
    """
    from collections import Counter

    disadv: Counter = Counter()
    adv: Counter = Counter()
    by_type: dict[str, Counter] = {t: Counter() for t in TYPE_VALUES}
    disadv_ev: dict[str, list[str]] = {}
    adv_ev: dict[str, list[str]] = {}
    for info in m.get("platforms", {}).values():
        for j in info.get("judgments", []):
            r = j.get("attribution_result")
            if not r:
                continue
            for d in r.get("client_disadvantage_dims", []):
                disadv[d["dim"]] += 1
                by_type[d["type"]][d["dim"]] += 1
                disadv_ev.setdefault(d["dim"], []).append(d["evidence"])
            for d in r.get("client_advantage_dims", []):
                adv[d["dim"]] += 1
                adv_ev.setdefault(d["dim"], []).append(d["evidence"])
    return {
        d: {
            "disadvantage": disadv[d],
            "advantage": adv[d],
            "true_disadvantage": by_type[TYPE_TRUE_DISADVANTAGE][d],
            "client_has_unreferenced": by_type[TYPE_CLIENT_HAS_UNREFERENCED][d],
            "disadvantage_evidence": disadv_ev.get(d, [])[:5],
            "advantage_evidence": adv_ev.get(d, [])[:5],
        }
        for d in DIMS if disadv[d] or adv[d]
    }
