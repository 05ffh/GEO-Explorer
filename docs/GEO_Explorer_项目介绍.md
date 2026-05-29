# GEO Explorer — 品牌 AI 认知资产管理平台

> **项目介绍文档 v2 | 生成时间: 2026-05-30 | 版本: Phase 12**

---

## 一、项目概述

### 1.1 这是什么

GEO Explorer 是一套**品牌 AI 可见度监测与优化平台**，对标 [GEOAhead](https://geoahead.com/)。它向多个 AI 平台（DeepSeek、Kimi、豆包等）系统性地发起品牌相关的查询，监测 AI 如何描述你的品牌，检测与事实不符的"幻觉"，自动生成纠正内容，最终提升品牌在 AI 中的认知准确度。

**一句话：让你的品牌在 AI 眼中是正确、完整、有竞争力的。**

### 1.2 解决的问题

- **问题 1：你不知道 AI 怎么说你的品牌** — 用户问 AI"最好的咖啡品牌有哪些"，星巴克被提到了吗？描述对吗？
- **问题 2：AI 的"幻觉"没人管** — AI 可能说星巴克是"便宜的便利店咖啡"，这是事实错误，会影响潜在客户决策
- **问题 3：发现了问题不知道怎么修** — 传统 SEO 工具不管 AI 平台，GEO 需要新的方法论
- **问题 4：修复后没有持续监测** — 发布了纠正内容，AI 学到了吗？需要闭环验证

### 1.3 核心指标（10 KPI）

| KPI | 中文名 | 说明 |
|-----|--------|------|
| SOV | 声量份额 | 品牌在 AI 回复中被提及的频率 |
| First Recommendation Rate | 首次推荐率 | 非品牌场景问题中优先推荐的比率 |
| Accuracy | 准确率 | AI 对品牌描述与 GT（事实）的一致性 |
| Completeness | 完备性 | GT 关键字段在 AI 回复中的覆盖率 |
| Citation Rate | 引用率 | AI 回复中引用官方来源的比率 |
| Scenario Recall | 场景联想率 | 非品牌场景词下品牌被提及的比例 |
| Semantic Stability | 语义锚点稳定度 | 不同平台对品牌描述的一致性 |
| Differentiation | 差异化程度 | AI 表述中品牌独特卖点的出现率 |
| Cross-Platform Consistency | 跨平台一致性 | 品牌关键声明的跨平台稳定性 |
| Recommendation Quality | 推荐理由质量 | AI 推荐理由的实质性和准确度 |

每个 KPI 均包含：分子(numerator)、分母(denominator)、置信度(confidence)、指标解释卡。

---

## 二、系统架构

### 2.1 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 语言 | Python 3.12 | 全异步 (async/await) |
| Web 框架 | FastAPI | REST API + Jinja2 服务端渲染 + HTMX 局部刷新 |
| ORM | SQLAlchemy 2.0 async | 异步查询 + Alembic 迁移 |
| 数据库 | PostgreSQL 16 | 主存储，JSONB 支持 |
| 任务队列 | Celery + Redis 7 | 异步采集任务调度 |
| 前端 | Jinja2 + HTMX 2.0 + Tailwind CDN + Chart.js 4.4 | Data-Dense Dashboard 风格 |
| 设计系统 | #1E40AF / #3B82F6 / #F59E0B | Fira Code + Fira Sans + Heroicons SVG |
| AI 平台 | DeepSeek / Kimi / 豆包 | OpenAI-compatible API |
| 搜索 | DuckDuckGo + Google Custom Search (预留) | 免费搜索 + 备用 |
| PDF 生成 | Puppeteer + marked | Chrome 渲染中文 PDF |
| Word 生成 | python-docx | 可编辑企业文档 |
| 部署 | Systemd 守护进程 | Redis + Celery + API 三服务开机自启 |

### 2.2 项目结构

```
explore geo/                              # 项目根目录
├── src/
│   ├── models/         (22 文件)          # ORM 数据模型
│   ├── adapters/       (5 文件)           # AI 平台适配器
│   ├── collector/      (3 文件)           # 采集引擎 + GT 自动采集
│   ├── analyzer/       (17 文件)          # 10 KPI + 幻觉检测 + 聚合
│   ├── actions/        (6 文件)           # Action 引擎 + Content Package
│   ├── api/            (9 文件)           # REST API 端点
│   ├── search/         (3 文件)           # DuckDuckGo + AI 搜索层
│   ├── reports/        (4 文件)           # 报告生成 + PDF/DOCX 导出
│   ├── schemas/        (2 文件)           # GT 字段定义 + 来源等级体系
│   ├── view_models/    (8 文件)  ←新     # Dashboard ViewModel 层（模板只渲染不计算）
│   └── templates/      (21 文件) ←新     # Jinja2 页面 + 组件 + 布局
│       ├── base.html                       # 全局布局 (Tailwind CDN + Heroicons)
│       ├── dashboard/                      # 品牌总览页
│       ├── gt_review/                      # GT 审核页
│       ├── evidence/                       # AI 证据页
│       ├── hallucinations/                 # 幻觉风险页
│       ├── actions/                        # Action 工作台
│       ├── content/                        # Content 管理页
│       ├── trends/                         # 趋势归因页
│       ├── auth/                           # 登录页
│       └── partials/components/            # 10 个可复用 UI 组件
├── tests/              (15 文件)           # 112 个测试
├── deploy/             (3 文件)            # systemd 服务文件
├── docs/superpowers/                       # 设计规范 + 实现计划
├── reports/                               # 品牌诊断报告输出
└── alembic/                               # 数据库迁移（10+ 版本）
```

**代码统计：92 个 Python 文件，21 个模板文件，112 个测试（0 失败），70+ 次 git 提交。**

### 2.3 数据模型（22 张表 + 1 张新增）

```
organizations ──┐
users ──────────┤
                ├── brands ─────────────┬── ground_truth_versions
                │                       ├── collection_runs ── query_results
                │                       ├── metrics_snapshots
                │                       ├── hallucination_results
                │                       ├── action_plans ── content_packages
                │                       │               └─ action_themes ← Phase 11 新增
                │                       ├── gt_candidates ── gt_evidences
                │                       │                └─ gt_reviews
                │                       ├── competitor_sets
                │                       └── insight_summaries
                ├── query_templates
                ├── prompt_versions
                ├── api_usage_logs
                └── content_library
```

**Phase 11 新增：** ActionTheme 模型（9 状态生命周期）、GT Evidence 扩展（source_tier S/A/B/C/D、human_confirmed、review_status）。

**Phase 12 新增：** HallucinationResult.error_type、QueryResult.dimension/brand_mentioned、ContentPackage.title。

---

## 三、打造过程 — 12 个 Phase 的演进

### Phase 1-2: 基础设施（8 commits）

FastAPI + PostgreSQL + Docker 基础设施，14 个 ORM 数据模型。多租户架构（Organization → Brand → 业务数据），ActionPlan 状态机。

### Phase 3-4: 种子数据 + AI 适配器（2 commits）

22 个查询模板覆盖 5 个维度（品牌认知、竞品对比、场景推荐等），GT 字段 P0-P2 三级分级体系。5 个 AI 平台适配器统一 OpenAI-compatible 接口。

### Phase 5-6: 采集引擎 + 分析引擎（2 commits）

异步采集引擎 with 平台级 Semaphore 限流、429 退避重试。5 个核心 KPI 计算器 + 幻觉检测器。

### Phase 7-8: Action 引擎 + API + Dashboard（2 commits）

ActionPlan 状态机 + Content Brief 工厂（6 类模板）。JWT 认证、CRUD API、Jinja2 Dashboard with Chart.js。

### Phase 9: 采集→分析自动衔接（11 commits, 62 tests）

CollectionRun 双字段状态机，采集完成自动触发分析，Celery 异步化。首次真实采集：星巴克 69/69 成功，SOV 65.2%。

### Phase 10: GT 自动采集 + Action 执行 + KPI 升级（89 tests）

- GT 三层模型：Candidate → Evidence → Review → Promote → Active GT
- GT 自动采集：3 AI 平台 × 10 问 + DuckDuckGo，字段级置信度 + 冲突检测
- KPI 从 5→10：新增 Scenario Recall / Semantic Stability / Differentiation / Cross-Platform Consistency / Recommendation Quality
- Action Plans 自动生成 + Content Package 管线
- 报告交付系统：统一文件夹，3 格式（.md/.docx/.pdf）
- Systemd 守护：geo-redis / geo-celery / geo-api 开机自启

### Phase 11: 可信度加固（6 commits, 89 tests）

对齐专家评审 P0-1~P0-5，7 个阶段：

- **Stage 1 — 数据模型：** GT Evidence 新增 source_tier (S/A/B/C/D)、human_confirmed、review_status。ActionTheme 模型（9 状态生命周期）。ContentPackage 扩展（risk_level、fact_source_map、publish_url、verified_at、CONTENT_PACKAGE_TRANSITIONS 状态机）
- **Stage 2 — GT 可信度体系：** SOURCE_TIERS 含分数和示例，FIELD_EVIDENCE_REQUIREMENTS 字段级最低证据要求，HIGH_RISK_FIELD_TIER_REQUIREMENTS S 级强制要求，分层置信度计算（S≠A），字段类型感知冲突检测（域名归一化/identity/classification/factual 冲突类型）
- **Stage 3 — KPI 可解释：** 10 KPI 统一返回 numerator/denominator/confidence，_build_kpi_cards() 生成标准化解释卡
- **Stage 4 — 语义幻觉检测：** 9 种错误类型（identity/category/positioning/feature/competitor_confusion/unsupported/outdated/overclaim/negative），ClaimVerification（verdict/error_type/similarity_score/needs_human_review）
- **Stage 5 — Action Theme 聚合：** 按 (field, severity) 聚类，最多 10 主题，含 title/platforms/typical AI claims/KPI impact
- **Stage 6 — Content 治理：** 自动风险分级（low/medium/high → needs_review/fact_checked），状态机驱动

### Phase 12: Dashboard 运营工作台（7 commits, 112 tests）★ 当前

7 页面运营工作台，经过产品体验架构负责人 + 前端架构评审专家 + 可信运营工作台交付审查人三轮审阅：

- **品牌总览页：** AI 认知健康分（环形图）+ 10 KPI 卡片（含分子/分母/置信度/趋势）+ 数据可信度面板 + 阻塞事项提醒 + 最大风险 + 最优先行动
- **GT 审核页：** 审核进度条 + 字段列表（含风险等级/状态/来源等级标签）+ 筛选（冲突/高风险/未审核）+ 证据来源展开面板 + 批量操作 + Promote 阻断原因
- **AI 证据页：** 平台/维度/提及筛选 + AI 回答卡片（KPI/幻觉/Action 串联）+ 引用 URL + GT 对比表
- **幻觉风险页：** Cluster 视图 / 详细列表切换 + 按 (error_type, severity, field_name, dimension) 聚类 + 人工复核（确认/误判/GT错误/低风险偏差）
- **Action 工作台：** Kanban 看板（9 列状态）+ 优先级卡片 + 状态流转按钮（带角色级 TRANSITION_GUARDS 权限校验）
- **Content 管理页：** 风险等级标签 + 事实来源映射（句子→GT字段→URL→Source Tier→人工确认）+ 发布检查清单 + 审核流程
- **趋势归因页：** Chart.js 折线图 + 事件标记 + Action 效果验证表 + 归因标签（6 种结果判断）

**技术亮点：**
- ViewModel 层：所有计算在后端完成，模板只负责渲染（0 业务逻辑在 Jinja2）
- 11 个可复用 UI 组件（badges / states / KPI card / banners）
- Tailwind CDN（NO @apply）+ Heroicons SVG + Fira Code/Fira Sans
- HTMX 局部刷新 + Chart.js 生命周期管理
- Cookie + JWT 双通道认证（页面路由用 Cookie，HTMX 请求用 Header）
- Starlette 1.1+ 兼容

---

## 四、完整业务链路

```
 ┌──────────────────────────────────────────────────────────────────────────┐
│                     GEO Explorer 完整链路 (Phase 12)                       │
└──────────────────────────────────────────────────────────────────────────┘

 ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐
 │ 1. GT 采集    │    │ 2. GT 审核    │    │ 3. Brand 采集     │
 │              │    │              │    │                  │
 │ S/A/B/C/D    │ -> │ 字段级确认    │ -> │ 22 模板 x 3 平台 │
 │ 来源等级     │    │ Promote>Active│    │ = 66 次 AI 调用  │
 │ 证据持久化   │    │ 阻断原因提示  │    │ 异步 Celery      │
 └──────────────┘    └──────────────┘    └──────┬───────────┘
                                                ↓
 ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐
 │ 6. 报告交付   │    │ 5. Content   │    │ 4. 分析引擎       │
 │              │    │    Package   │    │                  │
 │ .md + .docx  │ <- │              │ <- │ 10 KPI 计算      │
 │ + .pdf       │    │ 风险分级     │    │ 9 类幻觉检测      │
 │ + Schema JSON│    │ 事实来源映射  │    │ P0/P1/P2 分级    │
 │              │    │ 发布检查清单  │    │ Action Theme 聚合 │
 └──────────────┘    └──────────────┘    └──────────────────┘
```

### 各环节详解

**第 1 步 — GT 采集（Ground Truth Auto-Collection）**

用户输入品牌名称 → 系统向 DeepSeek/Kimi/豆包 各发送 10 个预设问题 → DuckDuckGo 搜索 → 字段级证据聚合（每条证据标记 S/A/B/C/D 来源等级）→ 冲突检测（域名归一化/identity/classification/factual）→ 分层置信度计算 → 生成 GroundTruthCandidate + 持久化 Evidence 到 gt_evidences 表

**第 2 步 — GT 审核**

字段级审核面板（候选值 + 置信度 + 来源等级标签 + 证据列表）→ 逐字段确认（接受/编辑/删除/标记不确定）→ 高风险字段强制 S/A 级证据 → 冲突高亮 → Promote 条件检查（阻断原因列表）→ Promote 为 active GroundTruthVersion

**第 3 步 — Brand GEO 采集**

22 个标准查询模板 x 3 个 AI 平台 = 66 次异步 AI 调用（Celery worker 执行，202 + task_id 返回）

**第 4 步 — 分析引擎**

- **10 KPI 计算：** 每个 KPI 返回 numerator + denominator + confidence + 解释卡
- **语义幻觉检测：** 声明抽取 → 字段归类 → 9 种错误类型判定 → needs_human_review 标记
- **Action Theme 聚合：** 按 (field, severity) 聚类 → 最多 10 主题 → 含 KPI 影响预估

**第 5 步 — Content Package 生成**

Action Theme → LLM 生成完整内容 → FactCheck（GT 字段验证 + 禁止声明检查）→ 风险分级（low/medium/high）→ Schema.org JSON-LD → 发布检查清单

**第 6 步 — 报告交付 + 效果验证**

统一文件夹：诊断报告.md + 优化方案.md/.docx/.pdf + Content Pieces + Schema JSON-LD

---

## 五、前端运营工作台

Phase 12 构建了完整的 7 页面 B2B 运营工作台：

### 页面索引

| 页面 | 路由 | 功能 |
|------|------|------|
| 品牌总览 | `/brands/{id}` | AI 健康分 + 10 KPI 卡片 + 阻塞事项 + 风险/行动摘要 |
| GT 审核 | `/brands/{id}/gt-review` | 字段级审核 + 证据追溯 + Promote 阻断提示 |
| AI 证据 | `/brands/{id}/evidence` | AI 回答 + KPI/幻觉/Action 串联 + 筛选 |
| 幻觉风险 | `/brands/{id}/hallucinations` | Cluster 聚合 + 人工复核 + 误判纠正 |
| Action 工作台 | `/brands/{id}/actions` | Kanban 看板 + 9 状态流转 + 权限管控 |
| Content 管理 | `/brands/{id}/content` | 风险分级 + 事实映射 + 审核发布 |
| 趋势归因 | `/brands/{id}/trends` | 趋势图 + 事件标记 + 效果验证 + 归因 |

### 设计系统

- 风格：Data-Dense Dashboard
- 主色 #1E40AF / 辅色 #3B82F6 / 强调 #F59E0B
- 字体：Fira Code (标题) + Fira Sans (正文)
- 图标：Heroicons SVG 24x24
- 图表：Chart.js 4.4
- 技术：Jinja2 + HTMX 2.0 + Tailwind CDN
- 认证：JWT Cookie + Bearer Header 双通道
- 响应式：375px / 768px / 1024px / 1440px 四断点

### 6 类用户角色

| 角色 | 权限边界 |
|------|----------|
| Owner/Admin | 全部（管理品牌、成员、权限、API、额度） |
| Analyst | 读全部数据 + 触发采集 + 确认幻觉 + 验证效果 |
| GT Reviewer | 审核 GT 候选字段 + Promote |
| Content Editor | 生成/编辑/导出 Content Package |
| Legal Reviewer | 审核高风险内容 + 竞品对比 |
| Viewer | 只读 Dashboard 和报告 |

### 8 种全局状态处理

每个页面统一处理：loading（骨架屏）、empty（引导提示 + CTA）、error（错误 + 重试）、permission_denied（锁图标）、partial_data（黄色警告条）、stale_data（刷新提示）、success（正常展示）

---

## 六、关键设计决策

### 6.1 为什么是 GT 三层审核模型

```
GroundTruthCandidate (候选) → GroundTruthReview (审核记录) → Active GroundTruthVersion
     ↑                               ↑                              ↑
  AI 自动采集                    人工字段级确认                 用于 KPI 计算
```

- AI 采集结果不能直接用于 KPI 计算 — 可能包含错误、冲突、不准确信息
- 必须经过人工字段级审核 + S/A/B/C/D 来源等级验证
- 高风险字段（official_name/category/positioning/pricing 等）强制需要 S/A 级证据 + 人工确认
- Promote 后旧版本自动标记为 superseded，支持版本追溯

### 6.2 为什么需要来源等级体系 (S/A/B/C/D)

| 等级 | 来源 | 权重 | 能否直接进入 GT |
|------|------|------|----------------|
| S | 官网、官方文档、政府/工商/交易所 | 1.0 | 可直接使用 |
| A | 权威媒体、行业数据库、专业评测 | 0.7 | 需人工确认 |
| B | 搜索引擎摘要、百科、聚合页 | 0.4 | 只能作为线索 |
| C | AI 平台回答 | 0.2 | 只能作为候选 |
| D | 论坛、自媒体、未知站点 | 0.0 | 不进入 GT |

### 6.3 为什么 ViewModel 层

```
ORM Models → ViewModels → Templates
  (数据)      (预计算)     (纯渲染)
```

- 所有数字格式化、状态判断、权限计算在 ViewModel 中完成
- Jinja2 模板 0 业务逻辑 — 只负责循环和条件渲染
- 好处：模板稳定、可测试、ORM 变更不影响前端、模板不会因复杂表达式出错

### 6.4 为什么不自动发布

Content Package 生成的内容经过事实检查（GT 字段验证 + 禁止声明检查），但最终发布决策必须由人类做出：
- 内容可能包含品牌敏感的表述
- 发布目标（官网/CMS/第三方平台）需要人工选择
- Schema.org 结构化数据需要 SEO 验证
- 所有内容默认经过 risk_level 分级（low→普通审核 / medium→品牌审核 / high→法务审核）

### 6.5 异步任务架构

品牌采集（66 次 AI 调用）和 GT 采集（30 次 AI 调用）都在 Celery worker 中异步执行。API 立即返回 202 + task_id，避免 HTTP 超时。这是从 Phase 9 实际教训中总结的——同步执行时 30 个 AI 调用需要 17 分钟，HTTP 直接超时。

---

## 七、当前状态与成熟落地补齐清单

### 7.1 已完成 — P0 全部对齐

| P0 项目 | 完成内容 |
|---------|---------|
| P0-1 可信事实工程体系 | SOURCE_TIERS (S/A/B/C/D)、FIELD_EVIDENCE_REQUIREMENTS、HIGH_RISK_FIELD_TIER_REQUIREMENTS、GT Evidence 证据表、冲突检测、GT Review 审核界面 |
| P0-2 KPI 可解释体系 | 10 KPI 每个返回 numerator/denominator/confidence、_build_kpi_cards() 生成解释卡、Dashboard 展示 |
| P0-3 语义级幻觉检测 | 9 种错误类型、ClaimVerification (verdict/error_type/similarity_score/needs_human_review)、Hallucination 风险页 |
| P0-4 Action 聚合与优先级 | _cluster_action_themes() 聚合最多 10 主题、Action 工作台 Kanban 看板 |
| P0-5 Content 内容治理 | risk_level (low/medium/high)、CONTENT_PACKAGE_TRANSITIONS 状态机、事实来源映射、Content 管理页 |
| P0-6 Dashboard 工作台 | 7 页面全部可渲染，112 tests 0 failures，6 角色体系 + 8 状态覆盖 |

### 7.2 部分完成 — P1

| P1 项目 | 当前完成度 | 还需做什么 |
|---------|-----------|-----------|
| P1-1 Action 效果归因 | 60% — compute_attribution_label() 6 种归因结果已实现 | 趋势页需要接入真实归因数据，而非占位 UI；发布前后 KPI 自动对比 |
| P1-3 权限与审核流 | 50% — TRANSITION_GUARDS 角色映射已实现，页面按钮按权限渲染 | 需要审计日志表 + 所有 POST 操作写日志；RBAC 中间件 |
| P1-2 行业模板体系 | 0% | 金融/餐饮/SaaS/新能源 4 行业的问题模板、GT 字段扩展、KPI 权重、风险词库 |
| P1-4 成本与调用监控 | 0% | api_usage_logs 模型已存在，需 Dashboard 展示 API 调用量/Token/费用 |
| P1-5 队列稳定性 | 0% | Celery 死信队列、重试策略、任务幂等、进度展示、失败隔离 |
| P1-6 客户版报告语言 | 0% | 技术指标→客户语言翻译层、高管摘要版/执行版报告模板 |

### 7.3 未开始 — P2

| P2 项目 | 说明 |
|---------|------|
| P2-1 Benchmark 与竞品归因 | 行业基准、竞品 KPI 对比、品牌差距归因 |
| P2-2 长期趋势与稳定性分析 | 周/月/季趋势、断崖式下降识别、模型更新影响识别 |
| P2-3 自动化报告产品化 | 客户版/内部版/高管摘要版 PDF 模板、可配置品牌视觉 |
| P2-4 CMS / 发布系统集成 | WordPress/Strapi 草稿创建、Webhook 推送、发布后 URL 回填 |
| P2-5 多品牌 / 多租户 SaaS | 组织隔离、套餐权限、成员管理、账单系统、数据删除机制 |

### 7.4 推荐下一阶段路线图

```
阶段 1 (当前): 可信度加固 ✅ 已完成
  └─ GT 证据等级 + KPI 解释卡 + 语义幻觉 + Action Theme + Content 治理

阶段 2 (当前): 运营工作台化 ✅ 已完成
  └─ 7 页面 + ViewModel 层 + 组件系统 + 认证 + 权限

阶段 3 (下一步): 前后端紧密集成 + P1 补齐
  └─ 趋势归因真实数据 + 审计日志 + 行业模板 + 成本监控 + 队列治理

阶段 4: 效果验证与行业化
  └─ 竞品 Benchmark + 长期趋势 + 报告产品化

阶段 5: 商业化与 SaaS 化
  └─ CMS 集成 + 多租户套餐 + 客户版报告
```

---

## 八、核心数字

| 指标 | 数值 |
|------|------|
| Python 源文件 | 92 个 |
| Jinja2 模板文件 | 21 个 |
| ORM 数据模型 | 22 张表 |
| ViewModel | 8 个 |
| UI 组件 | 11 个 |
| 页面 | 7 个 + 登录页 |
| API 端点 | 30+ 个 |
| KPI | 10 个 |
| 幻觉错误类型 | 9 种 |
| 来源等级 | 5 级 (S/A/B/C/D) |
| 用户角色 | 6 种 |
| 页面状态 | 8 种 |
| AI 平台适配器 | 5 个 (DeepSeek/Kimi/豆包 可用，文心待更新) |
| 测试 | 112 个，0 失败 |
| Git 提交 | 70+ 次 |
| 设计规范 | 7 份 |
| 实现计划 | 5 份 |
| 专家评审 | 4 轮 |

---

## 九、如何运行

### 环境要求

- Python 3.12 + venv
- PostgreSQL 16 (localhost:5432, geo/geo, geo_explorer)
- Redis 7 (localhost:6379)
- Node.js 22 (PDF 生成)

### 启动命令

```bash
# 数据库迁移
cd "/home/ffh/explore geo"
.venv/bin/python -m alembic upgrade head

# 启动服务（systemd 守护）
sudo systemctl start geo-redis geo-celery geo-api

# 或手动启动
redis-server --daemonize yes
.venv/bin/celery -A src.celery_app worker --loglevel=info --concurrency=4 &
.venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 &

# 浏览器访问
http://localhost:8000/login
# 点击一键登录 → 品牌总览 → 7 页面导航
```

### API 使用流程

```bash
# 1. 创建品牌
curl -X POST /api/brands -d '{"name":"星巴克","industry":"餐饮"}'

# 2. 触发 GT 自动采集（异步）
curl -X POST /api/brands/{id}/gt-collect  # 返回 202 + task_id

# 3. 审核 GT + Promote
curl -X POST /api/gt-candidates/{id}/review
curl -X POST /api/gt-candidates/{id}/promote

# 4. 触发 GEO 诊断采集（异步）
curl -X POST /api/brands/{id}/collections  # 返回 202 + task_id

# 5. 查看 Dashboard
curl /api/dashboard  # 10 KPI + GT 统计

# 6. 生成报告
curl -X POST /api/dashboard/brands/{id}/reports/generate
```

---

## 十、项目文件索引

| 文件/目录 | 说明 |
|-----------|------|
| `src/models/` | 22 个 ORM 数据模型 |
| `src/adapters/` | 5 个 AI 平台适配器 |
| `src/collector/engine.py` | 品牌采集引擎 |
| `src/collector/gt_collector.py` | GT 自动采集编排器 |
| `src/analyzer/pipeline.py` | 分析管线（KPI→幻觉→Action→Content→报告） |
| `src/analyzer/hallucination.py` | 语义幻觉检测器（9 错误类型） |
| `src/analyzer/gt_confidence.py` | 来源等级加权置信度计算 |
| `src/analyzer/gt_conflict_detector.py` | 字段类型感知冲突检测 |
| `src/actions/executor.py` | Content Package 生成器 |
| `src/actions/fact_checker.py` | 事实检查器（GT 验证 + 禁止声明） |
| `src/actions/schema_generator.py` | Schema.org JSON-LD 生成 |
| `src/reports/delivery.py` | 统一报告交付系统 |
| `src/schemas/ground_truth.py` | GT 字段 + 来源等级 + KPI 中文名 |
| `src/view_models/` | 8 个 ViewModel（Dashboard/GT Review/Evidence/...） |
| `src/templates/` | 21 个 Jinja2 模板（7 页面 + 11 组件 + 布局） |
| `src/api/dashboard.py` | Dashboard + 报告 API |
| `src/api/ground_truth.py` | GT 审核 API + Promote |
| `src/api/deps.py` | 认证依赖（JWT Cookie + Bearer 双通道） |
| `tests/` | 112 个测试 |
| `deploy/` | systemd 服务配置文件 |
| `docs/superpowers/specs/` | 设计规范 |
| `docs/superpowers/plans/` | 实现计划 |
| `reports/` | 品牌诊断报告输出 |

---

*GEO Explorer Phase 12 | 2026-05-30 | 70+ commits | 112 tests | 92 source files | 21 templates*
