# P1-1 Action 效果归因 实现计划 v2

**日期:** 2026-05-30 | **状态:** Plan | **审阅:** 已通过方向评审，v2 修正全部 P0/P1
**依赖:** Phase 12 Dashboard | **前置:** published_at 字段迁移 (Stage 0)

---

## 一、目标

让趋势归因页从占位 UI 变成可用的运营工具。回答 GEO 核心问题：

> **发布优化内容后，AI 对品牌的认知是否改善了？**

注意：目标是**解释变化**，不是画趋势线。

---

## 二、修正清单（v1 → v2）

| # | 问题 | v1 做法 | v2 修正 |
|---|------|---------|---------|
| P0-1 | 发布时间 | `pkg.created_at` | 新增 `published_at` 字段，无此字段的 ContentPackage 不进归因 |
| P0-2 | 绑定关系 | 一对一 | 支持一对多/多对一，归因以"发布事件"为中心 |
| P0-3 | 前后窗口 | 固定 2 个 snapshot | 引入 `pre_window_days` / `post_window_days` / `absorption_lag_days` |
| P0-4 | 混淆因素 | 仅 GT 变更/平台失败 | 扩展为 7 类：GT/Prompt/Template/Model/平台/多Action/Content未索引 |
| P0-5 | 归因标签 | 中文字符串 | 结构化：`label_key` + `label_cn` + `confidence` + `reason` + `confounders` |
| P0-6 | 变化阈值 | 无 | 每个 KPI 设置最小有效变化阈值 |
| P0-7 | 目标 KPI 校验 | 直接读字典 key | 统一读取函数 + issue_type 兜底映射 |
| P0-8 | 事件标记 | 旁边列表 | Chart.js 时间轴 + tooltip 联动 |
| P0-9 | HTMX 切换 | 完整页面塞进局部 | 拆分 shell/_content，fragment endpoint 返回局部 HTML |
| P0-10 | Chart 生命周期 | 无处理 | destroy → recreate 在 htmx:afterSwap |

---

## 三、Stage 0 — published_at Migration

### Task 0: 添加 published_at 字段

**文件:** `alembic/versions/xxxx_phase12_add_published_at.py`

```sql
ALTER TABLE content_packages ADD COLUMN published_at TIMESTAMPTZ;
ALTER TABLE content_packages ADD COLUMN published_platform VARCHAR(50) DEFAULT '';
```

在 `src/models/content_package.py` 中新增：
```python
published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
published_platform: Mapped[str] = mapped_column(String(50), default="")
```

更新 `mark-published` API 端点在设置 `publish_url` 时同时写入 `published_at = now()`。

---

## 四、实现任务

### Task 1: 10 KPI 统一读取函数

**文件:** `src/view_models/trends.py`

```python
def get_kpi_value(snapshot: MetricsSnapshot, kpi_key: str) -> float:
    """Read KPI value from MetricsSnapshot — ORM field or details JSON."""
    # 5 基础 KPI — ORM 列
    if hasattr(snapshot, kpi_key) and kpi_key in (
        "sov", "first_rec_rate", "accuracy_rate", "completeness_rate", "citation_rate"
    ):
        return getattr(snapshot, kpi_key, 0.0) or 0.0
    # 5 扩展 KPI — details.extended_kpis
    ek = (snapshot.details or {}).get("extended_kpis", {})
    return ek.get(kpi_key, {}).get("value", 0.0) if isinstance(ek.get(kpi_key), dict) else 0.0


def get_kpi_threshold(kpi_key: str) -> float:
    """Minimum meaningful change threshold per KPI."""
    return {
        "sov": 0.05, "first_rec_rate": 0.05, "accuracy_rate": 0.05,
        "completeness_rate": 0.05, "citation_rate": 0.03,
        "scenario_recall": 0.05, "semantic_stability": 0.05,
        "differentiation": 0.05, "cross_platform_consistency": 0.05,
        "recommendation_quality": 0.03,
    }.get(kpi_key, 0.05)


def infer_target_kpi(theme: ActionTheme) -> list[str]:
    """Infer target KPI from issue_type if expected_kpi_impact is empty."""
    if theme.expected_kpi_impact and isinstance(theme.expected_kpi_impact, dict):
        keys = [k for k in theme.expected_kpi_impact if k in KPI_KEYS]
        if keys:
            return keys[:3]
    mapping = {
        "citation_low": ["citation_rate"],
        "accuracy_low": ["accuracy_rate"],
        "completeness_low": ["completeness_rate"],
        "scenario_missing": ["scenario_recall"],
        "differentiation_missing": ["differentiation"],
        "recommendation_weak": ["recommendation_quality"],
    }
    return mapping.get(theme.issue_type, ["accuracy_rate"])
```

