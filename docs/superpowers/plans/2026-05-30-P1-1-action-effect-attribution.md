# P1-1 Action 效果归因 实现计划

**日期:** 2026-05-30 | **状态:** Plan | **依赖:** Phase 12 Dashboard

---

## 一、目标

让趋势归因页从占位 UI 变成可用的运营工具。回答 GEO 运营的核心问题：**发布优化内容后，AI 对品牌的认知是否改善了？**

---

## 二、当前状态

| 能力 | 状态 |
|------|------|
| `compute_attribution_label()` 6 种归因逻辑 | 已完成 |
| `build_trends_vm()` ViewModel | 骨架（只返回 brand 基本信息） |
| 趋势页模板 | 占位（空 Chart.js 容器 + 空状态） |
| `GET /api/brands/{id}/metrics/history` | 已有（可复用） |
| MetricsSnapshot 历史数据 | 数据库中已有 |

---

## 三、实现任务

### Task 1: 实现 trends ViewModel — 趋势数据查询

**文件:** `src/view_models/trends.py`

从 `MetricsSnapshot` 拉取历史快照，组装 Charts.js 需要的 `dates` + `series` 格式：

```python
async def build_trends_vm(brand, range_str, user, db) -> dict:
    limit = {"week": 12, "month": 24, "quarter": 8}[range_str]
    
    # 获取历史快照
    snapshots = await db.execute(
        select(MetricsSnapshot).where(
            MetricsSnapshot.brand_id == brand.id,
            MetricsSnapshot.platform.is_(None),
            MetricsSnapshot.dimension.is_(None),
        ).order_by(desc(MetricsSnapshot.week_start)).limit(limit)
    )
    snapshots = list(snapshots.scalars().all())
    snapshots.reverse()  # 时间升序
    
    dates = [s.week_start.isoformat()[:10] for s in snapshots]
    series = {kpi: [round(getattr(s, kpi, 0), 4) for s in snapshots] 
              for kpi in ["sov", "first_rec_rate", "accuracy_rate", "completeness_rate", "citation_rate"]}
    
    # 事件标记：GT 版本变更 + Content Package 发布
    events = await _build_events(brand.id, db)
    
    # 归因表
    attribution = await _build_attribution(brand.id, snapshots, db)
    
    return {
        "brand": {"id": str(brand.id), "name": brand.name},
        "dates": dates,
        "series": series,
        "events": events,
        "attribution": attribution,
        "range": range_str,
    }
```

**事件标记数据结构：**
```python
events = [
    {"type": "gt_update", "date": "2026-05-15", "label": "GT v3"},
    {"type": "content_published", "date": "2026-05-20", "label": "品牌定位纠偏"},
]
```

---

### Task 2: 实现 trends ViewModel — 归因表查询

**文件:** `src/view_models/trends.py`

为每个已发布的 ActionTheme 计算发布前后 KPI 对比：

```python
async def _build_attribution(brand_id, snapshots, db):
    # 查询已发布的 ActionTheme
    themes = await db.execute(
        select(ActionTheme).where(
            ActionTheme.brand_id == brand_id,
            ActionTheme.status.in_(["published_marked", "verification_pending", "verified"]),
        ).order_by(ActionTheme.updated_at.desc())
    )
    themes = themes.scalars().all()
    
    # 查询关联的 ContentPackage（获取发布时间）
    rows = []
    for theme in themes:
        pkg = await db.execute(
            select(ContentPackage).where(
                ContentPackage.action_theme_id == theme.id,
                ContentPackage.publish_url != "",
            ).order_by(desc(ContentPackage.created_at)).limit(1)
        )
        pkg = pkg.scalar_one_or_none()
        if not pkg or not pkg.created_at:
            continue
        
        publish_time = pkg.created_at
        
        # 分割发布前后 snapshots
        pre = [s for s in snapshots if s.week_start < publish_time.date()][-2:]
        post = [s for s in snapshots if s.week_start >= publish_time.date()][:2]
        
        if len(pre) < 1 or len(post) < 1:
            continue
        
        # 目标 KPI（从 expected_kpi_impact 读取）
        target_kpis = list(theme.expected_kpi_impact.keys()) if theme.expected_kpi_impact else ["accuracy_rate"]
        
        for kpi_key in target_kpis[:3]:  # 最多 3 个目标 KPI
            pre_vals = [getattr(s, kpi_key, 0) for s in pre]
            post_vals = [getattr(s, kpi_key, 0) for s in post]
            pre_avg = sum(pre_vals) / len(pre_vals)
            post_avg = sum(post_vals) / len(post_vals)
            change = post_avg - pre_avg
            
            # 混淆因素检测
            gt_changed = _gt_changed_during(brand_id, pre[-1].week_start, post[-1].week_start, db)
            platform_failure = any(s.failure_rate > 0.3 for s in post)
            
            label = compute_attribution_label(pre_avg, post_avg, len(pre) + len(post), gt_changed, platform_failure)
            
            rows.append({
                "theme_title": theme.title,
                "publish_date": publish_time.isoformat()[:10],
                "target_kpi": kpi_key,
                "kpi_label": KPI_DISPLAY_NAMES.get(kpi_key, kpi_key),
                "pre_avg": round(pre_avg, 4),
                "post_avg": round(post_avg, 4),
                "change": round(change, 4),
                "direction": "up" if change > 0 else "down",
                "attribution_label": label,
                "sample_size": len(pre) + len(post),
            })
    
    return rows
```

