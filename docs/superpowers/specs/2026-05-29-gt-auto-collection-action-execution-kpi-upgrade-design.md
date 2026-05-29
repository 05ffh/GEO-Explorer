# Design: GT 自动采集 + Action 内容执行准备 + KPI 体系升级 (Phase 10 v2)

**日期:** 2026-05-29
**状态:** Draft v2 — 审阅修正后
**审阅:** GEO 产品架构负责人 / AI 数据管线与内容自动化风控评审专家

---

## 概述

Phase 10 将 GEO Explorer 从「AI 可见度监测系统」升级为「品牌 AI 认知资产运营系统」：

1. **GT 自动采集** — 系统自动收集候选事实 → 字段级证据展示 → 用户逐字段审核 → 生成正式 GT
2. **KPI 体系升级** — 从 5 基础 KPI 升级为 10 KPI，每个 KPI 含计算口径、样本量、置信度
3. **Action 内容执行准备器** — 用户确认后生成 Content Package（Markdown + Schema JSON-LD + 发布清单），内容经事实检查，不自动发布

---

## Section 1: GT 自动采集器

### 1.1 核心原则

```
GT 自动采集结果 = GroundTruthCandidate（候选事实，不可直接用于 KPI 计算）
用户确认后的结果 = GroundTruthVersion（正式事实，方可参与 KPI 计算）
```

### 1.2 输入方式

渐进式消歧输入：

```
必填: 公司名
可选: 官网 URL / 行业 / 所在地区 / 产品名 / 一句话描述
    ↓
系统自动检测: 同名公司混淆 / 搜索结果行业分散 / AI 平台定位冲突
    ↓
若疑似混淆 → status = needs_disambiguation → 要求用户选择
```

### 1.3 完整数据流

```
用户输入公司名 + 可选消歧信息
    ↓
同名公司消歧检查
    ↓
┌─────────────────────────────────────────┐
│ 第一轮: AI 平台基础采集 (3 平台 × 10 问题) │
│ DeepSeek + Kimi + 豆包                    │
│ → 候选 GT 字段 + 平台间一致性初步评分       │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ 第二轮: 搜索源采集（多源可插拔）           │
│ DuckDuckGo (免费) → Brave Search (备选)   │
│ Google Custom Search (需 Key + cx)        │
│ → 搜索结果摘要 + 官方来源 URL 识别          │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ 第三轮: 官方来源抓取与验证                 │
│ 从搜索结果中识别官网 / 官方文档 / 工商页面  │
│ 抓取 About 页 / 产品页 / 联系页            │
│ → 官方来源信息提取                         │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ 第四轮: AI 平台搜索增强 (supports_web_search) │
│ DeepSeek/Kimi web search 再跑一轮          │
│ → 带实时引用和 URL 的增强信息               │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ 聚合引擎: 字段级候选事实抽取                │
│ 每字段独立: 值 / 来源列表 / 来源质量 / 冲突  │
│ → GroundTruthCandidate + GroundTruthEvidence│
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ 用户逐字段审核                             │
│ 每个字段: 接受 / 编辑 / 删除 / 标记不确定    │
│ 高风险字段强制人工确认                      │
│ → GroundTruthReview 记录审核过程            │
└─────────────────────────────────────────┘
    ↓
若必填字段完整 + 高风险字段已确认 + 用户确认
    ↓
生成 active GroundTruthVersion → 触发正式采集
若不完备 → status = needs_completion，不触发采集
```

### 1.4 GT 采集问题模板 (10 个)