---

### Task 2: 归因窗口与混淆因素

**文件:** `src/view_models/trends.py`

```python
# 窗口配置（可后续做成 settings）
PRE_WINDOW_DAYS = 14
POST_WINDOW_DAYS = 14
ABSORPTION_LAG_DAYS = 7
MIN_PRE_SNAPSHOTS = 2
MIN_POST_SNAPSHOTS = 2

async def _build_attribution(brand_id, snapshots, db):
    """归因表：为每个已发布 Action 计算 pre/post KPI 对比."""
    # 查询已发布的 ActionTheme
    themes = await db.execute(
        select(ActionTheme).where(
            ActionTheme.brand_id == brand_id,
            ActionTheme.status.in_(["published_marked", "verification_pending", "verified"]),
        ).order_by(ActionTheme.updated_at.desc())
    )
    themes = themes.scalars().all()
    
    rows = []
    for theme in themes:
        # 获取关联 ContentPackage（必须有 published_at）
        pkgs = await db.execute(
            select(ContentPackage).where(
                ContentPackage.action_theme_id == theme.id,
                ContentPackage.published_at.isnot(None),
            ).order_by(desc(ContentPackage.published_at))
        )
        pkgs = pkgs.scalars().all()
        
        for pkg in pkgs:
            publish_dt = pkg.published_at
            if not publish_dt:
                continue
            
            post_start = publish_dt + timedelta(days=ABSORPTION_LAG_DAYS)
            pre_start = publish_dt - timedelta(days=PRE_WINDOW_DAYS)
            
            pre = [s for s in snapshots if pre_start <= s.week_start < publish_dt.date()][-MIN_PRE_SNAPSHOTS:]
            post = [s for s in snapshots if s.week_start >= post_start.date()][:MIN_POST_SNAPSHOTS]
            
            if len(pre) < MIN_PRE_SNAPSHOTS or len(post) < MIN_POST_SNAPSHOTS:
                continue
            
            # 目标 KPI
            target_kpis = infer_target_kpi(theme)
            
            # 混淆因素检测（全部异步）
            confounders = []
            if await _gt_changed_during(brand_id, pre[0].week_start, post[-1].week_start, db):
                confounders.append({"type": "gt_update", "severity": "high", "detail": "GT 版本在归因窗口内变更"})
            if await _prompt_changed_during(brand_id, pre[0].week_start, post[-1].week_start, db):
                confounders.append({"type": "prompt_change", "severity": "high", "detail": "Prompt 模板在归因窗口内变更"})
            if any((s.failure_rate or 0) > 0.3 for s in post):
                confounders.append({"type": "platform_failure", "severity": "medium", "detail": "post 窗口部分平台失败"})
            
            for kpi_key in target_kpis[:3]:
                pre_vals = [get_kpi_value(s, kpi_key) for s in pre]
                post_vals = [get_kpi_value(s, kpi_key) for s in post]
                pre_avg = sum(pre_vals) / len(pre_vals)
                post_avg = sum(post_vals) / len(post_vals)
                change = post_avg - pre_avg
                threshold = get_kpi_threshold(kpi_key)
                
                result = compute_attribution(
                    pre_avg, post_avg, len(pre) + len(post),
                    bool(confounders), change, threshold,
                )
                
                rows.append({
                    "theme_id": str(theme.id),
                    "theme_title": theme.title,
                    "publish_date": publish_dt.isoformat()[:10],
                    "publish_url": pkg.publish_url or "",
                    "target_kpi": kpi_key,
                    "kpi_label": KPI_DISPLAY_NAMES.get(kpi_key, kpi_key),
                    "pre_avg": round(pre_avg, 4),
                    "post_avg": round(post_avg, 4),
                    "change": round(change, 4),
                    "change_display": f"{'+' if change > 0 else ''}{round(change * 100, 1)}%",
                    "is_meaningful": abs(change) >= threshold,
                    "threshold": threshold,
                    "sample_size": len(pre) + len(post),
                    "pre_sample_size": len(pre),
                    "post_sample_size": len(post),
                    "label_key": result["label_key"],
                    "label_cn": result["label_cn"],
                    "confidence": result["confidence"],
                    "confounders": confounders,
                    "reason": result["reason"],
                    "needs_more_data": result["needs_more_data"],
                })
    
    return rows
```

