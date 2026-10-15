# GEO 诊断报告（HTML→PDF）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 产出一份面向甲方管理层的 AI 可见度诊断报告（HTML），用户浏览器预览确认后转 PDF。

**Architecture:** 三层——①`report_data.py` 从 V6 快照提取报告所需数据（纯函数，可测）；②`geo_report.py` + Jinja2 模板把数据渲染成商务蓝 HTML；③`build_geo_report.py` CLI 串起来。业务叙述（场景描述/归因叙述/方向）由主 agent 撰写，作为 `narrative` 输入传给渲染器，**不进提取脚本**（提取只产事实数字）。

**Tech Stack:** Python 3.12 / SQLAlchemy async / Jinja2 3.1.6（已在 requirements）/ Puppeteer `md2pdf`（PDF 转换，已装）。

**设计文档：** `docs/superpowers/specs/2026-10-14-geo-report-design.md`
**数据源：** V6 run `535b8108-54fa-4198-931e-37c76d0a5c53` 快照 1

**语言铁律（全任务适用）：** 报告中不出现"脚本/系统/字段/JSON/命中率算法"等字眼；只讲业务含义。模板里任何给甲方看的文案都过这一关。

---

## File Structure

| 文件 | 职责 |
|---|---|
| `src/report/report_data.py` | `build_report_data(run) -> dict`：从 run 提取全部报告数字（命中率/竞对/场景/舆情/归因/供给侧）。纯函数、可测。 |
| `src/report/geo_report.py` | `render_report(data, narrative, *, brand, city, date) -> str`：Jinja2 渲染 → HTML 字符串。 |
| `src/report/templates/geo_report.html.j2` | HTML 模板（商务蓝样式 + 布局 + 各章结构 + 附录）。 |
| `scripts/build_geo_report.py` | CLI：`run_id` → 读 run → 提取 → 合并 narrative → 渲染 → 写 HTML 文件。 |
| `tests/test_report_data.py` | 提取函数测试（字段存在 + 关键数字正确）。 |
| `tests/test_geo_report.py` | 渲染冒烟测试（含关键字符串 + 无技术词）。 |

**narrative 输入**：CLI 从 `src/report/narratives/<品牌>_<城市>.py`（或 `.json`）读，主 agent 撰写。首份 = `src/report/narratives/福州香格里拉.py`。

---

## Task 1: 数据提取 `build_report_data`

