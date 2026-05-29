# Design: GT 自动采集 + Action 自动执行 + KPI 体系升级 (Phase 10)

**日期:** 2026-05-29
**状态:** Draft — 待审阅
**依赖:** Phase 9 已交付（采集→分析→洞察全链路自动运行）

---

## 概述

Phase 10 补齐 GEO Explorer 的两个核心缺口，同时升级指标体系：

1. **GT 自动采集** — 从「人工填写 GT」升级为「系统自动收集 + 交叉验证 + 用户确认」
2. **Action 自动执行** — 从「只给优化建议」升级为「生成完整内容 + 发布清单」
3. **KPI 体系升级** — 从 5 基础指标 升级为 10 指标（5 已有 + 5 新增 P0）

---

## Section 1: GT 自动采集器

### 1.1 输入方式

渐进式输入：用户只需填公司名即可开始，系统在采集过程中自动发现 URL 并追加采集。

### 1.2 数据流

```
用户输入: 公司名（必填）+ URL（可选）
    ↓
第一轮: AI 平台采集 (3 平台 × 8 问题 = 24 次查询)
  DeepSeek + Kimi + 豆包
  8 个 GT 采集问题 → 候选 GT 字段 + 各平台一致性评分
    ↓
第二轮: DuckDuckGo 搜索交叉验证
  搜索 "{公司} 公司" / "{公司} 产品" / "{公司} 官网"
  → 从搜索结果摘要提取: 工商信息、官网 URL、行业描述
    ↓
第三轮: AI 平台内置搜索 (DeepSeek/Kimi web search)
  search_enabled=True 再跑一轮，获取带引用的实时信息
    ↓
聚合引擎: LLM (DeepSeek) 结构化
  输入: AI 平台结果 + DuckDuckGo 结果 + AI 搜索增强结果
  规则:
    - AI + 搜索都一致 → confidence=high
    - 仅 AI 有 → confidence=medium
    - 仅搜索有 → confidence=low
    - 三源都不一致 → mark as uncertain
    ↓
输出: GT JSON + 每字段证据来源 + 置信度
    ↓
用户确认 GT → 写入 GroundTruthVersion → 自动触发正式采集
```

### 1.3 GT 采集问题模板 (8 个)

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

### 1.4 GT 模板扩展

在现有 GT 字段基础上，P0 优先新增 8 个字段：

| 新字段 | 支撑能力 |
|---|---|
| `aliases` (增强) | SOV 更准确、场景联想率 |
| `category` | 信息准确率（品类判断）、跨平台一致性 |
| `core_scenarios` | 场景联想率、推荐理由质量 |
| `scenario_keywords` | 场景联想率、语义锚点稳定度 |
| `target_competitors` | 竞品共现率、差异化识别率 |
| `preferred_recommendation_reasons` | 推荐理由质量、差异化识别率 |
| `forbidden_claims` (增强) | 负面幻觉率、合规风控 |
| `source_of_truth_by_field` | 官方引用率、可信来源多样性、证据追溯 |

### 1.5 搜索层设计

多源可插拔架构——每个搜索源实现统一接口，有 Key 就用，没 Key 就跳过：

```python
class SearchBackend:
    name: str
    async def search(query: str, num: int = 5) -> list[SearchResult]
```

| 层级 | 搜索源 | 费用 | 状态 |
|---|---|---|---|
| L1 | DuckDuckGo | 免费，零 Key | ✅ 默认可用 |
| L2 | AI 平台 web search (DeepSeek/Kimi) | 已有 Key | ✅ 可用 |
| L3 | Brave Search API | 免费 2000次/月 | 备选（后续注册） |

Google Custom Search API Key 已获取 (`AIzaSyD6Ydkx1on4symlnGAH_BFB61xdWQprC-w`)，但缺 cx（Search Engine ID）。用户创建搜索引擎失败，待解决后接入 L4。

### 1.6 新增模块

```
src/collector/gt_collector.py       # GT 采集编排 (orchestrator)
src/search/                          # 搜索层（可插拔）
├── __init__.py                      # SearchBackend 接口 + 组合器
├── duckduckgo_backend.py            # DuckDuckGo 实现
├── ai_search_backend.py             # AI 平台 web search 实现
src/analyzer/gt_aggregator.py        # GT 聚合 + LLM 结构化 + 置信度评分
src/api/ground_truth.py              # GT 自动采集 API 端点
tests/test_gt_collector.py
tests/test_gt_aggregator.py
```