---

### Task 3: 结构化归因标签

**文件:** `src/view_models/trends.py`（替换 `compute_attribution_label`）

```python
def compute_attribution(pre_avg, post_avg, sample_size, has_confounders, change, threshold) -> dict:
    """Structured attribution result."""
    if sample_size < 4:
        return {"label_key": "insufficient_sample", "label_cn": "样本不足",
                "confidence": "low", "reason": f"仅 {sample_size} 个快照，不足以判断效果。",
                "needs_more_data": True}

    if has_confounders:
        return {"label_key": "confounded", "label_cn": "存在混淆因素",
                "confidence": "low", "reason": "归因窗口内检测到 GT/Prompt/平台变化，无法归因到 Action。",
                "needs_more_data": False}

    if abs(change) < threshold:
        direction = "提升" if change > 0 else "下降"
        return {"label_key": "no_obvious_effect", "label_cn": "无明显效果",
                "confidence": "medium",
                "reason": f"变化 {abs(change)*100:.1f}% 低于最小阈值 {threshold*100:.0f}%，{direction}可能是随机波动。",
                "needs_more_data": True}

    if change > threshold:
        return {"label_key": "possible_action_effect", "label_cn": "可能由 Action 导致",
                "confidence": "medium",
                "reason": f"发布后提升 {change*100:.1f} 个百分点，超过阈值 {threshold*100:.0f}%。",
                "needs_more_data": True}
    else:
        return {"label_key": "negative_effect_possible", "label_cn": "可能存在负面效果",
                "confidence": "medium",
                "reason": f"发布后下降 {abs(change)*100:.1f} 个百分点。建议排查 Action 内容或外部事件。",
                "needs_more_data": True}
```

---

### Task 4: trends ViewModel — 趋势 + 事件 + 归因

**文件:** `src/view_models/trends.py`（完整实现）

