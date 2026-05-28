# GEO Explorer — 品牌AI可见度监测与优化系统

> 品牌 AI 认知运营系统：监测 → 分析 → 行动 → 验证，闭环迭代。

## 1. 项目定位

内部使用的品牌 AI 可见度管理平台，监测品牌在多个 AI 引擎中的表现，提供可落地的优化行动方案。架构预留 SaaS 多租户扩展能力。

**对标系统：** [GEOAhead](https://geoahead.com/) — 让品牌在 AI 答案里被正确推荐。

**最终目标：** 不是「监测工具」，而是品牌 AI 认知运营系统。帮助品牌在 AI 世界中建立稳定、准确、可引用的认知。

## 2. 核心闭环

```
输入品牌/企业名称
    ↓
【监测层】向 4 个 AI 平台 → 系统性质询 → 采集 AI 回答
    ↓
【分析层】计算 5 大指标 → 检测幻觉 → 竞品对比
    ↓
【行动层】生成可执行任务 → 内容工厂执行 → 下次监测验证效果
    ↓
循环迭代，持续提升 AI 可见度
```

## 3. 目标用户与使用场景

| 用户角色 | 使用场景 |
|---|---|
| 品牌运营负责人 | 每周查看品牌在 AI 中的表现，发现认知偏差 |
| 内容/市场团队 | 根据 Action Plan 执行具体优化任务 |
| 管理层 | 查看竞品对比和趋势报告，评估品牌 AI 资产健康度 |
| GEO 策略师 | 深度分析问题明细、幻觉报告、调整策略 |

后续 SaaS 化后支持多品牌、多团队协作。

## 4. 系统架构

```
┌──────────────────────────────────────────────────────────────┐
│                      GEO Explorer                              │
├──────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │DeepSeek  │  │  Kimi    │  │  豆包    │  │  文心    │      │
│  │ Adapter  │  │ Adapter  │  │ Adapter  │  │ Adapter  │      │
│  │query()     │  │query()     │  │query()     │  │query()     │      │
│  │extract_   │  │extract_   │  │extract_   │  │extract_   │      │
│  │citations()│  │citations()│  │citations()│  │citations()│      │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘      │
│       └──────────────┴─────────────┴──────────────┘           │
│                          │                                     │
│              ┌───────────▼───────────┐                         │
│              │   监测层 (Collector)   │                         │
│              │  问题模板 → 并发查询   │                         │
│              │  Prompt版本管理       │                         │
│              │  原始请求/响应落盘     │                         │
│              └───────────┬───────────┘                         │
│                          │                                     │
│              ┌───────────▼───────────┐                         │
│              │   分析层 (Analyzer)    │                         │
│              │  SOV│首推│讲对│完整度│引用率                      │
│              │  HallucinationDetector│                         │
│              │  竞品矩阵引擎          │                         │
│              └───────────┬───────────┘                         │
│                          │                                     │
│              ┌───────────▼───────────┐                         │
│              │  行动层 (Action Engine)│                         │
│              │  优先级引擎│可执行任务  │                         │
│              │  Content Factory      │                         │
│              │  效果验证│策略库沉淀   │                         │
│              └───────────┬───────────┘                         │
│                          │                                     │
│              ┌───────────▼───────────┐                         │
│              │     Web Dashboard      │                         │
│              │  7 页面架构（见§15）   │                         │
│              └───────────────────────┘                         │
│                                                                │
│  PostgreSQL │ Redis │ Celery │ FastAPI │ Jinja2+HTMX           │
└──────────────────────────────────────────────────────────────┘
```

## 5. 技术选型

| 层 | 技术 | 原因 |
|---|---|---|
| 后端框架 | FastAPI (Python 3.12) | 异步原生，对接 4 个 AI API 并发查询 |
| 任务队列 | Celery + Redis | 周期采集 + 分析计算调度 |
| 数据库 | PostgreSQL 16 | JSONB 存 Ground Truth 和指标明细 |
| 前端 | Jinja2 + HTMX | V1 快速验证，不做 SPA |
| 部署 | Docker Compose | 一键启动全部服务 |

## 6. AI 平台接入方案

V1 覆盖 4 个国内 AI 平台：

| 平台 | 接入方式 | Base URL | 鉴权 | 预估单价(输入/百万token) |
|---|---|---|---|---|
| DeepSeek | OpenAI SDK 兼容 | api.deepseek.com | API Key | ¥1 (V4-Flash) |
| Kimi (Moonshot) | OpenAI SDK 兼容 | api.moonshot.cn/v1 | API Key | ¥1-2 (K2系列) |
| 豆包 (字节) | volcenginesdkarkruntime | ark.cn-beijing.volces.com/api/v3 | API Key | ¥2-4 |
| 文心 (百度) | 千帆 V2 (OpenAI兼容) | 千帆 endpoint | API Key + Secret Key | ¥2-8 |

**Adapter 职责（精简后）：**

```python
class PlatformAdapter(ABC):
    async def query(prompt: str, params: QueryParams) -> AIResponse
    async def extract_citations(response: str) -> list[Citation]
```

Adapter 只负责：平台调用、响应解析、引用提取。**幻觉检测不在 Adapter 中**，统一放在分析层的 `HallucinationDetector`。

每个平台对应一个 Adapter 实现，对接 OpenAI SDK 兼容格式（豆包除外，需 volcenginesdkarkruntime）。统一通过环境变量或配置表读取 API Key。

## 7. Ground Truth 事实库管理 [P0]

### 7.1 设计原则

Ground Truth 是讲对率、幻觉检测、行动计划的共同地基。如果 Ground Truth 不可靠：

- AI 说错了但系统判断不了 → 漏报。
- AI 说得合理但 Ground Truth 太窄 → 误报。

因此 Ground Truth 需要**字段标准 + 来源标注 + 审核流程 + 版本管理**。

### 7.2 字段标准

每个品牌必须维护以下字段：

| # | 字段 | 级别 | 说明 | 示例 |
|---|---|---|---|---|
| 1 | `official_name` | P0 | 品牌官方中文全称 | 北京象往科技有限公司 |
| 2 | `aliases` | P0 | 品牌别名/简称/英文名/产品名 | ["象往科技","Xiangwang","Tourism_Xiangwang"] |
| 3 | `industry` | P0 | 行业归属 | 旅游科技 / SaaS |
| 4 | `category` | P0 | 产品/服务类型 | 旅游行业自动化解决方案 |
| 5 | `positioning` | P0 | 一句话核心定位 | 飞猪业务自动化运营平台 |
| 6 | `target_users` | P1 | 目标用户群 | 飞猪商家、旅游行业运营人员 |
| 7 | `core_scenarios` | P1 | 核心使用场景 | 订单管理、数据采集、日报生成、流量监控 |
| 8 | `differentiators` | P1 | 差异化优势 | 一站式飞猪业务数据整合，覆盖KPI/订单/流量/投放四大板块 |
| 9 | `tech_tags` | P2 | 技术/能力标签 | ["Python","自动化","数据采集","Selenium","Playwright"] |
| 10 | `market_position` | P2 | 行业阶段/市场地位 | 垂直领域工具，服务飞猪生态 |
| 11 | `official_domains` | P0 | 官网与官方域名 | ["xiangwang.com"]（示例） |
| 12 | `trusted_sources` | P1 | 可信来源 URL 列表 | 官网、官方文档、官方博客 |
| 13 | `forbidden_claims` | P1 | 禁止表述 | ["市场第一","行业唯一","100%覆盖"] |
| 14 | `competitors` | P0 | 核心竞品列表 | ["竞品A","竞品B"] |

### 7.3 版本管理

Ground Truth 必须版本化。品牌事实变更后需创建新版本，旧版本保留用于历史指标回溯。

数据模型：

```
ground_truth_versions
  id (PK)
  brand_id (FK → brands)
  version (int)
  ground_truth_json (JSONB)
  source_urls (TEXT[])
  reviewer (string)
  status: draft | active | deprecated
  created_at
  updated_at
```

- `active` 状态只能有一条记录（当前生效版本）。
- 指标计算始终关联到采集时生效的 Ground Truth 版本，保证历史数据可复现。
- 版本变更触发人工审核：reviewer 确认后 status → active。

## 8. Prompt 与采集一致性设计 [P0]

### 8.1 问题

AI 回答高度受 Prompt、模型版本、温度、是否联网影响。如果这些参数不持久化，指标波动无法归因。例如某品牌本周 SOV 下降，可能是：

1. 品牌内容真的少了。
2. AI 平台模型升级了。
3. 系统 Prompt 调整了。
4. 开启/关闭了联网搜索。

没有记录就无法判断。

### 8.2 设计

**Prompt 版本管理表：**

```
prompt_versions
  id (PK)
  name
  system_prompt (TEXT)
  template_rules (JSONB)     -- 变量替换规则
  version (int)
  status: draft | active | deprecated
  created_at
  updated_at
```

**采集请求/响应完整落盘：**

每个 `query_results` 记录保存：

```
query_results 扩展字段：
  prompt_version_id (FK → prompt_versions)
  system_prompt (TEXT)        -- 实际使用的 system prompt 快照
  user_prompt (TEXT)          -- 模板渲染后的最终 user prompt
  template_version (int)
  request_payload_json (JSONB) -- 完整请求体（脱敏后）
  response_raw_json (JSONB)    -- 完整原始响应
  model_name
  model_version
  temperature
  top_p
  max_tokens
  search_enabled (bool)
  latency_ms
  status: success | timeout | rate_limited | error
  error_code
  error_message
  retry_count
  collected_at
```

预期价值：
- 结果可复现、指标波动可归因。
- 支持不同 Prompt 策略的 A/B 测试。
- 支持回溯历史采集条件。

## 9. 监测层设计

### 9.1 问题模板引擎

5 个维度 × 22 个标准问题模板：

| 维度 | 问题数 | 目的 | 示例 |
|---|---|---|---|
| 定义认知 | 4 | AI 的基本定义是否准确 | "{品牌} 是什么？" "{品牌} 属于什么行业？" |
| 场景推荐 | 5 | 是否出现在推荐列表，排第几 | "最好用的{行业}工具有哪些？" "小团队适合什么{品类}？" |
| 对比评价 | 4 | AI 如何看待与竞品的差异 | "{品牌} 和 {竞品} 有什么区别？" |
| 信任验证 | 4 | 犹豫型问题中 AI 如何描述 | "{品牌} 靠谱吗？" "{品牌} 的用户口碑怎么样？" |
| 场景联想 | 5 | 场景描述时 AI 是否自然联想到品牌 | "想做跨境电商，用什么工具？" |

模板变量：`{品牌}` `{行业}` `{品类}` `{竞品}` `{场景}` — 从品牌 Ground Truth 动态填充。

用户可添加自定义问题模板，关联到任意维度。

### 9.2 采集频率

- **默认：** 每周一次（Celery Beat，周一凌晨 03:00）
- **手动触发：** 品牌首次添加时立即全量采集
- **单品牌重采：** Dashboard 提供单品牌「立即重采」按钮
- **并发控制：** 4 平台并行，每平台内 22 个问题串行（避免触发频率限制）

## 10. 指标体系与判定规则 [P0]

### 10.1 指标总览

| # | 指标 | 目的 | 核心衡量 |
|---|---|---|---|
| 1 | SOV 体感覆盖率 | AI 是否在回答中提及你 | 品牌被提及的有效回答占比 |
| 2 | 首推率 | AI 是否优先推荐你 | 推荐列表/表述中排第一的占比 |
| 3 | 讲对率 (Accuracy) | AI 提及你时说得对不对 | AI 提及字段中正确描述的占比 |
| 4 | 认知完整度 (Completeness) | AI 是否全面了解你 | Ground Truth 关键字段被正确覆盖的占比 |
| 5 | 引用感知率 | AI 是否引用你的官方来源 | 明确引用官网/可信来源的占比 |

> 注：讲对率拆为 Accuracy + Completeness 两个指标，避免「AI 少说少错所以讲对率很高」的问题。

### 10.2 SOV 体感覆盖率

**指标目的：** 品牌在 AI 回答中出现频率和广度。

```
SOV = 品牌被提及的有效回答数 / 有效回答总数 × 100%
```

**分子 — 品牌被提及的有效回答数：**
- 官方名称 `official_name` 命中 → 算提及。
- `aliases` 中任意别名命中 → 算提及。
- 产品名是否算提及 → 在 Ground Truth 中配置（`aliases` 包含产品名即算）。
- **只出现在引用 URL 中但正文未出现 → 不算提及。**
- 负面提及 → 算提及，但额外标记 `sentiment: negative`。

**分母 — 有效回答总数：**
- AI 正常返回有效内容的回答。
- 排除：拒答、空答、超时、接口失败、返回乱码（另行统计为采集失败率）。

**分母排除统计：**

```
采集失败率 = 无效回答数 / 总尝试查询数 × 100%
```

单独展示，不混入 SOV。

**维度切分：** 全局 SOV / 单平台 SOV / 单维度 SOV / 时间趋势（周环比）。

### 10.3 首推率 First-Recommendation Rate

**指标目的：** AI 在多选项推荐中是否优先推荐该品牌。

```
首推率 = 品牌被判定为第一推荐的次数 / 推荐类有效回答数 × 100%
```

**分子 — 第一推荐判定：**

| 回答形式 | 判定规则 |
|---|---|
| 有序列表（1. XX 2. YY） | 序号 1 的品牌 = 第一推荐 |
| 无序列表（- XX - YY） | 首个列出的品牌 + LLM 辅助语义判断 |
| 自然段落 | 出现"首选""最推荐""优先考虑""强烈推荐"且指向目标品牌 → 判为首推 |
| 细分场景首推 | 品牌只在某个细分场景中排第一 → 标记为 `局部首推`，不直接等同全局首推 |
| 无推荐表述 | 不计入分子 |

**分母 — 推荐类有效回答数：**
- 仅限「场景推荐」维度的 5 个问题。
- 排除 AI 未做任何推荐的回答（如拒答、纯定义式回答）。

### 10.4 讲对率 Accuracy Rate

**指标目的：** AI 提及品牌时，描述的准确程度。

```
讲对率 = AI 提及字段中正确描述的字段数 / AI 提及的字段总数 × 100%
```

**「提及字段」定义：**
- AI 回答中明确描述了某个 Ground Truth 字段对应的信息。
- 通过 LLM 逐字段判定：对每个 Ground Truth 字段，判断 AI 回答中是否涉及、涉及后是否正确。

**判定标准（逐字段）：**

| 判定 | 条件 |
|---|---|
| ✅ 正确 | AI 描述与 Ground Truth 一致，语义匹配 |
| ❌ 错误 | AI 明确描述了该字段但内容与 Ground Truth 矛盾 |
| ⚠️ 存疑 | 描述模糊、部分正确、或涉及主观判断 |
| ⊘ 未提及 | AI 回答中未涉及该字段 |

**排除规则：**
- AI 未提及的字段不计入分母（不影响 Accuracy）。
- 存疑项计入分母但不判方向，标记需要人工复核。

**和 Ground Truth 字段级别的关联：**

| GT 字段级别 | 错误严重等级 |
|---|---|
| P0 字段错误 | 幻觉 P0 |
| P1 字段错误 | 幻觉 P1 |
| P2 字段错误 | 幻觉 P2 |

### 10.5 认知完整度 Completeness Rate [新增]

**指标目的：** AI 是否全面了解品牌（而不是只知其一）。

```
认知完整度 = AI 正确覆盖的 Ground Truth 关键字段数 / Ground Truth 应覆盖字段总数 × 100%
```

- 分母 = Ground Truth 中所有 active 字段（P0 + P1 + P2，排除 `official_domains` 和 `forbidden_claims`）≈ 12 个。
- 分子 = P0/P1/P2 字段中判定为「✅ 正确」的字段数。
- 「未提及」和「错误」都不计入分子。

**和讲对率的关系：**

| | 讲对率 (Accuracy) | 认知完整度 (Completeness) |
|---|---|---|
| 关注点 | AI 说的时候对不对 | AI 知道的够不够全 |
| 低分意味着 | AI 对你认知有错误 | AI 对你认知不完整，在很多方面不了解你 |

两者互补，避免「AI 只说你名字所以 Accuracy 100%」的偏差。

### 10.6 引用感知率 Citation Perception Rate

**指标目的：** AI 回答中是否主动引用品牌的官方来源。

```
引用感知率 = AI 回答中明确引用品牌官网或可信来源的次数 / 品牌被提及的有效上下文数 × 100%
```

**分子 — 明确引用判定：**

| 引用类型 | 是否计入 | 说明 |
|---|---|---|
| 官网 URL 命中（`official_domains` 中任意域名） | ✅ | URL 正则匹配 |
| 官方文档/官方博客/官方帮助中心 | ✅ | 需在 `trusted_sources` 中配置 |
| AI 明确注明 "据XX官网介绍" / "来源：XX" | ✅ | 中文引用句式识别 |
| 第三方媒体/百科/论坛引用 | 计入 `third_party_mention_rate` | **不计入引用感知率** |
| 模型未联网或平台不支持返回引用 | **标记能力限制** | 不计入分母 |

**分母 — 品牌被提及的有效上下文数：**
- AI 回答中提及品牌的独立段落或语义块数。

## 11. 幻觉检测设计 [P0]

### 11.1 职责归属

幻觉检测从 Adapter 剥离，统一放在分析层。

```python
# Adapter — 只做平台交互
class PlatformAdapter(ABC):
    async def query(prompt: str, params: QueryParams) -> AIResponse
    async def extract_citations(response: str) -> list[Citation]

# Analyzer — 统一幻觉检测
class HallucinationDetector:
    def extract_claims(response: str) -> list[Claim]
    def compare_with_ground_truth(claims: list[Claim], gt: GroundTruth) -> HallucinationReport
```

统一检测标准，跨平台结果可比较。

### 11.2 检测流程

```
AI 回答
  → Claim 提取（实体识别：品牌名、产品名、数值、日期、关系声明）
  → 与 Ground Truth 逐条比对
  → 输出判决：✅正确 / ❌错误 / ⚠️存疑 / ⊘未覆盖
  → 生成 HallucinationReport
```

### 11.3 报告内容

```
HallucinationReport:
  - brand_id
  - query_result_id
  - platform
  - severity: P0 | P1 | P2
  - field_name
  - ai_claim: "AI 说：总部在上海"
  - ground_truth: "实际：总部在杭州"
  - verdict: 错误
  - human_review_required: true/false
  - detected_at
```

P0 错误必须人工复核后再触发 Action Plan。

## 12. 竞品矩阵设计 [P1]

### 12.1 竞品来源

| 来源 | 方式 | 说明 |
|---|---|---|
| 用户手动指定 | 品牌设置中配置核心竞品 | 最权威 |
| AI 自动发现 | 采集结果中高频共现品牌 | 补充发现隐性竞品 |
| 系统推荐 | 按行业、场景、目标用户推荐 | 基于行业数据库 |

### 12.2 竞品分组

支持多组对比，避免口径混杂：

```
competitor_sets
  id (PK)
  brand_id (FK → brands)
  name: "核心竞品组" | "替代方案组" | "行业头部组"
  competitor_brand_ids (FK[] → brands)
  source_type: manual | auto_discovered | system_recommended
  version (int)
  is_active (bool)
  created_at
  updated_at
```

### 12.3 对比维度

```
竞品矩阵：
                你的品牌    竞品A    竞品B    行业均值
    SOV          65%       45%      30%       40%
    首推率        40%       35%      15%       25%
    讲对率        80%       60%      55%       58%
    完整度        55%       40%      30%       35%
    引用率        25%       10%      5%        10%
```

支持：按平台看、按问题维度看、按时间趋势看（周环比）。

## 13. Action Plan 行动任务系统 [P1]

### 13.1 触发到行动的映射

| 触发条件 | 行动类型 | 示例任务 |
|---|---|---|
| P0 身份锚点错误 | 定义纠正 | 重写官网 About 页面品牌定位描述 |
| SOV 落后竞品 | 场景渗透 | 列出竞品出现你缺失的 N 个场景，逐个覆盖 |
| 首推率低 | 权威建设 | 行业文章 + 第三方评测 + FAQ |
| 引用率低 | 官网结构化 | Schema JSON-LD 标记 |
| 认知完整度低 | 维度补全 | 针对未覆盖的 GT 字段创建专项内容 |
| 某维度完全缺失 | 内容新造 | 对比类内容从零创建 |

### 13.2 任务数据结构

```
action_plans
  id (PK)
  brand_id (FK → brands)
  organization_id (FK → organizations)
  trigger_type              -- 触发条件
  action_type               -- 行动类型
  priority: P0 | P1 | P2    -- 从分析层继承
  evidence_query_result_ids  -- 证据：哪些采集结果触发了此任务
  ai_wrong_claims (JSONB)    -- AI 说了什么错误内容（摘录）
  correct_ground_truth (JSONB) -- 正确的品牌事实
  suggested_content_type     -- 建议内容类型（对应 Content Factory 6 类）
  target_page                -- 建议修改的目标页面 URL
  platform_target            -- 建议发布的目标平台
  expected_metric_lift       -- 预期指标提升（如"讲对率 ↑15%"）
  acceptance_criteria (TEXT)  -- 验收标准
  owner (FK → users)         -- 负责人
  due_date                   -- 截止日期
  status: pending | in_progress | pending_review | completed
  review_notes (TEXT)
  created_at
  completed_at
  verified_at                 -- 下次监测后验证通过时间
```

### 13.3 任务示例

```
任务 ID: AP-001
标题: 重写官网 About 页面中的品牌定位描述
触发: DeepSeek "@品牌 是什么？" → 将品牌误判为"营销自动化工具"
AI 错误原句: "XX 是一家营销自动化 SaaS 公司"
正确表述: "XX 是专注于飞猪生态的旅游行业自动化运营平台"
建议内容形式: FAQ + Glossary（Content Factory 类型 1）
目标页面: https://example.com/about
验收标准: 下次采集中 P0 身份锚点错误消失，讲对率 ≥ 90%
负责人: @content-lead
截止: 2026-06-04
```

### 13.4 状态流转

```
pending → in_progress → pending_review → completed
                            ↓ (review rejected)
                        in_progress (rework)
                                    ↓
completed → (下次监测周期) → verified_at 设定 → 策略沉淀

若 verified 后指标未改善 → 追加二轮任务，标记关联前序任务
```

## 14. Content Factory 内容工厂 [P1]

### 14.1 6 类 AI 优化内容

| # | 类型 | 格式 | AI 目的 |
|---|---|---|---|
| 1 | 结构化定义 | FAQ / Glossary | 给 AI 一个无歧义的品牌定义锚点 |
| 2 | 场景问题库 | Q&A 矩阵 | 覆盖用户可能提的 50+ 个场景问题 |
| 3 | 对比清单 | Comparison Table | 在对比类问题中占据格式优势 |
| 4 | 行业知识 | Tutorial / Guide | 成为领域知识源，而非仅产品提供方 |
| 5 | 信任信号 | Case Study / Review | 多源一致性的核心载体 |
| 6 | 结构化元数据 | Schema / JSON-LD | AI 直接解析品牌事实 |

### 14.2 内容质量守则

Content Factory 不能变成「为 AI 可见度制造低质内容」的工具。每条内容必须遵守：

1. **真实性** — 内容必须基于真实产品能力和事实，不虚构。
2. **客观性** — 对比内容必须有客观依据，标注比较维度和数据来源。
3. **可验证** — 案例内容必须可追溯（客户名称、使用场景、数据来源）。
4. **禁止虚假声明** — 不得虚构客户、奖项、排名、市场地位。
5. **Schema 一致** — Schema 结构化事实必须与页面正文内容一致。
6. **禁止内容农场** — 不得批量生成低质量、重复、关键词堆砌页面。
7. **审核门禁** — P0 和 P1 相关内容产出需人工审核后发布。

## 15. Dashboard 信息架构 [P1]

### 15.1 页面结构

```
1. 总览页 /
   - 全局指标卡片（SOV / 首推率 / 讲对率 / 完整度 / 引用率）
   - 各指标周环比趋势
   - 幻觉风险数量（P0/P1/P2）
   - 待处理 Action Plan 数量
   - 采集状态（最近一次采集时间、成功率）

2. 品牌详情页 /brands/{id}
   - 品牌事实库展示与编辑
   - 5 大指标趋势图（按周）
   - 平台表现对比雷达图
   - 维度表现对比（5 维度 × 5 指标）

3. 问题明细页 /brands/{id}/queries
   - 按平台 × 问题维度筛选
   - 每个平台的原始 AI 回答全文
   - 品牌提及判定（是否出现、位置、情绪）
   - 推荐位置标注
   - 引用来源标注
   - 错误声明高亮

4. 幻觉报告页 /brands/{id}/hallucinations
   - P0 / P1 / P2 错误分布饼图
   - 跨平台错误对比
   - 错误字段详情列表
   - 每条错误的 AI 原句 vs Ground Truth 对比
   - 人工复核按钮（修正判决）

5. 竞品矩阵页 /brands/{id}/competitors
   - 品牌 × 指标 × 时间对比表
   - 按维度 / 平台切分
   - 趋势叠加线图

6. Action Plan 页面 /brands/{id}/actions
   - 任务列表（按优先级排序）
   - 筛选：状态 / 负责人 / 优先级
   - 每条任务展示：触发原因 → 具体行动 → 验收标准
   - 状态流转按钮

7. Content Library 页面 /brands/{id}/content
   - 按内容类型分组
   - 关联 Action Plan 任务
   - 内容状态（草稿 → 审核 → 已发布）
   - 效果验证结果（发布后对应指标变化）
```

## 16. 数据模型（完整版）

### 16.1 多租户基础表 [P0]

```
organizations
  id (PK, UUID)
  name
  plan: free | pro | enterprise
  created_at
  updated_at

users
  id (PK, UUID)
  organization_id (FK → organizations)
  email
  name
  role: admin | editor | viewer
  password_hash
  created_at
  updated_at

organization_members
  id (PK, UUID)
  organization_id (FK → organizations)
  user_id (FK → users)
  role: owner | admin | member
  created_at
```

### 16.2 品牌与事实库

```
brands
  id (PK, UUID)
  organization_id (FK → organizations)
  name (TEXT)                    -- 品牌官方名称
  aliases (TEXT[])               -- 别名列表
  industry (TEXT)                -- 行业
  ground_truth_version_id (FK → ground_truth_versions)  -- 当前活跃版本
  created_by (FK → users)
  updated_by (FK → users)
  created_at
  updated_at

ground_truth_versions
  id (PK, UUID)
  brand_id (FK → brands)
  version (INT)
  ground_truth_json (JSONB)      -- 完整 GT 字段
  source_urls (TEXT[])
  reviewer (TEXT)
  status: draft | active | deprecated
  created_at
  updated_at
```

### 16.3 问题模板与 Prompt 管理

```
query_templates
  id (PK, UUID)
  organization_id (FK → organizations)  -- NULL = 系统默认
  dimension (TEXT)               -- 定义认知/场景推荐/对比评价/信任验证/场景联想
  template_text (TEXT)           -- "{品牌} 是什么？"
  priority (INT)
  is_active (BOOL)
  created_by (FK → users)
  created_at

prompt_versions
  id (PK, UUID)
  name (TEXT)
  system_prompt (TEXT)
  template_rules (JSONB)         -- 变量替换规则
  version (INT)
  status: draft | active | deprecated
  created_at
  updated_at
```

### 16.4 采集结果 [P0 扩展]

```
query_results
  id (PK, UUID)
  brand_id (FK → brands)
  organization_id (FK → organizations)
  platform: deepseek | kimi | doubao | wenxin
  template_id (FK → query_templates)
  prompt_version_id (FK → prompt_versions)
  question (TEXT)                -- 最终提问文本
  system_prompt (TEXT)           -- 实际 system prompt 快照
  user_prompt (TEXT)             -- 模板渲染后的 user prompt
  request_payload_json (JSONB)   -- 完整请求体
  response_raw_json (JSONB)      -- 完整原始响应
  answer_text (TEXT)             -- 提取后的纯文本回答
  citations (JSONB)              -- [{url, type, context}]
  model_name (TEXT)
  model_version (TEXT)
  temperature (FLOAT)
  search_enabled (BOOL)
  status: success | timeout | rate_limited | error | empty
  error_code (TEXT)
  error_message (TEXT)
  latency_ms (INT)
  retry_count (INT)
  collected_at (TIMESTAMP)

  -- 索引
  INDEX (brand_id, collected_at)
  INDEX (platform, collected_at)
  INDEX (status)
```

### 16.5 指标快照

```
metrics_snapshots
  id (PK, UUID)
  brand_id (FK → brands)
  organization_id (FK → organizations)
  ground_truth_version_id (FK → ground_truth_versions)  -- 采集时的 GT 版本
  week_start (DATE)              -- 统计周起始日期
  platform (TEXT, NULL)          -- NULL = 全局，非 NULL = 单平台
  dimension (TEXT, NULL)         -- NULL = 全局，非 NULL = 单维度

  -- 5 大指标
  sov (FLOAT)                    -- 体感覆盖率 0-1
  first_rec_rate (FLOAT)         -- 首推率 0-1
  accuracy_rate (FLOAT)          -- 讲对率 0-1
  completeness_rate (FLOAT)      -- 认知完整度 0-1
  citation_rate (FLOAT)          -- 引用感知率 0-1

  sample_size (INT)              -- 有效样本数
  failure_rate (FLOAT)           -- 采集失败率

  details (JSONB)                -- 计算明细
  created_at
```

### 16.6 幻觉检测

```
hallucination_results
  id (PK, UUID)
  brand_id (FK → brands)
  query_result_id (FK → query_results)
  ground_truth_version_id (FK → ground_truth_versions)
  field_name (TEXT)              -- GT 字段名
  field_level: P0 | P1 | P2     -- 字段级别
  severity: P0 | P1 | P2        -- 错误严重等级
  verdict: correct | wrong | uncertain | not_mentioned
  ai_claim (TEXT)                -- AI 声称的内容（摘录）
  ground_truth_value (TEXT)      -- GT 中的正确值
  human_reviewed (BOOL)
  human_verdict (TEXT, NULL)     -- 人工复核修正
  reviewer_id (FK → users, NULL)
  reviewed_at (TIMESTAMP)
  detected_at (TIMESTAMP)
```

### 16.7 行动任务

```
action_plans
  id (PK, UUID)
  brand_id (FK → brands)
  organization_id (FK → organizations)
  trigger_type (TEXT)
  action_type (TEXT)
  priority: P0 | P1 | P2
  evidence_query_result_ids (UUID[])
  evidence_hallucination_ids (UUID[])
  ai_wrong_claims (JSONB)
  correct_ground_truth (JSONB)
  suggested_content_type (TEXT)
  target_page (TEXT)
  platform_target (TEXT)
  expected_metric_lift (JSONB)    -- {"metric": "accuracy_rate", "delta": 0.15}
  acceptance_criteria (TEXT)
  owner_id (FK → users)
  due_date (DATE)
  status: pending | in_progress | pending_review | completed
  review_notes (TEXT)
  created_at
  completed_at
  verified_at
```

### 16.8 内容库

```
content_library
  id (PK, UUID)
  brand_id (FK → brands)
  organization_id (FK → organizations)
  action_plan_id (FK → action_plans, NULL)
  content_type (TEXT)            -- FAQ / Q&A / Comparison / Tutorial / Case / Schema
  title (TEXT)
  body (TEXT)
  platform_target (TEXT)
  quality_check_passed (BOOL)    -- 内容质量守则审核
  status: draft | review | published
  published_url (TEXT, NULL)
  metric_impact (JSONB, NULL)     -- 发布后指标变化记录
  created_by (FK → users)
  created_at
  published_at
```

### 16.9 竞品管理

```
competitor_sets
  id (PK, UUID)
  brand_id (FK → brands)
  organization_id (FK → organizations)
  name (TEXT)
  competitor_brand_ids (UUID[])
  source_type: manual | auto_discovered | system_recommended
  version (INT)
  is_active (BOOL)
  created_at
  updated_at
```

### 16.10 API 用量与成本 [P1]

```
api_usage_logs
  id (PK, UUID)
  organization_id (FK → organizations)
  brand_id (FK → brands)
  platform (TEXT)
  query_result_id (FK → query_results)
  prompt_tokens (INT)
  completion_tokens (INT)
  cost (DECIMAL)                  -- 本次调用花费（元）
  status: success | failed
  created_at
```

## 17. 任务调度与成本控制 [P1]

### 17.1 采集量估算

```
单品牌单次全量采集 = 4 平台 × 22 问题 = 88 次 API 调用

每次调用预估 Token：
  输入（system + user prompt）≈ 500 tokens
  输出（AI 回答）≈ 800 tokens

单次全量 Token = 88 × (500 + 800) = 114,400 tokens
单品牌单次成本（DeepSeek V4-Flash）≈ ¥0.30
单品牌单次成本（4平台混合，保守估算）≈ ¥1.50

月度成本（4品牌，周度采集）≈ ¥1.50 × 4 × 4.3 ≈ ¥26
```

### 17.2 并发与限流策略

| 策略 | 配置 |
|---|---|
| 平台间并发 | 4 平台同时请求 |
| 平台内串行 | 同一平台 22 问题逐条发送，间隔 2s |
| 超时时间 | 单次 API 调用 30s 超时 |
| 最大重试 | 失败后重试 2 次，指数退避（1s, 4s, 16s） |
| 平台限流触发 | 收到 429 → 退避 60s 后恢复 |
| 月调用上限 | 单组织每月 10,000 次（≈ 113 品牌次），硬限制防超支 |

### 17.3 失败处理

```
单问题失败 → 重试 2 次 → 仍失败 → 标记 status=error → 继续下一问题
单平台整体失败 → 记录 → 下次采集周期自动补采
采集失败率 > 30% → 触发告警（日志 + Dashboard 红色标记）
```

### 17.4 告警

- 采集失败率 > 30%：Dashboard 告警标记
- API 余额不足：配置余额阈值，低于 ¥10 提示
- 连续 3 周采集失败率 > 50%：阻断自动采集，需人工介入

## 18. 权限、多租户与数据隔离 [P0]

### 18.1 设计原则

- 所有核心业务表带 `organization_id`，查询必须加该过滤条件。
- API 层通过 JWT token 解析 `organization_id`，注入到所有查询上下文。
- V1 内部使用时单组织模式，`organization_id` 硬编码，但代码层面不跳过隔离逻辑。
- SaaS 化时只需新增组织注册和切换逻辑，数据库不需要迁移。

### 18.2 权限矩阵

| 角色 | 查看数据 | 编辑品牌 | 执行采集 | 管理任务 | 系统配置 |
|---|---|---|---|---|---|
| admin (管理员) | ✅ | ✅ | ✅ | ✅ | ✅ |
| editor (编辑) | ✅ | ✅ | ✅ | ✅ | ❌ |
| viewer (只读) | ✅ | ❌ | ❌ | ❌ | ❌ |

### 18.3 数据隔离要求

```
每个 SQL 查询必须包含:
  WHERE organization_id = $current_org_id

例外: 
  - 系统级 prompt_versions (organization_id IS NULL) 所有组织可读
  - 系统级 query_templates (organization_id IS NULL) 所有组织可读
```

## 19. 合规、安全与内容质量守则 [P1]

### 19.1 数据安全

- API Key 存储：环境变量或 PostgreSQL 加密字段，不落地代码仓库。
- 用户密码：bcrypt 哈希存储。
- JWT Token：过期时间 24h，refresh token 7d。
- 采集的 AI 回答数据可能含敏感信息，Dashboard 访问需认证。

### 19.2 内容质量守则（与 §14.2 一致）

1. 内容必须基于真实产品能力和事实。
2. 对比内容必须有客观依据，标注比较维度和数据来源。
3. 案例内容必须可追溯。
4. 不得虚构客户、奖项、排名、市场地位。
5. Schema 结构化事实必须与页面正文一致。
6. 不得批量生成低质量、重复、关键词堆砌页面。
7. P0/P1 内容产出需人工审核后发布。

### 19.3 合规底线

- 不对 AI 平台进行任何形式的攻击、逆向或非授权访问。
- 不批量生成虚假正面评价或攻击竞品的负面内容。
- 采集频率遵循各平台的合理使用政策。
- 不冒充用户向 AI 平台发送诱导性提问。

## 20. 验证闭环与效果评估

```
行动执行完成 → 下次监测周期触发 → 指标前后对比:

  讲对率 P0 错误 2→0     ✅ Action Plan "定义纠正" 生效
  SOV 35% → 52%           ✅ 场景渗透策略有效 → 策略库沉淀
  首推率 40% → 42%        ⚠️ 边际改善，需追加权威建设
  引用率 5% → 18%         ✅ Schema 改造生效
  认知完整度 30% → 30%    ❌ 未改善 → 追加二轮任务

策略库沉淀条件：
  - 同类触发条件 + 同类行动 → 指标提升 > 阈值 → 标记"已验证有效策略"
  - 同类触发条件 → 指标未提升 → 标记"需追加方案"

阈值（V1 默认）：
  - SOV 提升 > 5pp → 有效
  - 首推率提升 > 5pp → 有效
  - 讲对率提升 > 10pp → 有效
  - 引用率提升 > 5pp → 有效
```

## 21. MVP 开发范围

### 必做 (MVP Core)

1. 品牌管理 + Ground Truth 录入与版本管理
2. 4 个 AI 平台 Adapter（DeepSeek、Kimi、豆包、文心）
3. 22 个标准问题模板 + 5 维度管理
4. 手动触发采集 + Celery Beat 周度调度
5. 5 大指标计算（SOV、首推率、讲对率、认知完整度、引用感知率）
6. 幻觉检测 + 人工复核入口
7. Prompt 版本管理 + 完整请求/响应落盘
8. 数据模型多租户预留（organization_id）
9. Dashboard 7 页面架构
10. Action Plan 可执行任务系统
11. Content Factory 基础版 + 质量守则
12. 指标快照与历史趋势
13. API 用量记录

### 暂缓

1. SaaS 付费套餐与计费
2. 自动内容发布到外部平台
3. 大规模行业 Benchmark
4. 自动发现新问题模板
5. 复杂 RBAC 权限体系（V1 仅 admin/editor/viewer）
6. PDF/PPTX 高级报告导出
7. 外部工具集成（飞书、Notion、Jira）

## 22. 后续商业化扩展 [P2]

| 能力 | 说明 |
|---|---|
| 行业 Benchmark | 同行业内多品牌横向比较，形成行业基准 |
| 指标波动归因 | 自动分析指标变化是由内容/竞品/模型/检索源哪类因素导致 |
| 自动发现问题模板 | 基于共现词、搜索意图、客服问题等自动生成新问题 |
| 内容 Brief 自动生成 | 基于 Action Plan 自动生成内容 Brief 而非直接内容 |
| 外部工具集成 | 飞书/Notion 同步任务，Jira/Linear 同步，CMS 发布 |
| 客户报告导出 | PDF/Markdown/HTML/PPTX 多格式 |
| 多语言支持 | 英文品牌 + 国际 AI 平台（ChatGPT、Gemini、Perplexity） |