**Files:**
- Create: `src/report/__init__.py`
- Create: `src/report/report_data.py`
- Test: `tests/test_report_data.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_report_data.py
"""报告数据提取：从 V6 快照产出报告所需字段（纯函数，喂 mock run）。"""
from src.report.report_data import build_report_data


def _run(measurement, **extra):
    class R:
        pass
    r = R()
    r.measurement_json = measurement
    r.gt_facts_json = extra.get("gt", {})
    r.cdp_facts_json = extra.get("cdp", {})
    r.sentiment_json = extra.get("sentiment", {})
    r.positioning_json = extra.get("positioning", {})
    r.brand = extra.get("brand", "香格里拉")
    r.city = extra.get("city", "福州")
    return r


_M = {
    "overall": {"overall_hit_rate": 0.7873,
                "platform_hit_rates": {"deepseek": 0.9375, "kimi": 0.875,
                                       "doubao": 0.875, "wenxin": 0.4615}},
    "effective_visibility": 0.6917,
    "negative_rate_combined": 0.1735,
    "miss_structure": {"structural": 6, "true_disadvantage": 6},
    "competitor_visibility": {"bands": {"福州世茂洲际酒店": "main"},
                              "overall": {"main": {"status": "ok", "members": [
                                  {"name": "福州世茂洲际酒店", "overall_rate": 0.5336,
                                   "platform_rates": {"deepseek": 0.9375}}]},
                              "secondary": {"status": "ok", "members": []}}},
    "attribution_dims": {"设施": {"advantage": 22, "disadvantage": 24,
                                 "true_disadvantage": 22, "advantage_evidence": ["a"],
                                 "disadvantage_evidence": ["b"]}},
    "content_assets": [{"content": "地址：福州市鼓楼区新权南路9号", "count": 2}],
    "platforms": {"deepseek": {"judgments": [
        {"layer": "hit", "question_id": "hit_b1", "question": "福州市中心有哪些高端酒店推荐",
         "recommendation": "recommend", "has_hotel_recommendations": True,
         "hotels_recommended": ["福州香格里拉大酒店"], "referred_content": ["老牌五星，位置核心"],
         "scene": {"dim": "region", "val": "五一广场", "rank_in_scene": 1, "in_scene_count": 3}}]}},
    "question_fingerprint": ["hit_b1"],
}


def test_hit_rates_and_derived():
    d = build_report_data(_run(_M))
    assert d["hit_rate"] == 0.7873
    assert d["platform_hit_rates"]["deepseek"] == 0.9375
    assert d["effective_visibility"] == 0.6917
    assert d["negative_rate"] == 0.1735


def test_competitors_banded():
    d = build_report_data(_run(_M))
    assert d["competitors"]["main"][0]["name"] == "福州世茂洲际酒店"
    assert d["competitors"]["main"][0]["rate"] == 0.5336


def test_scenes_grouped_from_client_yaml():
    d = build_report_data(_run(_M))
    # hit_b1 归到「商旅」场景（client yaml 的 scenario 字段）
    assert any(s["name"] == "商旅" for s in d["scenes"])


def test_sentiment_and_attribution():
    d = build_report_data(_run(_M, sentiment={"store_level": {
        "rate": 0.1735, "total": 98, "negative_count": 17,
        "themes": {"hygiene": 12, "service": 3, "dining": 2, "price": 1}}}))
    assert d["sentiment"]["themes"]["hygiene"] == 12
    assert d["attribution"]["设施"]["true_disadvantage"] == 22
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_report_data.py -q`
Expected: FAIL（`ModuleNotFoundError: src.report`）

- [ ] **Step 3: 实现**

```python
# src/report/__init__.py
```