```python
ALL_KPI_KEYS = [
    "sov", "first_rec_rate", "accuracy_rate", "completeness_rate", "citation_rate",
    "scenario_recall", "semantic_stability", "differentiation",
    "cross_platform_consistency", "recommendation_quality",
]

async def build_trends_vm(brand, range_str, user, db) -> dict:
    limit = {"week": 12, "month": 24, "quarter": 8}[range_str]
    
    # 只拉已完成分析的 snapshots (P1-1)
    runs = await db.execute(
        select(CollectionRun.id).where(
            CollectionRun.brand_id == brand.id,
            CollectionRun.analysis_status == "completed",
        ).order_by(desc(CollectionRun.analysis_completed_at)).limit(limit)
    )
    run_ids = [r[0] for r in runs.all()]
    
    if not run_ids:
        return {"brand": {"id": str(brand.id), "name": brand.name},
                "dates": [], "series": {}, "events": [], "attribution": [],
                "range": range_str, "has_data": False}
    
    snapshots = (await db.execute(
        select(MetricsSnapshot).where(
            MetricsSnapshot.collection_run_id.in_(run_ids),
            MetricsSnapshot.platform.is_(None),
            MetricsSnapshot.dimension.is_(None),
        ).order_by(MetricsSnapshot.week_start)
    )).scalars().all()
    
    dates = [s.week_start.isoformat()[:10] for s in snapshots]
    series = {}
    for kpi in ALL_KPI_KEYS:
        series[kpi] = [round(get_kpi_value(s, kpi), 4) for s in snapshots]
    
    events = await _build_events(brand.id, dates[0], dates[-1], db)
    attribution = await _build_attribution(brand.id, snapshots, db)
    
    return {"brand": {"id": str(brand.id), "name": brand.name},
            "dates": dates, "series": series, "events": events,
            "attribution": attribution, "range": range_str, "has_data": True}


async def _build_events(brand_id, date_from, date_to, db) -> list:
    """Build event markers: GT versions, content publishes, prompt changes."""
    events = []
    
    # GT version changes
    gt_versions = await db.execute(
        select(GroundTruthVersion).where(
            GroundTruthVersion.brand_id == brand_id,
        ).order_by(GroundTruthVersion.created_at)
    )
    for gt in gt_versions.scalars().all():
        if gt.created_at:
            events.append({
                "type": "gt_update", "date": gt.created_at.isoformat()[:10],
                "label": f"GT v{gt.version}", "severity": "info",
            })
    
    # Content publishes
    pkgs = await db.execute(
        select(ContentPackage).where(
            ContentPackage.brand_id == brand_id,
            ContentPackage.published_at.isnot(None),
            ContentPackage.publish_url != "",
        ).order_by(ContentPackage.published_at)
    )
    for pkg in pkgs.scalars().all():
        events.append({
            "type": "content_published",
            "date": pkg.published_at.isoformat()[:10],
            "label": pkg.title or "Content Package",
            "severity": "info",
        })
    
    # Prompt version changes (from CollectionRun)
    runs = await db.execute(
        select(CollectionRun).where(
            CollectionRun.brand_id == brand_id,
            CollectionRun.prompt_version_id.isnot(None),
        ).order_by(CollectionRun.started_at)
    )
    prev_pv = None
    for run in runs.scalars().all():
        if run.prompt_version_id and run.prompt_version_id != prev_pv:
            events.append({
                "type": "prompt_change",
                "date": run.started_at.isoformat()[:10] if run.started_at else "",
                "label": "Prompt 变更", "severity": "warning",
            })
        prev_pv = run.prompt_version_id
    
    return sorted(events, key=lambda e: e["date"])
```

---

### Task 5: 趋势页模板 — shell + _content 拆分

**文件:** `src/templates/trends/index.html`（页面 shell）

```html
{% extends "base.html" %}
{% block title %}{{ vm.brand.name }} — 趋势归因{% endblock %}
{% block content %}
<h1 class="font-heading text-2xl font-bold text-text mb-5">{{ vm.brand.name }} — 趋势与归因</h1>
<div class="flex items-center gap-3 mb-4">
    <div class="flex bg-slate-100 rounded-lg p-0.5">
        {% for r, rk in [('周','week'),('月','month'),('季','quarter')] %}
        <button class="px-4 py-1.5 text-sm rounded-md cursor-pointer transition-colors
                       {% if vm.range == rk %}bg-white shadow-sm text-text{% else %}text-slate-600{% endif %}"
                hx-get="/brands/{{ vm.brand.id }}/trends-fragment?range={{ rk }}"
                hx-target="#trends-content" hx-swap="innerHTML">{{ r }}</button>
        {% endfor %}
    </div>
</div>
<div id="trends-content">
    {% include "trends/_content.html" %}
</div>
{% endblock %}
```

**文件:** `src/templates/trends/_content.html`（HTMX 局部内容）