---

## Section 2: KPI 体系升级 (5 → 10)

### 2.1 完整 10 指标

#### 可见度层 (4)

| # | 指标 | 状态 | 计算方式 |
|---|---|---|---|
| 1 | SOV 声量份额 | 已有 | 品牌名+别名在所有回答中的提及率 |
| 2 | 首次推荐率 | 已有 | 品牌出现在列表首位+推荐关键词匹配 |
| 3 | **场景联想率** | 新增 P0 | 品牌在非品牌名场景问题中被提及次数 / 场景问题总数 |
| 4 | 问题覆盖广度 | P1 后续 | 品牌出现的问题类型数 / 问题类型总数 |

#### 认知质量层 (6)

| # | 指标 | 状态 | 计算方式 |
|---|---|---|---|
| 5 | 信息准确率 | 已有 | GT 字段精确匹配 + 列表覆盖率 |
| 6 | 信息完整度 | 已有 | GT 必填字段的覆盖比例 |
| 7 | **语义锚点稳定度** | 新增 P0 | `positioning_keywords` 在 AI 回答中的出现比例(跨平台均值) |
| 8 | **差异化识别率** | 新增 P0 | AI 正确提及 `key_differentiators` 的回答数 / 品牌被提及回答数 |
| 9 | **跨平台一致性** | 新增 P0 | 核心 GT 字段在 3 平台中判断一致的平台数 / 总平台数 |
| 10 | **推荐理由质量** | 新增 P0 | AI 推荐理由与 `preferred_recommendation_reasons` 的匹配度(0-3 评分) |

#### 现有 KPI 增强

| 现有 KPI | 增强点 |
|---|---|
| SOV | 使用 `aliases` 别名匹配——不只数全称也数简称/英文名 |
| 信息准确率 | 新增 `category` 字段校验——不只判断 GT 字段对错，也判断品类归属 |
| 官方引用率 | 使用 `source_of_truth_by_field`——不只数域名出现，也判断引用页面是否正确 |

### 2.2 新增 KPI vs GT 字段依赖

| 新增 KPI | 依赖的 GT 新字段 |
|---|---|
| 场景联想率 | core_scenarios, scenario_keywords |
| 语义锚点稳定度 | positioning_keywords |
| 差异化识别率 | key_differentiators |
| 跨平台一致性 | category, core_products, target_users |
| 推荐理由质量 | preferred_recommendation_reasons |

### 2.3 指标分层上线计划

| 阶段 | 内容 | 时机 |
|---|---|---|
| 阶段一 (本次) | 10 KPI: 5 已有 + 5 新增 P0 | Phase 10 |
| 阶段二 | +信任与竞争指标 (竞品共现率、AI 信任倾向、负面幻觉率、可信来源多样性、决策推进率) | 后续 |
| 阶段三 | +长期闭环指标 (时间稳定性、行动验证提升率、内容优化响应率) | 需 2-4 周数据积累 |

---

## Section 3: Action 自动执行器

### 3.1 从建议到执行

```
当前: 检测到问题 → 生成 Content Brief → (停)
目标: 检测到问题 → 生成方案 → 用户确认 → 自动生成完整内容 → 多格式交付
```

### 3.2 触发→内容映射

| 触发条件 | 生成内容 | 交付格式 |
|---|---|---|
| P0 幻觉 (AI 说错事实) | 纠错声明 + FAQ 页面 | Markdown + FAQ Schema JSON-LD |
| 引用率 < 5% | 品牌结构化数据 (Organization Schema) | JSON-LD + 部署指导 |
| 准确率 < 60% | 「关于我们」标准页面 | Markdown |
| 完整度 < 50% | 完整品牌介绍页 (含产品/场景/用户) | Markdown |
| 首次推荐率 < 10% | 行业对比文章 / 评测 | Markdown + 发布清单 |
| 差异化识别率 < 30% | 竞品对比页 | Markdown + Comparison Schema |
| 场景联想率 < 20% | 场景化 FAQ / 解决方案页 | Markdown + FAQ Schema |

