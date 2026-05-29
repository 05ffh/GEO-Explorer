# Phase 12: Dashboard 运营工作台 设计规范

**日期:** 2026-05-29 | **状态:** Define | **审阅:** P0-6 专家补齐清单

---

## 一、概述

将 GEO Explorer 从"API 可调用"升级为"运营工作台可日常使用"。实现专家评审清单 P0-6 全部 7 个页面的前端。

### 设计系统

| 要素 | 选择 |
|------|------|
| 风格 | Data-Dense Dashboard — 多图表、KPI 卡片、数据表、紧凑布局 |
| 主色 | #1E40AF (Navy Blue) |
| 辅色 | #3B82F6 (Blue) |
| 强调 | #F59E0B (Amber) |
| 背景 | #F8FAFC (Slate-50) |
| 文字 | #1E3A8A (Blue-900) |
| 标题字体 | Fira Code |
| 正文字体 | Fira Sans |
| 图表库 | Chart.js |
| 图标 | Heroicons (SVG) |

### 技术方案

当前项目使用 Jinja2 + HTMX。有两种方案：

**方案 A: 纯 Jinja2 + HTMX + Tailwind CDN (推荐)**
- 添加 Tailwind CSS CDN 到 base 模板
- 每个页面一个 Jinja2 模板
- HTMX 处理局部刷新、Tab 切换、分页
- 零构建步骤，与现有架构一致
- 缺点：无 CSS  tree-shaking，CDN 依赖

**方案 B: npm + Tailwind CLI + 静态构建**
- 需要 Node.js 构建步骤
- CSS 文件更小
- 缺点：增加构建复杂度

**选择方案 A** — 与现有 Jinja2 架构一致，快速交付，CDN 版本的 Tailwind 在生产环境中可缓存。

### 页面路由

```
GET /                          → 品牌总览 (Dashboard)
GET /brands/{id}               → 品牌详情 / KPI 总览
GET /brands/{id}/gt-review     → GT 审核页
GET /brands/{id}/evidence      → AI 回答证据页
GET /brands/{id}/hallucinations → 幻觉风险页
GET /brands/{id}/actions        → Action 工作台
GET /brands/{id}/content        → Content Package 管理
GET /brands/{id}/trends         → 趋势与归因
```

### 布局结构

```
┌──────────────────────────────────────────────┐
│  Logo  GEO Explorer    [品牌选择器]  [用户]   │  ← 固定顶栏
├──────────┬───────────────────────────────────┤
│ 导航      │                                   │
│          │                                   │
│ 📊 总览   │        <main>                     │
│ 📋 GT审核 │        页面内容                    │
│ 💬 AI证据 │        (HTMX 局部更新)            │
│ ⚠ 幻觉   │                                   │
│ ✅ Action │                                   │
│ 📦 Content│                                   │
│ 📈 趋势   │                                   │
│          │                                   │
├──────────┴───────────────────────────────────┤
│  GEO Explorer Phase 10  |  {brand} 诊断      │  ← 状态栏
└──────────────────────────────────────────────┘
```

---

## 二、7 个页面详细设计

### 页面 1: 品牌总览 (Dashboard)

**路由:** `/`  
**HTMX:** 品牌切换触发局部刷新

**内容区块（从上到下）:**

1. **AI 认知健康分** — 大数字 + 环形进度条
   - 综合分 = (SOV + Accuracy + Completeness) / 3 的加权
   - 颜色: <50% red, 50-70% amber, >70% green

2. **10 KPI 卡片** — 2 行 × 5 列 Grid
   - 每张卡片: 指标名、得分(大号)、分子/分母(小号)、置信度标签、迷你趋势线
   - 点击展开 KPI 解释卡 (HTMX 加载详情)

3. **采集状态概览** — 3 个状态卡片
   - 采集成功率、数据可信度、GT 覆盖率

4. **本轮最大风险** — 红色高亮卡片
   - P0 幻觉数、最严重 Action Theme

5. **最优先行动** — Amber 卡片
   - 1-3 个 Action Theme 快速入口

### 页面 2: GT 审核页

**路由:** `/brands/{id}/gt-review`  
**HTMX:** 字段级审核、接受/编辑/删除