```html
{% from "partials/components/empty_state.html" import empty_state %}

{% if not vm.has_data %}
{{ empty_state("暂无趋势数据", "完成至少 2 次采集后，KPI 趋势图将在此展示。") }}
{% else %}

<!-- KPI 趋势图 -->
<div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
    <div class="bg-white rounded-xl p-5 shadow-sm border border-gray-100 chart-container">
        <h3 class="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3">声量与推荐</h3>
        <canvas id="chart-sov"></canvas>
    </div>
    <div class="bg-white rounded-xl p-5 shadow-sm border border-gray-100 chart-container">
        <h3 class="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3">准确与完整</h3>
        <canvas id="chart-acc"></canvas>
    </div>
</div>

<!-- 事件时间轴 -->
{% if vm.events %}
<div class="bg-white rounded-xl p-5 shadow-sm border border-gray-100 mb-4">
    <h3 class="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3">关键事件</h3>
    <div class="flex flex-wrap gap-1.5">
        {% for ev in vm.events %}
        <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs
                     {% if ev.type == 'gt_update' %}bg-blue-100 text-blue-700
                     {% elif ev.type == 'content_published' %}bg-green-100 text-green-700
                     {% elif ev.type == 'prompt_change' %}bg-amber-100 text-amber-700
                     {% else %}bg-slate-100 text-slate-600{% endif %}">
            {{ ev.date }} — {{ ev.label }}</span>
        {% endfor %}
    </div>
</div>
{% endif %}

<!-- 归因表 -->
{% if vm.attribution %}
<div class="bg-white rounded-xl p-5 shadow-sm border border-gray-100">
    <h3 class="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3">Action 效果验证</h3>
    <div class="overflow-x-auto">
        <table class="w-full text-sm">
            <thead>
                <tr class="border-b border-gray-200 text-left text-xs text-slate-500 uppercase">
                    <th class="py-2 pr-2">Action</th><th class="py-2 pr-2">发布时间</th>
                    <th class="py-2 pr-2">KPI</th><th class="py-2 pr-2">发布前</th>
                    <th class="py-2 pr-2">发布后</th><th class="py-2 pr-2">变化</th>
                    <th class="py-2 pr-2">样本</th><th class="py-2 pr-2">归因</th>
                </tr>
            </thead>
            <tbody>
                {% for row in vm.attribution %}
                <tr class="border-b border-gray-100 hover:bg-slate-50">
                    <td class="py-2 pr-2 font-medium text-text max-w-[200px] truncate" title="{{ row.theme_title }}">{{ row.theme_title }}</td>
                    <td class="py-2 pr-2 text-slate-500">{{ row.publish_date }}</td>
                    <td class="py-2 pr-2 text-xs">{{ row.kpi_label }}</td>
                    <td class="py-2 pr-2">{{ (row.pre_avg * 100)|round|int }}%</td>
                    <td class="py-2 pr-2">{{ (row.post_avg * 100)|round|int }}%</td>
                    <td class="py-2 pr-2 {% if row.change > 0 %}text-green-600{% else %}text-red-600{% endif %} font-medium">{{ row.change_display }}</td>
                    <td class="py-2 pr-2 text-slate-400">{{ row.sample_size }}</td>
                    <td class="py-2 pr-2">
                        <span class="badge {% if row.label_key == 'possible_action_effect' %}badge-success
                                          {% elif row.label_key == 'no_obvious_effect' %}badge-pending
                                          {% elif row.label_key == 'insufficient_sample' %}badge-tier-D
                                          {% elif row.label_key == 'confounded' %}badge-p1
                                          {% else %}badge-pending{% endif %}"
                              title="置信度: {{ row.confidence }} | {{ row.reason }}">{{ row.label_cn }}</span>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</div>
{% else %}
{{ empty_state("暂无归因数据", "发布 Content 并完成复测后，Action 效果对比和归因分析将在此展示。") }}
{% endif %}

{% endif %}

<script>
(function() {
    var dates = {{ vm.dates | tojson }};
    var series = {{ vm.series | tojson }};
    if (!dates.length) return;

    function destroyChart(id) {
        if (window.geoCharts && window.geoCharts[id]) {
            window.geoCharts[id].destroy();
            delete window.geoCharts[id];
        }
    }

    function makeChart(id, kpis) {
        destroyChart(id);
        var ctx = document.getElementById(id);
        if (!ctx) return;
        var colors = ['#1E40AF', '#3B82F6', '#F59E0B', '#22c55e', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#f97316', '#84cc16'];
        var datasets = kpis.map(function(kpi, i) {
            return {
                label: kpi,
                data: series[kpi] || [],
                borderColor: colors[i % 10],
                backgroundColor: colors[i % 10] + '20',
                tension: 0.3, fill: false, pointRadius: 3,
            };
        });
        window.geoCharts = window.geoCharts || {};
        window.geoCharts[id] = new Chart(ctx, {
            type: 'line',
            data: { labels: dates, datasets: datasets },
            options: {
                responsive: true,
                plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, padding: 15, font: { size: 11 } } } },
                scales: {
                    y: { ticks: { callback: function(v) { return (v * 100).toFixed(0) + '%'; } } },
                    x: { ticks: { maxTicksLimit: 10, font: { size: 10 } } }
                },
                interaction: { intersect: false, mode: 'index' },
            }
        });
    }

    makeChart('chart-sov', ['sov', 'citation_rate', 'first_rec_rate']);
    makeChart('chart-acc', ['accuracy_rate', 'completeness_rate']);
})();
</script>
```