| # | 问题 | 目标 GT 字段 |
|---|---|---|
| 1 | {公司} 是一家什么样的公司？请详细描述 | official_name, positioning, industry |
| 2 | {公司} 属于什么行业和什么具体品类？ | industry, category, subcategory |
| 3 | {公司} 的核心产品/服务有哪些？ | core_products, core_features |
| 4 | {公司} 的目标用户是谁？主要服务什么人群？ | target_users, best_fit_users |
| 5 | {公司} 主要解决哪些用户问题或业务场景？ | core_scenarios, scenario_keywords |
| 6 | {公司} 和主要竞品相比有什么不同？有什么特点？ | key_differentiators |
| 7 | {公司} 的主要竞品或替代方案有哪些？ | target_competitors, alternative_solutions |
| 8 | 关于{公司}，有哪些常见误解或不能错误描述的地方？ | forbidden_claims, common_misconceptions |
| 9 | {公司} 有哪些官方来源可以证明它的信息？ | source_of_truth_by_field, official_docs, official_channels |
| 10 | 在什么情况下应该选择{公司}？推荐它的正确理由是什么？ | preferred_recommendation_reasons, best_fit_users |

### 1.5 GT 模板扩展 (P0 优先 8 字段)

| 新字段 | 支撑能力 | 是否高风险 |
|---|---|---|
| `aliases` (增强) | SOV、场景联想率 | 否 |
| `category` | 品类判断、跨平台一致性 | **是** |
| `core_scenarios` | 场景联想率、推荐理由质量 | 否 |
| `scenario_keywords` | 场景联想率、语义锚点稳定度 | 否 |
| `target_competitors` | 竞品共现率、差异化识别率 | **是** |
| `preferred_recommendation_reasons` | 推荐理由质量、差异化识别率 | **是** |
| `forbidden_claims` (增强) | 负面幻觉率、合规风控 | **是** |
| `source_of_truth_by_field` | 官方引用率、证据追溯 | 否 |

高风险字段必须用户逐字段确认后才可进入 active GT。

### 1.6 搜索来源质量分级

| 来源类型 | 可信等级 | 用途 |
|---|---|---|
| 官网 / 官方文档 / 官方社媒 | High | 可作为正式候选事实 |
| 政府 / 监管 / 工商 / 交易所 | High | 可作为正式候选事实 |
| 权威媒体 / 行业数据库 | Medium | 可作为辅助证据 |
| 搜索摘要 / 聚合页 / 百科类页面 | Low | 只能作为线索，不得直接标记 high confidence |
| 论坛 / 自媒体 / 未知站点 | Very Low | 默认不进入 GT，只作线索 |

### 1.7 字段级置信度评分规则

每个字段独立评分：

```text
High:
  - 至少 1 个官方来源 (official_site / gov / regulatory) 支持
  - 且至少 2 个 AI / 搜索来源一致
  - 无明显冲突

Medium:
  - 多个平台 AI 一致 (>=2)
  - 或权威第三方来源支持
  - 但没有官方来源直接确认

Low:
  - 只有搜索摘要支持
  - 或只有单个平台 AI 提到
  - 或来源不明确

Uncertain:
  - 多源冲突
  - 同名公司疑似混淆
  - 涉及融资、客户、奖项、资质等敏感事实但无官方证据
  - 缺少来源
```

### 1.8 用户确认界面要求

每个字段展示:

```
字段名 | 候选值 | 置信度(High/Medium/Low/Uncertain) | 证据来源列表 | 来源摘录
冲突来源 (如有) | 推荐操作 | 操作: [接受] [编辑] [删除] [标记不确定]
```

高风险字段 (`official_name`, `category`, `positioning`, `target_competitors`, `forbidden_claims`, `proof_points`, `pricing`, `certifications`, `customers`, `awards`, `funding`, `legal_sensitive_claims`) 必须逐字段确认。

Uncertain 字段不得参与正式 KPI 计算，除非用户手动确认。

### 1.9 正式采集触发条件

```
GroundTruthVersion.status == "active"
AND required_fields_complete == true
AND user_confirmed == true
AND high_risk_fields_reviewed == true
```

最小必填字段:

```
official_name, aliases, industry, category, positioning,
core_products, target_users, core_scenarios, key_differentiators,
official_domains, source_of_truth_by_field
```

若不完备 → status = needs_completion，不触发正式采集。

### 1.10 搜索层设计

多源可插拔架构：

```python
class SearchBackend:
    name: str
    async def search(query: str, num: int = 5) -> list[SearchResult]
    # SearchResult: {title, snippet, url, source_quality}

class PlatformCapabilities:
    supports_web_search: bool
    supports_citations: bool
    citation_format: str
```