**内容:**
- 左侧: 字段列表 (树形，按风险等级分组)
- 右侧: 字段详情面板
  - 候选值 (AI 提取)
  - 置信度 + 来源等级标签
  - 证据来源列表 (可展开看 URL)
  - 冲突来源 (红色标注)
  - 操作: [接受] [编辑] [删除] [标记不确定]
- 底部: [Promote 为正式 GT] 按钮 (校验通过后可用)

### 页面 3: AI 回答证据页

**路由:** `/brands/{id}/evidence`  
**HTMX:** 分页、平台筛选

**内容:**
- 筛选栏: 平台 | 问题维度 | 是否提及品牌
- 列表/表格: 每个 AI 回答一行
  - 平台图标 + 问题 + 回答片段(可展开)
  - 品牌是否被提及 ✓/✗
  - 错误声明标签 (P0/P1/P2)
  - 引用来源
- 点击行展开完整回答 + GT 字段对比

### 页面 4: 幻觉风险页

**路由:** `/brands/{id}/hallucinations`  
**HTMX:** 筛选、分页、详情展开

**内容:**
- 顶部汇总: P0/P1/P2 计数 + 按错误类型分布柱状图
- Issue Cluster 卡片 (聚合视图，默认):
  - 主题名、涉及字段、AI 原句摘录、GT 正确值
  - [确认] [忽略] 按钮
- 详细列表视图 (可切换)
- 筛选: 严重度 | 字段 | 平台

### 页面 5: Action 工作台

**路由:** `/brands/{id}/actions`  
**HTMX:** 状态流转、拖拽(?先不做)

**内容:**
- Kanban 风格列:
  - 待确认 | 生成中 | 待审核 | 可发布 | 已发布 | 已验证
- 每张卡片: Action Theme 标题、优先级标签、字段标签、创建时间
- 点击进入详情: AI 原句、GT 值、建议内容类型
- [确认] [生成内容] [标记已发布] 按钮

### 页面 6: Content Package 管理

**路由:** `/brands/{id}/content`  
**HTMX:** 预览、下载、状态变更

**内容:**
- 列表: 内容主题、类型、风险等级标签、状态标签、更新时间
- 点击展开预览面板:
  - 渲染后的 Markdown 内容
  - Schema.org JSON-LD (代码块)
  - 发布检查清单 (checkbox)
  - 事实检查报告
- 操作: [审核通过] [导出 MD] [导出 JSON] [标记已发布]

### 页面 7: 趋势与归因

**路由:** `/brands/{id}/trends`  
**HTMX:** 时间范围切换

**内容:**
- 时间范围选择器: 周/月/季
- 10 KPI 趋势线图 (Chart.js)
- 平台对比雷达图
- Action 发布时间标记线 (虚线 + 标签)
- 底部表格: 指标变化汇总

---

## 三、文件规划

```
新增:
  src/templates/base.html              ← 基础布局（导航+侧栏+顶栏）
  src/templates/dashboard/index.html   ← 重写: 品牌总览
  src/templates/dashboard/kpi-card.html  ← KPI 卡片组件
  src/templates/brands/detail.html     ← 品牌详情
  src/templates/brands/gt_review.html  ← GT 审核
  src/templates/brands/evidence.html   ← AI 证据
  src/templates/brands/hallucinations.html ← 幻觉风险
  src/templates/brands/actions.html    ← Action 工作台
  src/templates/brands/content.html    ← Content 管理
  src/templates/brands/trends.html     ← 趋势归因
  src/static/css/app.css               ← 全局样式覆盖

修改:
  src/main.py                          ← 添加新路由
  src/api/dashboard.py                  ← KPI Cards API 增强
  src/api/brands.py                     ← GT/证据/Action API 增强
```

---

## 四、验证标准

- [ ] 7 个页面均可正常渲染
- [ ] 品牌选择器可切换，HTMX 局部刷新
- [ ] KPI 卡片展示 10 个指标含分子分母
- [ ] GT 审核页可逐字段审核
- [ ] 幻觉风险页 P0/P1/P2 正确聚合
- [ ] Action 工作台状态流转正确
- [ ] Content 管理页可预览和下载
- [ ] 响应式: 375px / 768px / 1024px / 1440px
- [ ] 所有现有 89 tests 继续通过
- [ ] 无 emoji 图标 (Heroicons SVG)