### 3.3 内容生成流程

```
Action Plan 生成
    ↓
用户确认界面 (确认 / 修改 / 跳过)
    ↓ 确认
LLM (DeepSeek) 基于 GT 事实 + AI 平台分析 + 竞品数据 生成完整内容
    ↓
保存到 content_library 表
    ↓
交付物:
  - Markdown 文件 (可直接复制到官网 CMS)
  - Schema.org JSON-LD (可粘贴到官网 <head>)
  - 发布平台清单 + 针对各平台的格式化文本
```

### 3.4 发布准备清单 (B 方案)

```
✅ 内容文件保存到 content_library/
✅ 结构化数据 (Schema.org JSON-LD)
📋 发布平台清单:
   - 官网 CMS → 复制 Markdown
   - 官网 <head> → 粘贴 JSON-LD
   - 知乎 → 转换为文章格式
   - 百度百科 → 对照更新词条
   - 小红书 → 截取精华段落
⏱ 下次监测: 发布 N 周后重新采集，验证优化效果
```

### 3.5 新增/修改模块

```
src/actions/executor.py              # Action 自动执行引擎 (新)
src/actions/engine.py                # 扩展: +执行确认逻辑
src/api/actions.py                   # 扩展: +执行确认 +内容生成端点
src/templates/actions/confirm.html   # 用户确认界面 (新)
tests/test_action_executor.py        # (新)
```

---

## Section 4: 整体改动范围

### 4.1 新增文件 (12)

```
src/collector/gt_collector.py
src/search/__init__.py
src/search/duckduckgo_backend.py
src/search/ai_search_backend.py
src/analyzer/gt_aggregator.py
src/analyzer/scenario_recall.py        # 场景联想率
src/analyzer/semantic_stability.py     # 语义锚点稳定度
src/analyzer/differentiation.py        # 差异化识别率
src/analyzer/cross_platform_consistency.py  # 跨平台一致性
src/analyzer/recommendation_quality.py      # 推荐理由质量
src/actions/executor.py
src/api/ground_truth.py
tests/test_gt_collector.py
tests/test_gt_aggregator.py
tests/test_kpi_extended.py             # 5 个新增 KPI 测试
tests/test_action_executor.py
```

### 4.2 修改文件 (8)

```
src/models/ground_truth.py            # 扩展 GT 字段 (8 新增)
src/config.py                          # 搜索配置 + 新 KPI 阈值
src/analyzer/pipeline.py              # +5 个新 KPI 计算 + 新 KPI 写入 MetricsSnapshot
src/analyzer/evaluator.py             # 增强: aliases 匹配 + category 校验
src/api/dashboard.py                  # 扩展: 新 KPI 展示
src/templates/dashboard/index.html    # 新 KPI 卡片
src/api/brands.py                     # GT 自动采集触发端点
src/models/metrics_snapshot.py        # 扩展: 新增 KPI 字段
src/actions/engine.py                 # +执行确认逻辑
```

### 4.3 测试目标

~15 new tests: GT 采集 (4) + GT 聚合 (3) + 5 新 KPI (5) + Action 执行 (3)

---

## Section 5: 执行阶段

| 阶段 | 内容 | 依赖 |
|---|---|---|
| **1. GT 模型扩展** | GroundTruthVersion 扩展 8 字段、migration、模型测试 | 无 |
| **2. 搜索层** | DuckDuckGo + AI search 后端、SearchBackend 接口、可插拔组合器 | 无 |
| **3. GT 自动采集** | gt_collector 编排器、gt_aggregator 聚合引擎、API 端点 | 1, 2 |
| **4. 5 新 KPI** | 场景联想率/语义锚点/差异化/跨平台一致性/推荐理由质量、pipeline 集成 | 1 |
| **5. MetricsSnapshot 扩展** | 新 KPI 字段、migration、Dashboard KPI 卡片 | 4 |
| **6. Action 自动执行** | executor 引擎、用户确认流程、内容生成 + 交付 | 1 |
| **7. 端到端验证** | GT 采集 → 正式采集 → 10 KPI → Insights → Action 执行 | 3, 5, 6 |