```python
# src/report/report_data.py
"""报告数据提取（P5 报告层）：从 V6 快照提取报告所需事实数字。

只产数字/清单，不产叙述——业务叙述由主 agent 撰写后经 narrative 传入。
场景分组读 question_templates_client.yaml 的 scenario 字段（体系B 专属）；
体系A 无该字段时退化为按 persona 分组。
"""
from __future__ import annotations

_THEME_CN = {"hygiene": "卫生", "service": "服务", "dining": "餐饮", "price": "价格"}


def _scenario_map() -> dict[str, str]:
    from src.industry_knowledge.loader import get_knowledge_loader
    try:
        items = get_knowledge_loader().load_category("question_templates_client")
    except Exception:
        return {}
    return {it["id"]: it["scenario"] for it in items if it.get("scenario")}


def _scenes(platforms: dict, scenario_of: dict[str, str]) -> list[dict]:
    """按场景聚合命中层：每场景的题数 + 甲方被推荐次数/有效次数 + 样例。"""
    agg: dict[str, dict] = {}
    for pname, info in platforms.items():
        for j in info.get("judgments", []):
            if j.get("layer") != "hit":
                continue
            sc = scenario_of.get(j.get("question_id") or "")
            if not sc:
                continue
            d = agg.setdefault(sc, {"name": sc, "questions": [], "valid": 0, "hit": 0})
            if j.get("question") not in d["questions"]:
                d["questions"].append(j.get("question"))
            if j.get("has_hotel_recommendations") and j.get("recommendation") is not None:
                d["valid"] += 1
                if j.get("recommendation") == "recommend":
                    d["hit"] += 1
    for d in agg.values():
        d["hit_rate"] = round(d["hit"] / d["valid"], 4) if d["valid"] else 0.0
    return list(agg.values())


def build_report_data(run) -> dict:
    m = run.measurement_json or {}
    cv = m.get("competitor_visibility") or {}
    bands = cv.get("bands") or {}
    comp: dict[str, list] = {"main": [], "secondary": []}
    for band in ("main", "secondary"):
        for mem in ((cv.get("overall") or {}).get(band) or {}).get("members", []):
            comp[band].append({
                "name": mem["name"], "rate": mem.get("overall_rate"),
                "platform_rates": mem.get("platform_rates") or {},
                "band": bands.get(mem["name"], band),
            })
    sent = (run.sentiment_json or {}).get("store_level") or {}
    return {
        "brand": getattr(run, "brand", "") or m.get("brand", ""),
        "city": getattr(run, "city", "") or m.get("city", ""),
        "collected_at": m.get("collected_at", ""),
        "question_count": len(m.get("question_fingerprint") or []),
        "hit_rate": (m.get("overall") or {}).get("overall_hit_rate"),
        "platform_hit_rates": (m.get("overall") or {}).get("platform_hit_rates") or {},
        "effective_visibility": m.get("effective_visibility"),
        "negative_rate": m.get("negative_rate_combined"),
        "miss_structure": m.get("miss_structure") or {},
        "competitors": comp,
        "scenes": _scenes(m.get("platforms") or {}, _scenario_map()),
        "attribution": m.get("attribution_dims") or {},
        "content_assets": m.get("content_assets") or [],
        "sentiment": {
            "rate": sent.get("rate"), "total": sent.get("total"),
            "negative_count": sent.get("negative_count"),
            "themes": {_THEME_CN.get(k, k): v for k, v in (sent.get("themes") or {}).items()},
        },
        "gt_facts_count": _count_facts(run.gt_facts_json),
        "cdp_facts_count": _count_facts(run.cdp_facts_json),
        "cdp_consistency": (run.cdp_facts_json or {}).get("consistency") or {},
        "cdp_stale": (run.cdp_facts_json or {}).get("stale_facts") or {},
    }


def _count_facts(facts_json) -> int:
    if not isinstance(facts_json, dict):
        return 0
    return sum(len(v) for v in (facts_json.get("facts") or {}).values() if isinstance(v, list))
```

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_report_data.py -q`
Expected: 4 passed

- [ ] **Step 5: 提交**

```bash
git add src/report/__init__.py src/report/report_data.py tests/test_report_data.py
git commit -m "报告层：数据提取 build_report_data（命中率/竞对/场景/舆情/归因/供给侧）"
```

---

## Task 2: HTML 模板骨架 + 商务蓝样式

**Files:**
- Create: `src/report/templates/geo_report.html.j2`

- [ ] **Step 1: 写模板（封面 + 章节页 + 正文 + 表格 + 页脚 + 打印样式）**

模板要点（完整 CSS 与结构，Jinja 变量与 Task 1 的 data 键一一对应）：

```jinja
<!DOCTYPE html>
<html lang="zh"><head><meta charset="UTF-8"><title>{{ brand }} AI 可见度诊断报告</title>
<style>
  :root{--blue:#1e3a8a;--blue2:#2563eb;--bluebg:#eff6ff;--ink:#111827;--mut:#6b7280;--line:#e5e7eb;}
  @page{size:A4;margin:0;}
  *{box-sizing:border-box;}
  body{margin:0;font-family:'Microsoft YaHei','Noto Sans SC',sans-serif;color:var(--ink);background:#fff;line-height:1.75;}
  .page{width:210mm;min-height:297mm;padding:22mm 20mm;margin:0 auto;position:relative;page-break-after:always;}
  .page:last-child{page-break-after:auto;}
  .foot{position:absolute;bottom:10mm;left:20mm;right:20mm;font-size:9px;color:var(--mut);
        border-top:1px solid var(--line);padding-top:4px;display:flex;justify-content:space-between;}
  /* 封面 */
  .cover{background:var(--blue);color:#fff;display:flex;flex-direction:column;justify-content:center;}
  .cover .kicker{font-size:13px;letter-spacing:2px;opacity:.8;}
  .cover h1{font-size:40px;margin:8px 0 4px;font-weight:800;}
  .cover .sub{font-size:16px;opacity:.9;}
  .cover .big{font-size:64px;font-weight:800;color:#93c5fd;margin-top:32px;line-height:1;}
  .cover .biglabel{font-size:14px;opacity:.85;}
  /* 章节分隔页 */
  .divider{background:var(--blue);color:#fff;display:flex;flex-direction:column;justify-content:center;}
  .divider .no{font-size:72px;font-weight:800;color:#60a5fa;line-height:1;}
  .divider h2{font-size:30px;margin:6px 0;font-weight:700;}
  .divider .dsub{opacity:.85;font-size:15px;}
  /* 正文 */
  h2.sec{color:var(--blue);font-size:22px;border-bottom:3px solid var(--blue2);padding-bottom:8px;margin:0 0 14px;}
  h3.sub{font-size:16px;color:var(--blue2);margin:20px 0 8px;}
  p{margin:8px 0;}
  .lede{font-size:15px;color:#374151;}
  table{width:100%;border-collapse:collapse;margin:12px 0;font-size:13px;}
  th{background:var(--bluebg);color:var(--blue);text-align:left;padding:8px 10px;border-bottom:2px solid var(--blue2);}
  td{padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top;}
  .num{font-variant-numeric:tabular-nums;font-weight:700;}
  .cards{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:12px 0;}
  .card{border:1px solid var(--line);border-left:4px solid var(--blue2);border-radius:6px;padding:10px 12px;}
  .card.risk{border-left-color:#dc2626;}
  .card h4{margin:0 0 4px;font-size:14px;}
  .card p{margin:0;font-size:12.5px;color:#374151;}
  .kpi{display:flex;gap:24px;margin:14px 0;}
  .kpi div{flex:1;}
  .kpi .v{font-size:34px;font-weight:800;color:var(--blue);line-height:1;}
  .kpi .l{font-size:12px;color:var(--mut);}
  blockquote{border-left:3px solid var(--blue2);background:var(--bluebg);margin:8px 0;padding:6px 12px;font-size:13px;color:#374151;}
  .note{font-size:11.5px;color:var(--mut);margin-top:6px;}
</style></head><body>

<!-- 封面 -->
<div class="page cover">
  <div class="kicker">AI 可见度诊断报告</div>
  <h1>{{ city }}{{ brand }}</h1>
  <div class="sub">在生成式 AI 世界里的品牌可见度</div>
  <div class="big">{{ (hit_rate*100)|round(1) }}%</div>
  <div class="biglabel">综合命中率 · 基于 {{ question_count }} 个高频问题 × 4 个主流 AI</div>
</div>

{# 后续章节：执行摘要 / ①..⑥ / 方向 / 附录，Task 3-5 逐章补 #}

</body></html>
```

- [ ] **Step 2: 提交**

```bash
git add src/report/templates/geo_report.html.j2
git commit -m "报告层：HTML 模板骨架 + 商务蓝样式（封面/章节页/正文/表格/页脚）"
```

---

## Task 3: 渲染器 `render_report`

**Files:**
- Create: `src/report/geo_report.py`
- Test: `tests/test_geo_report.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_geo_report.py
"""渲染冒烟：含关键业务字符串 + 不含技术词。"""
from src.report.geo_report import render_report


_DATA = {"brand": "香格里拉", "city": "福州", "hit_rate": 0.7873, "question_count": 28,
         "platform_hit_rates": {"deepseek": 0.9375}, "competitors": {"main": [], "secondary": []},
         "scenes": [], "attribution": {}, "sentiment": {"themes": {}}, "content_assets": []}
_NARR = {"exec_summary": {"conclusion": "结论", "highlights": [], "risks": [], "priority": []},
         "sections": {}}


def test_render_contains_brand_and_rate():
    html = render_report(_DATA, _NARR, brand="香格里拉", city="福州", date="2026-10-14")
    assert "福州香格里拉" in html and "78.7%" in html


def test_render_has_no_technical_words():
    html = render_report(_DATA, _NARR, brand="香格里拉", city="福州", date="2026-10-14")
    for bad in ("脚本", "JSON", "字段", "measurement", "judgment"):
        assert bad not in html, f"报告不应出现技术词：{bad}"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_geo_report.py -q`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现**

```python
# src/report/geo_report.py
"""报告渲染：数据 + 业务叙述 → 商务蓝 HTML（Jinja2）。"""
from __future__ import annotations
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape

_TDIR = Path(__file__).parent / "templates"


def _env() -> Environment:
    return Environment(loader=FileSystemLoader(str(_TDIR)),
                       autoescape=select_autoescape(["html"]))


def render_report(data: dict, narrative: dict, *, brand: str, city: str, date: str) -> str:
    tpl = _env().get_template("geo_report.html.j2")
    return tpl.render(**data, narrative=narrative, brand=brand, city=city, date=date)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_geo_report.py -q`
Expected: 2 passed

- [ ] **Step 5: 提交**

```bash
git add src/report/geo_report.py tests/test_geo_report.py
git commit -m "报告层：Jinja2 渲染器 render_report"
```

---

## Task 4: 逐章填充模板（①-⑥ + 方向）

**Files:**
- Modify: `src/report/templates/geo_report.html.j2`（替换 Task 2 的占位注释）

每章一节 `.page`，绑定字段如下（Jinja 片段示例，逐章照此写）：

- [ ] **Step 1: 执行摘要页**（`narrative.exec_summary`）

```jinja
<div class="page">
  <h2 class="sec">执行摘要</h2>
  <p class="lede">{{ narrative.exec_summary.conclusion }}</p>
  <div class="cards">
    {% for h in narrative.exec_summary.highlights %}
    <div class="card"><h4>{{ h.title }}</h4><p>{{ h.text }}</p></div>
    {% endfor %}
    {% for r in narrative.exec_summary.risks %}
    <div class="card risk"><h4>{{ r.title }}</h4><p>{{ r.text }}</p></div>
    {% endfor %}
  </div>
  <h3 class="sub">优先方向</h3>
  <ul>{% for p in narrative.exec_summary.priority %}<li>{{ p }}</li>{% endfor %}</ul>
  <div class="foot"><span>{{ city }}{{ brand }} · AI 可见度诊断报告</span><span>01</span></div>
</div>
```

- [ ] **Step 2: ① 我们做得怎么样**（`hit_rate` / `platform_hit_rates` / `effective_visibility`）

```jinja
<div class="page">
  <h2 class="sec">一、我们做得怎么样</h2>
  <div class="kpi">
    <div><div class="v">{{ (hit_rate*100)|round(1) }}%</div><div class="l">综合命中率</div></div>
    <div><div class="v">{{ (effective_visibility*100)|round(1) }}%</div><div class="l">有效可见度（含舆情折损）</div></div>
  </div>
  <table><tr><th>AI 平台</th><th>命中率</th></tr>
    {% for p, r in platform_hit_rates.items() %}<tr><td>{{ p }}</td><td class="num">{{ (r*100)|round(1) }}%</td></tr>{% endfor %}
  </table>
  <h3 class="sub">命中率是怎么得出的</h3>
  <p class="lede">{{ narrative.hit_rate_explain }}</p>
  <div class="foot"><span>{{ city }}{{ brand }} · AI 可见度诊断报告</span><span>02</span></div>
</div>
```

- [ ] **Step 3: ② 主战场四场景**（`scenes` + `narrative.scenes`）

```jinja
{% for s in scenes %}
<div class="page">
  <h2 class="sec">二、AI 可见度主战场 · {{ s.name }}</h2>
  <div class="kpi"><div><div class="v">{{ (s.hit_rate*100)|round(1) }}%</div><div class="l">该场景命中率</div></div></div>
  <h3 class="sub">这一场景，用户会这样问 AI</h3>
  <ul>{% for q in s.questions %}<li>{{ q }}</li>{% endfor %}</ul>
  <h3 class="sub">AI 的回答</h3>
  <p class="lede">{{ narrative.scenes[s.name].summary }}</p>
  {% for q in narrative.scenes[s.name].quotes %}<blockquote>{{ q }}</blockquote>{% endfor %}
  <div class="foot"><span>{{ city }}{{ brand }} · AI 可见度诊断报告</span><span>03</span></div>
</div>
{% endfor %}
```

- [ ] **Step 4: ③ 竞对追赶**（`competitors` + `narrative.competitors`）

```jinja
<div class="page">
  <h2 class="sec">三、威胁：竞对正在追赶</h2>
  <p class="lede">{{ narrative.competitors.summary }}</p>
  <table><tr><th>品牌</th><th>命中率</th><th>定位</th></tr>
    <tr><td>{{ city }}{{ brand }}（我们）</td><td class="num">{{ (hit_rate*100)|round(1) }}%</td><td>—</td></tr>
    {% for c in competitors.main %}<tr><td>{{ c.name }}</td><td class="num">{{ (c.rate*100)|round(1) }}%</td><td>主要竞对</td></tr>{% endfor %}
    {% for c in competitors.secondary %}<tr><td>{{ c.name }}</td><td class="num">{{ (c.rate*100)|round(1) }}%</td><td>次要竞对</td></tr>{% endfor %}
  </table>
  <p class="note">{{ narrative.competitors.source_note }}</p>
  <div class="foot"><span>{{ city }}{{ brand }} · AI 可见度诊断报告</span><span>04</span></div>
</div>
```

- [ ] **Step 5: ④ 舆情拖累**（`sentiment` + `narrative.sentiment`）

```jinja
<div class="page">
  <h2 class="sec">四、拖累：舆情在拉低可见度</h2>
  <div class="kpi">
    <div><div class="v">{{ (sentiment.rate*100)|round(1) }}%</div><div class="l">负面率</div></div>
    <div><div class="v">{{ sentiment.negative_count }}</div><div class="l">负面条目</div></div>
  </div>
  <table><tr><th>负面主题</th><th>条目</th></tr>
    {% for t, n in sentiment.themes.items() %}<tr><td>{{ t }}</td><td class="num">{{ n }}</td></tr>{% endfor %}
  </table>
  <p class="lede">{{ narrative.sentiment.summary }}</p>
  <div class="foot"><span>{{ city }}{{ brand }} · AI 可见度诊断报告</span><span>05</span></div>
</div>
```

- [ ] **Step 6: ⑤ 被低估的资产**（`content_assets` / `gt_facts_count` / `cdp_facts_count` / `cdp_consistency` / `cdp_stale` + `narrative.assets`）

```jinja
<div class="page">
  <h2 class="sec">五、被低估的资产：AI 眼中的 {{ city }}{{ brand }}</h2>
  <h3 class="sub">AI 实际引用了什么</h3>
  <table><tr><th>AI 引用的内容</th><th>出现次数</th></tr>
    {% for a in content_assets[:12] %}<tr><td>{{ a.content }}</td><td class="num">{{ a.count }}</td></tr>{% endfor %}
  </table>
  <p class="lede">{{ narrative.assets.summary }}</p>
  <div class="foot"><span>{{ city }}{{ brand }} · AI 可见度诊断报告</span><span>06</span></div>
</div>
```

- [ ] **Step 7: ⑥ 归因**（`attribution` + `narrative.attribution`）

```jinja
<div class="page">
  <h2 class="sec">六、为什么：归因分析</h2>
  <table><tr><th>维度</th><th>优势条目</th><th>真实劣势</th></tr>
    {% for dim, d in attribution.items() %}
    <tr><td>{{ dim }}</td><td class="num">{{ d.advantage }}</td><td class="num">{{ d.true_disadvantage }}</td></tr>
    {% endfor %}
  </table>
  <h3 class="sub">最该解决的短板</h3>
  {% for q in narrative.attribution.key_quotes %}<blockquote>{{ q }}</blockquote>{% endfor %}
  <div class="foot"><span>{{ city }}{{ brand }} · AI 可见度诊断报告</span><span>07</span></div>
</div>
```

- [ ] **Step 8: 方向页**（`narrative.directions`）

```jinja
<div class="page">
  <h2 class="sec">七、方向</h2>
  <ul>{% for d in narrative.directions %}<li><b>{{ d.title }}</b> —— {{ d.text }}</li>{% endfor %}</ul>
  <div class="foot"><span>{{ city }}{{ brand }} · AI 可见度诊断报告</span><span>08</span></div>
</div>
```

- [ ] **Step 9: 跑渲染测试 + 提交**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_geo_report.py -q`
Expected: 2 passed

```bash
git add src/report/templates/geo_report.html.j2
git commit -m "报告层：①-⑥ 各章 + 方向页模板（绑定 report_data 字段）"
```

---

## Task 5: 附录（逐题命中明细 + 口径与方法）

**Files:**
- Modify: `src/report/templates/geo_report.html.j2`
- Modify: `src/report/report_data.py`（加 `judgments` 提取）
- Modify: `tests/test_report_data.py`

- [ ] **Step 1: 测试——附录数据（每平台逐题）**

```python
def test_appendix_judgments_per_platform():
    d = build_report_data(_run(_M))
    ds = d["appendix"]["deepseek"]
    assert ds[0]["question_id"] == "hit_b1"
    assert ds[0]["recommended"] is True
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_report_data.py::test_appendix_judgments_per_platform -q`
Expected: FAIL（KeyError: 'appendix'）

- [ ] **Step 3: 实现——`report_data.py` 加 `_appendix`**

```python
def _appendix(platforms: dict) -> dict:
    out = {}
    for pname, info in platforms.items():
        rows = []
        for j in info.get("judgments", []):
            if j.get("layer") != "hit":
                continue
            rows.append({
                "question_id": j.get("question_id"),
                "question": j.get("question"),
                "recommended": j.get("recommendation") == "recommend",
                "summary": "；".join(j.get("referred_content") or []) or "—",
            })
        out[pname] = rows
    return out
```

并在 `build_report_data` 的返回 dict 里加 `"appendix": _appendix(m.get("platforms") or {})`。

- [ ] **Step 4: 模板加附录页**

```jinja
{% for p, rows in appendix.items() %}
<div class="page">
  <h2 class="sec">附录 · {{ p }} 逐题命中明细</h2>
  <table><tr><th>#</th><th>问题</th><th>是否推荐</th><th>命中摘要</th></tr>
    {% for r in rows %}<tr><td>{{ loop.index }}</td><td>{{ r.question }}</td>
      <td>{{ "推荐" if r.recommended else "未推荐" }}</td><td>{{ r.summary }}</td></tr>{% endfor %}
  </table>
  <div class="foot"><span>{{ city }}{{ brand }} · AI 可见度诊断报告</span><span>附</span></div>
</div>
{% endfor %}
<div class="page">
  <h2 class="sec">附录 · 口径与方法</h2>
  <p class="lede">{{ narrative.method }}</p>
  <p class="note">数据时间：{{ date }}</p>
</div>
```

- [ ] **Step 5: 跑测试 + 提交**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_report_data.py tests/test_geo_report.py -q`
Expected: 全部 passed

```bash
git add src/report/report_data.py src/report/templates/geo_report.html.j2 tests/test_report_data.py
git commit -m "报告层：附录（逐题命中明细 + 口径与方法）"
```

---

## Task 6: CLI + 首份叙述 + 生成 HTML

**Files:**
- Create: `scripts/build_geo_report.py`
- Create: `src/report/narratives/福州香格里拉.py`
- Output: `output/福州香格里拉_AI可见度诊断报告.html`

- [ ] **Step 1: 写 CLI**

```python
# scripts/build_geo_report.py
"""生成 AI 可见度诊断报告 HTML。用法：
  PYTHONPATH=. .venv/bin/python scripts/build_geo_report.py <run_id> [--out output/]
"""
import argparse, asyncio, importlib, os, sys
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from src.config import settings
from src.models.collection_run import CollectionRun
from src.report.report_data import build_report_data
from src.report.geo_report import render_report


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("run_id")
    p.add_argument("--out", default="output")
    a = p.parse_args()
    engine = create_async_engine(settings.database_url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        run = await db.get(CollectionRun, a.run_id)
        if run is None:
            print(f"错误: run {a.run_id} 不存在"); sys.exit(1)
        data = build_report_data(run)
    await engine.dispose()
    mod = importlib.import_module(f"src.report.narratives.{data['city']}{data['brand']}")
    os.makedirs(a.out, exist_ok=True)
    html = render_report(data, mod.NARRATIVE, brand=data["brand"], city=data["city"],
                         date=(data.get("collected_at") or "")[:10])
    path = os.path.join(a.out, f"{data['city']}{data['brand']}_AI可见度诊断报告.html")
    open(path, "w", encoding="utf-8").write(html)
    print(f"已生成 {path}")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: 主 agent 撰写 `src/report/narratives/福州香格里拉.py`**

按设计文档第 3/5 节撰写 `NARRATIVE`（业务语言、无技术词）：`exec_summary`（结论+3优势+2风险+优先方向）、`hit_rate_explain`、`scenes`（4 场景的 summary + quotes）、`competitors`（summary + source_note）、`sentiment`、`assets`、`attribution`（key_quotes）、`directions`、`method`。引用的 AI 原话取自 V6 快照（`referred_content` / `attribution_result.*_dims[].evidence`），逐字。

- [ ] **Step 3: 生成并自检**

Run: `PYTHONPATH=. .venv/bin/python scripts/build_geo_report.py 535b8108-54fa-4198-931e-37c76d0a5c53`
Expected: `已生成 output/福州香格里拉_AI可见度诊断报告.html`

自检：打开文件 grep 无"脚本/JSON/字段/measurement/judgment"；命中率 78.7%、竞对 53.4% 等数字与设计一致。

- [ ] **Step 4: 提交**

```bash
git add scripts/build_geo_report.py src/report/narratives/福州香格里拉.py
git commit -m "报告层：CLI + 首份叙述（福州香格里拉）+ 生成 HTML"
```

---

## Task 7: 预览 → 转 PDF

- [ ] **Step 1: 用户浏览器预览**

用 Chrome 打开 `output/福州香格里拉_AI可见度诊断报告.html`，逐页确认版式与内容。按反馈迭代（改 narrative 或模板后重跑 CLI）。

- [ ] **Step 2: 确认后转 PDF**

```bash
# md2pdf 面向 md；HTML→PDF 用同一 Chrome 引擎
"/usr/bin/google-chrome" --headless --disable-gpu --no-sandbox \
  --print-to-pdf="output/福州香格里拉_AI可见度诊断报告.pdf" --no-pdf-header-footer \
  "file://$PWD/output/福州香格里拉_AI可见度诊断报告.html"
```

- [ ] **Step 3: 回读校验 PDF 页数与关键数字**

```bash
python3 -c "import pdfplumber;pdf=pdfplumber.open('output/福州香格里拉_AI可见度诊断报告.pdf');print('pages',len(pdf.pages));print((pdf.pages[0].extract_text() or '')[:80])"
```

- [ ] **Step 4: 提交 + 导桌面**

```bash
cp "output/福州香格里拉_AI可见度诊断报告.html" "output/福州香格里拉_AI可见度诊断报告.pdf" ~/Desktop/
git add src/report scripts/build_geo_report.py
git commit -m "报告层：HTML→PDF 交付（福州香格里拉）"
```

---

## Self-Review

**1. Spec coverage**：设计 §3 章节 → Task 4（①-⑥+方向）+ Task 5（附录）；§4 风格 → Task 2（CSS）；§5 口径 → Task 4 Step 2（命中率定义）+ Task 5（方法）+ narrative（来源声明）；§6 工作流 → Task 6-7；§2 数据 → Task 1。**全覆盖。**

**2. Placeholder scan**：Task 6 Step 2 的叙述内容标注"按设计文档撰写"——这是内容创作任务（主 agent 产出），非代码占位；其余步骤均含可执行代码/命令。

**3. Type consistency**：`build_report_data` 返回键（`hit_rate`/`platform_hit_rates`/`competitors`/`scenes`/`sentiment`/`attribution`/`content_assets`/`appendix`）在 Task 4/5 模板中引用一致；`render_report(data, narrative, *, brand, city, date)` 签名在 Task 3 定义、Task 6 调用一致。