---

### Task 3: 改写趋势页模板 — Chart.js 折线图

**文件:** `src/templates/trends/index.html`

用真实数据渲染图表，替换占位 UI：

```html
{% extends "base.html" %}
{% block title %}{{ vm.brand.name }} — 趋势归因{% endblock %}
{% block content %}

<h1 class="font-heading text-2xl font-bold text-text mb-5">{{ vm.brand.name }} — 趋势与归因</h1>

<!-- 时间范围切换 -->
<div class="flex items-center gap-3 mb-4">
    <div class="flex bg-slate-100 rounded-lg p-0.5">
        {% for r in ['周', '月', '季'] %}
        {% set rk = {'周':'week','月':'month','季':'quarter'}[r] %}
        <button class="px-4 py-1.5 text-sm rounded-md cursor-pointer transition-colors duration-150
                       {% if vm.range == rk %}bg-white text-text shadow-sm{% else %}text-slate-600 hover:bg-slate-200{% endif %}"
                hx-get="/brands/{{ vm.brand.id }}/trends?range={{ rk }}"
                hx-target="#trends-content" hx-swap="innerHTML">{{ r }}</button>
        {% endfor %}
    </div>
</div>

<div id="trends-content">
{% if vm.dates %}
<!-- KPI 趋势图 -->
<div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
    <div class="bg-white rounded-xl p-5 shadow-sm border border-gray-100 chart-container">
        <h3 class="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3">核心 KPI 趋势</h3>
        <canvas id="trend-chart-sov"></canvas>
    </div>
    <div class="bg-white rounded-xl p-5 shadow-sm border border-gray-100 chart-container">
        <h3 class="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3">准确率 & 完整度</h3>
        <canvas id="trend-chart-acc"></canvas>
    </div>
</div>

<!-- 事件时间线 -->
{% if vm.events %}
<div class="bg-white rounded-xl p-5 shadow-sm border border-gray-100 mb-4">
    <h3 class="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3">关键事件</h3>
    <div class="flex flex-wrap gap-2">
        {% for ev in vm.events %}
        <span class="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs
                     {% if ev.type == 'gt_update' %}bg-blue-100 text-blue-700
                     {% else %}bg-green-100 text-green-700{% endif %}">
            {{ ev.date }} — {{ ev.label }}
        </span>
        {% endfor %}
    </div>
</div>
{% endif %}

<!-- Action 效果验证表 -->
{% if vm.attribution %}
<div class="bg-white rounded-xl p-5 shadow-sm border border-gray-100">
    <h3 class="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3">Action 效果验证</h3>
    <div class="overflow-x-auto">
        <table class="w-full text-sm">
            <thead>
                <tr class="border-b border-gray-200 text-left text-xs text-slate-500 uppercase">
                    <th class="py-2 pr-3">Action Theme</th>
                    <th class="py-2 pr-3">发布时间</th>
                    <th class="py-2 pr-3">目标 KPI</th>
                    <th class="py-2 pr-3">发布前</th>
                    <th class="py-2 pr-3">发布后</th>
                    <th class="py-2 pr-3">变化</th>
                    <th class="py-2 pr-3">归因</th>
                </tr>
            </thead>
            <tbody>
                {% for row in vm.attribution %}
                <tr class="border-b border-gray-100">
                    <td class="py-2 pr-3 font-medium text-text">{{ row.theme_title }}</td>
                    <td class="py-2 pr-3 text-slate-500">{{ row.publish_date }}</td>
                    <td class="py-2 pr-3">{{ row.kpi_label }}</td>
                    <td class="py-2 pr-3">{{ (row.pre_avg * 100)|round|int }}%</td>
                    <td class="py-2 pr-3">{{ (row.post_avg * 100)|round|int }}%</td>
                    <td class="py-2 pr-3 {% if row.direction == 'up' %}text-green-600{% else %}text-red-600{% endif %}">
                        {{ '+' if row.change > 0 else '' }}{{ (row.change * 100)|round(1) }}%</td>
                    <td class="py-2 pr-3">
                        <span class="badge {% if '可能由 Action' in row.attribution_label %}badge-success
                                          {% elif '无明显' in row.attribution_label %}badge-pending
                                          {% else %}badge-p1{% endif %}">{{ row.attribution_label }}</span>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</div>
{% else %}
{{ empty_state("暂无归因数据", "发布 Content 并完成复测后，Action 效果对比和归因分析将在此展示。", none, none) }}
{% endif %}

{% else %}
{{ empty_state("暂无趋势数据", "完成至少 2 次采集后，KPI 趋势图将在此展示。", none, none) }}
{% endif %}
</div>

{% endblock %}

{% block scripts %}
<script>
{% if vm.dates %}
(function() {
    var dates = {{ vm.dates | tojson }};
    var series = {{ vm.series | tojson }};
    var events = {{ vm.events | tojson }};
    
    function makeChart(id, kpis, title) {
        var ctx = document.getElementById(id);
        if (!ctx) return;
        var datasets = kpis.map(function(kpi, i) {
            var colors = ['#1E40AF', '#3B82F6', '#F59E0B', '#22c55e', '#ef4444'];
            return {
                label: kpi,
                data: series[kpi],
                borderColor: colors[i % 5],
                backgroundColor: colors[i % 5] + '20',
                tension: 0.3,
                fill: false,
                pointRadius: 3,
            };
        });
        window.geoCharts[id] = new Chart(ctx, {
            type: 'line',
            data: { labels: dates, datasets: datasets },
            options: {
                responsive: true,
                plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, padding: 15, font: { size: 11 } } } },
                scales: {
                    y: { beginAtZero: false, ticks: { callback: function(v) { return (v * 100).toFixed(0) + '%'; } } },
                    x: { ticks: { maxTicksLimit: 12, font: { size: 10 } } }
                },
                interaction: { intersect: false, mode: 'index' },
            }
        });
    }
    
    makeChart('trend-chart-sov', ['sov', 'citation_rate', 'first_rec_rate']);
    makeChart('trend-chart-acc', ['accuracy_rate', 'completeness_rate']);
})();
{% endif %}
</script>
{% endblock %}
```