| 层级 | 搜索源 | 费用 | 状态 |
|---|---|---|---|
| L1 | DuckDuckGo | 免费，零 Key | 默认可用 |
| L2 | AI 平台 web search (DeepSeek/Kimi) | 已有 Key | 需检查 capabilities |
| L3 | Brave Search API | 免费 2000次/月 | 后续注册 |
| L4 | Google Custom Search | 需 Key + cx | 已配置 Key，cx 待验证 |

### 1.11 新增数据模型

```
GroundTruthCandidate
  id, organization_id, brand_id, collection_run_id
  candidate_json, confidence_summary
  status: pending_review | approved | rejected | edited
  created_at, reviewed_at, reviewer_id

GroundTruthEvidence
  id, candidate_id, field_name, value
  source_type: ai_platform | search_result | official_site | user_input
  source_name, source_url, excerpt, confidence, collected_at

GroundTruthReview
  id, candidate_id, reviewer_id
  action: approve | edit | reject
  field_changes_json, review_notes, reviewed_at
```

### 1.12 内部质量指标

```
GT 覆盖率 = 已确认字段数 / 必填字段数
GT 冲突率 = 多源冲突字段数 / 已采集字段数
证据充分度 = 有官方或权威来源支持的字段数 / 已确认字段数
```

---

## Section 2: KPI 体系升级 (5 → 10)

### 2.1 完整指标体系

#### 可见度层

| # | 指标 | 状态 | 分子 | 分母 | 排除规则 |
|---|---|---|---|---|---|
| 1 | SOV | 已有 | 品牌名+别名提及的回答数 | 全部回答数 | — |
| 2 | 首次推荐率 | 已有 | 品牌出现在列表首位+推荐关键词的回答数 | 全部回答数 | — |
| 3 | **场景联想率** | **新增 P0** | 品牌在非品牌名场景问题中被提及次数 | 场景问题总数 | 排除含品牌名的直接提问 |
| 4 | 问题覆盖广度 | P1 | 品牌出现的问题类型数 | 全部问题类型数 | — |

#### 认知质量层

| # | 指标 | 状态 | 分子 | 分母 | 排除规则 |
|---|---|---|---|---|---|
| 5 | 信息准确率 | 已有 | GT 字段匹配正确的数量(含 alias 匹配) | 全部 GT 字段数 | uncertain 字段不参与 |
| 6 | 信息完整度 | 已有 | GT 必填字段被覆盖的数量 | 全部 GT 必填字段数 | — |
| 7 | **语义锚点稳定度** | **新增 P0** | 所有回答中 positioning_keywords 命中数 | 回答数 × keyword 数 | 跨平台取均值 |
| 8 | **差异化识别率** | **新增 P0** | AI 正确提及 key_differentiators 的回答数 | 品牌被提及的回答数 | 品牌未被提及时记为 0 |
| 9 | **跨平台一致性** | **新增 P0** | 核心字段在各平台判断一致的字段数 | 核心字段总数 | partial collection 时仅计算有效平台 |
| 10 | **推荐理由质量** | **新增 P0** | 回答推荐理由与 preferred_recommendation_reasons 匹配得分(0-3) | 品牌被推荐的回答数 | 仅品牌被列举但无理由记 0 |

### 2.2 每个 KPI 必含元数据

```json
{
  "metric_key": "scenario_recall_rate",
  "metric_value": 0.33,
  "numerator": 2,
  "denominator": 6,
  "sample_size": 6,
  "valid_answer_count": 5,
  "failed_answer_count": 1,
  "confidence": "medium",
  "details": {}
}
```

### 2.3 MetricsSnapshot 扩展方案

保留 5 个基础字段 (sov, first_rec_rate, accuracy_rate, completeness_rate, citation_rate)。新增 KPI 不直接在 MetricsSnapshot 上加列，而是放入 `details_json` (JSONB)：