---

### Task 6: HTMX fragment endpoint

**文件:** `src/main.py`

```python
@app.get("/brands/{brand_id}/trends-fragment", response_class=HTMLResponse)
async def trends_fragment(request: Request, brand_id: str,
                          range_str: str = Query("month", pattern="^(week|month|quarter)$"),
                          user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    """Return trends content fragment for HTMX range switch."""
    brand = await get_org_brand_or_404(brand_id, user, db)
    from src.view_models.trends import build_trends_vm
    vm = await build_trends_vm(brand, range_str, user, db)
    return _render(request, "trends/_content.html", {"vm": vm})
```

更新主趋势页路由使用 `range_str` 参数：
```python
@app.get("/brands/{brand_id}/trends", response_class=HTMLResponse)
async def trends_page(request: Request, brand_id: str,
                      range_str: str = Query("month", pattern="^(week|month|quarter)$"),
                      ...):
    """Trends & attribution page."""
    brand = await get_org_brand_or_404(brand_id, user, db)
    from src.view_models.trends import build_trends_vm
    vm = await build_trends_vm(brand, range_str, user, db)
    org_brands = await _get_org_brands(user, db)
    return _render(request, "trends/index.html", _page_context(
        request, "trends", org_brands,
        current_brand_id=str(brand.id), current_brand_name=brand.name, vm=vm,
    ))
```

---

### Task 7: Chart.js 生命周期管理

**文件:** `src/templates/trends/_content.html`（内联 script 已包含 destroy → recreate 逻辑）

`_content.html` 中的 script 在初始化前先调用 `destroyChart(id)` 清除旧实例。HTMX 替换 `#trends-content` 后，script 自动重新执行，创建新实例。

---

### Task 8: 编写测试（17+ 个）

**文件:** `tests/test_trends.py`

```text
# ViewModel
test_build_trends_vm_no_data → dates=[], has_data=False
test_build_trends_vm_with_snapshots → series 含 10 KPI
test_build_trends_vm_filters_completed_analysis_only
test_build_trends_vm_includes_events

# 归因
test_attribution_uses_published_at_not_created_at
test_attribution_pre_post_split_with_absorption_lag
test_attribution_insufficient_pre_samples → label_key = insufficient_sample
test_attribution_insufficient_post_samples
test_attribution_meaningful_change_detected → label_key = possible_action_effect
test_attribution_small_change_no_effect → label_key = no_obvious_effect
test_attribution_confounded → label_key = confounded
test_attribution_negative_effect → label_key = negative_effect_possible

# KPI
test_get_kpi_value_basic_orm_field → sov
test_get_kpi_value_extended_from_details → scenario_recall
test_get_kpi_threshold_returns_per_kpi_default
test_get_kpi_threshold_unknown_returns_default
test_infer_target_kpi_from_expected_kpi_impact
test_infer_target_kpi_issue_type_fallback

# 页面
test_trends_page_renders_shell
test_trends_fragment_returns_content_only_no_layout
test_trends_fragment_uses_range_param
test_trends_fragment_rejects_invalid_range
```

---

## 五、验证标准

- [ ] 趋势页在有 >=2 次已完成的采集时展示 10 KPI 折线图
- [ ] 时间范围切换（周/月/季）只刷新 `#trends-content`，不整页跳转
- [ ] Chart.js 实例在 HTMX 切换后正确销毁和重建
- [ ] 事件标记（GT/Prompt/Content）正确渲染
- [ ] 归因表使用 `published_at` 而非 `created_at`
- [ ] 归因窗口含吸收期（默认 7 天）
- [ ] 归因标签结构化：label_key + confidence + reason
- [ ] 样本不足时返回 insufficient_sample
- [ ] 混淆因素检测：GT 变更/Prompt 变更/平台失败
- [ ] 无数据时展示空状态
- [ ] 整合已有 112 tests 继续通过
- [ ] 新增 >=17 个测试