---

### Task 4: 添加 HTMX 时间范围切换端点

**文件:** `src/main.py`（修改现有 `/brands/{brand_id}/trends` 路由）

现有路由已经接受 `range` 参数，只需要 ViewModel 生效即可。HTMX 时间范围按钮触发的请求会返回完整页面内容到 `#trends-content`。

如果希望只更新图表区域（性能更好），可新增 fragment 端点：

```python
@app.get("/brands/{brand_id}/trends-fragment", response_class=HTMLResponse)
async def trends_fragment(request: Request, brand_id: str, range: str = "month",
                          user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    """Return trends content fragment for HTMX swap."""
    brand = await get_org_brand_or_404(brand_id, user, db)
    from src.view_models.trends import build_trends_vm
    vm = await build_trends_vm(brand, range, user, db)
    return _render(request, "trends/_content.html", {"vm": vm})
```

---

### Task 5: 编写测试

**文件:** `tests/test_dashboard_viewmodels.py`（追加）

```python
class TestTrendsViewModel:
    async def test_build_trends_vm_no_data(self, db_session, test_brand, test_user):
        """No snapshots → empty series and dates."""
        vm = await build_trends_vm(test_brand, "month", test_user, db_session)
        assert vm["dates"] == []
        assert vm["series"]["sov"] == []

    async def test_build_trends_vm_with_snapshots(self, db_session, test_brand, test_user):
        """Snapshots present → series contains values."""
        # Create 3 snapshots
        ...

    async def test_attribution_pre_post_split(self, db_session, test_brand, test_user):
        """Published theme with snapshots before/after publish date → attribution row."""
        ...

    async def test_attribution_no_published_themes(self, db_session, test_brand, test_user):
        """No published themes → empty attribution list."""
        ...
```

---

## 四、验证标准

- [ ] 趋势页在有 >=2 次采集数据时展示折线图（Chart.js 正常渲染）
- [ ] 时间范围切换（周/月/季）可用，HTMX 局部刷新不整页跳转
- [ ] GT 版本变更和 Content 发布时间在图表旁以事件标签展示
- [ ] 已发布的 Action Theme 出现在效果验证表中，含发布前后对比和归因标签
- [ ] 无数据时展示空状态提示
- [ ] 现有 112 tests 继续通过
- [ ] 新增 >=8 个测试覆盖趋势 ViewModel 和归因逻辑