```json
{
  "extended_kpis": {
    "scenario_recall_rate": {"value": 0.33, "sample_size": 6, "confidence": "medium"},
    "semantic_stability": {"value": 0.71, "sample_size": 69, "confidence": "high"},
    ...
  }
}
```

后续需要独立查询时再建 `MetricValue` 模型（`snapshot_id + metric_key + metric_value + sample_size + details_json`）。

### 2.4 指标分层上线

| 阶段 | 内容 | 时机 |
|---|---|---|
| 本次 | 10 KPI: 5 已有 + 5 新增 P0 | Phase 10 |
| 后续 | +信任与竞争指标 (6 个 P1) | 需要更多 GT 字段支持 |
| 后续 | +长期闭环指标 (3 个 P2) | 需 2-4 周数据积累 |

---

## Section 3: Action 内容执行准备器

### 3.1 核心原则

```
系统只生成内容草稿和发布清单，不自动发布到任何第三方平台。
所有内容必须基于 active GroundTruth，不得虚构。
生成输出必须经过事实检查 + 禁止声明检查 + 来源覆盖检查。
```

### 3.2 从建议到执行

```
Action Plan 生成
    ↓
用户确认要执行哪个 Action
    ↓
系统检查 active GT 是否完整
    ↓
系统生成 Content Package 草稿
  - 输入: active GT + source_of_truth_by_field + forbidden_claims + preferred_recommendation_reasons
    ↓
自动事实检查 + 禁止声明检查 + 来源覆盖检查
    ↓
用户审核内容
    ↓
导出: Markdown / Schema JSON-LD / 发布清单（含平台合规提醒）
    ↓
系统记录发布时间和发布 URL（用户填写）
    ↓
下次监测验证 KPI 变化
```

### 3.3 触发→内容映射

| 触发条件 (可配置) | 生成内容 | 交付格式 |
|---|---|---|
| P0 幻觉 | 纠错声明 + FAQ 页面 | Markdown + FAQ Schema JSON-LD |
| 引用率 < ACTION_THRESHOLD | Organization Schema | JSON-LD + 部署指导 |
| 准确率 < ACTION_THRESHOLD | 「关于我们」标准页面 | Markdown |
| 完整度 < ACTION_THRESHOLD | 完整品牌介绍页 | Markdown |
| 首次推荐率 < ACTION_THRESHOLD | 行业对比文章 | Markdown + 发布清单 |
| 差异化识别率 < ACTION_THRESHOLD | 竞品对比页 | Markdown + Comparison Schema |
| 场景联想率 < ACTION_THRESHOLD | 场景化 FAQ / 解决方案页 | Markdown + FAQ Schema |

阈值配置化 (`config.py`):

```python
ACTION_THRESHOLDS = {
    "citation_rate": 0.05,
    "accuracy_rate": 0.60,
    "completeness_rate": 0.50,
    "first_rec_rate": 0.10,
    "differentiation_rate": 0.30,
    "scenario_recall_rate": 0.20,
}
```

### 3.4 内容生成 Prompt 约束

```
只能使用 active GroundTruth 中已确认字段
不得虚构客户、融资、奖项、认证、市场份额、合作伙伴
不得使用未经证实的"领先""第一""最大"等表述
涉及竞品对比时必须保持客观，不得贬损竞品
所有事实性段落必须标注来源于哪个 GT 字段
不确定信息必须省略，不得猜测
```

### 3.5 内容质量检查

```json
{
  "fact_check_passed": true,
  "forbidden_claims_check_passed": true,
  "source_coverage_score": 0.85,
  "needs_human_review": false
}
```

### 3.6 Content Package 模型

```python
class ContentPackage(Base):
    __tablename__ = "content_packages"
    id, action_plan_id, organization_id, brand_id
    content_items: JSONB       # [{type, title, body, target_platform, format, source_fields, risk_flags}]
    schema_items: JSONB         # [{schema_type, jsonld_content}]
    publishing_checklist: JSONB # [{platform, notes, compliance_warnings}]
    fact_check_report: JSONB
    status: draft | reviewed | exported | published
```

### 3.7 发布清单平台合规提醒

| 平台 | 注意事项 |
|---|---|
| 官网 CMS | 可发布完整 Markdown，但需品牌审核 |
| 官网 `<head>` | 仅发布经过技术检查的 JSON-LD |
| 知乎 | 需改写为知识分享，不宜硬广 |
| 百度百科 | 需中立、可验证、非营销化，不应自动生成夸张表述 |
| 小红书 | 需改写为轻量内容，不宜直接复制官网长文 |

### 3.8 执行后验证

每个 Content Package 自动生成验证计划：

```json
{
  "verification_questions": ["{品牌} 是什么？", "...场景问题..."],
  "target_kpis": ["citation_rate", "scenario_recall_rate"],
  "expected_improvement": "citation_rate +10pp",
  "suggested_retest_date": "发布后 2 周"
}
```

---

## Section 4: 改动范围

### 4.1 新增数据模型

```
GroundTruthCandidate, GroundTruthEvidence, GroundTruthReview
ContentPackage, ContentItem
```

### 4.2 新增模块

```
src/collector/gt_collector.py           # GT 采集编排
src/search/__init__.py                  # SearchBackend 接口 + PlatformCapabilities
src/search/duckduckgo_backend.py
src/search/ai_search_backend.py
src/search/google_search_backend.py     # Google Custom Search (需 Key+cx)
src/analyzer/gt_aggregator.py           # GT 聚合 + 字段级置信度
src/analyzer/gt_confidence.py           # 置信度评分引擎
src/analyzer/gt_conflict_detector.py    # 冲突检测
src/analyzer/scenario_recall.py         # 场景联想率
src/analyzer/semantic_stability.py      # 语义锚点稳定度
src/analyzer/differentiation.py         # 差异化识别率
src/analyzer/cross_platform_consistency.py  # 跨平台一致性
src/analyzer/recommendation_quality.py  # 推荐理由质量
src/actions/executor.py                 # Action 内容生成引擎
src/actions/content_package.py          # Content Package 管理
src/actions/fact_checker.py             # 事实检查
src/actions/schema_generator.py         # Schema JSON-LD 生成
```

### 4.3 修改模块

```
src/models/ground_truth.py              # 扩展 GT 字段
src/models/metrics_snapshot.py          # details_json 包含 extended_kpis
src/analyzer/pipeline.py                # +5 新 KPI 计算
src/analyzer/evaluator.py               # alias 匹配 + category 校验
src/config.py                           # 搜索配置 + KPI 阈值 + Action 阈值
src/api/ground_truth.py                 # GT 自动采集 API
src/api/actions.py                      # +执行确认 + Content Package 端点
src/api/dashboard.py                    # 新 KPI + Content Package 展示
src/templates/dashboard/index.html      # 新 KPI 卡片
src/templates/ground_truth/review.html  # GT 字段级审核页面
```

### 4.4 测试

~20 new tests: GT 采集 (5) + GT 置信度/冲突 (2) + KPI (5) + Action 内容生成 (5) + E2E (1) + 安全 (2)

---

## Section 5: 执行阶段

| 阶段 | 内容 |
|---|---|
| **1. 数据模型** | GT Candidate/Evidence/Review + Content Package、GT 字段扩展、migration、模型测试 |
| **2. 搜索层** | DuckDuckGo + AI search 后端、SearchBackend 接口、PlatformCapabilities、Google Search 预留 |
| **3. GT 自动采集** | gt_collector 编排 → gt_aggregator 字段级聚合 → gt_confidence 评分 → gt_conflict_detector → 生成 Candidate |
| **4. GT 审核层** | 字段级确认界面、高风险字段强制审核、active GT 生成、完备性检查、触发正式采集 |
| **5. 5 新 KPI** | 场景联想率/语义锚点/差异化/跨平台一致性/推荐理由质量、含 sample_size+confidence、pipeline 集成、details_json 写入 |
| **6. Action 内容执行准备器** | executor → Content Package → fact_checker → schema_generator → 用户审核 → 导出交付 |
| **7. Dashboard + E2E** | GT 审核页、新 KPI 卡片、Content Package 页、E2E 验收 |
