# GEO Explorer — 品牌AI可见度监测与优化系统

## 项目定位

内部使用的品牌AI可见度管理平台，监测品牌在多个AI引擎中的表现，提供可落地的优化行动方案。架构预留SaaS多租户扩展能力。

对标系统：[GEOAhead](https://geoahead.com/)（品牌AI可见度管理平台）

## 核心闭环

```
输入品牌/企业名称
    ↓
【监测层】向 4 个 AI 平台 → 系统性质询 → 采集 AI 回答
    ↓
【分析层】计算 4 大指标 → 检测幻觉 → 竞品对比
    ↓
【行动层】生成优化任务 → 内容工厂执行 → 下次监测验证效果
    ↓
循环迭代，持续提升 AI 可见度
```

## 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                    GEO Explorer                           │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
│  │DeepSeek  │  │  Kimi    │  │  豆包    │  │  文心    │ │
│  │ Adapter  │  │ Adapter  │  │ Adapter  │  │ Adapter  │ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘ │
│       └──────────────┴─────────────┴──────────────┘      │
│                          │                                │
│              ┌───────────▼───────────┐                    │
│              │    监测层 (Collector)  │                    │
│              │  问题模板 → 并发查询   │                    │
│              └───────────┬───────────┘                    │
│                          │                                │
│              ┌───────────▼───────────┐                    │
│              │    分析层 (Analyzer)   │                    │
│              │  SOV│首推率│讲对率│引用率│                  │
│              │    幻觉检测│竞品矩阵    │                    │
│              └───────────┬───────────┘                    │
│                          │                                │
│              ┌───────────▼───────────┐                    │
│              │   行动层 (Action Plan) │                    │
│              │  优先级引擎│内容工厂   │                    │
│              │  策略库│效果验证       │                    │
│              └───────────┬───────────┘                    │
│                          │                                │
│              ┌───────────▼───────────┐                    │
│              │     Web Dashboard      │                    │
│              │  指标看板│报告│品牌管理 │                    │
│              └───────────────────────┘                    │
│                                                           │
│  PostgreSQL │ Redis │ Celery │ FastAPI │ Jinja2+HTMX      │
└─────────────────────────────────────────────────────────┘
```

## 技术选型

| 层 | 技术 | 原因 |
|---|---|---|
| 后端框架 | FastAPI (Python 3.12) | 异步原生，对接 4 个 AI API 并发 |
| 任务队列 | Celery + Redis | 周期采集 + 分析计算的调度 |
| 数据库 | PostgreSQL 16 | JSONB 存 Ground Truth 和指标明细 |
| 前端 | Jinja2 + HTMX | V1 快速验证，不做 SPA |
| 部署 | Docker Compose | 一键 docker compose up |

## AI 平台接入方案

V1 覆盖 4 个国内 AI 平台：

| 平台 | 接入方式 | Base URL | 鉴权 |
|---|---|---|---|
| DeepSeek | OpenAI SDK 兼容 | api.deepseek.com | API Key |
| Kimi (Moonshot) | OpenAI SDK 兼容 | api.moonshot.cn/v1 | API Key |
| 豆包 (字节) | volcenginesdkarkruntime | ark.cn-beijing.volces.com/api/v3 | API Key |
| 文心 (百度) | 千帆 V2 (OpenAI兼容) | 千帆 endpoint | API Key + Secret Key |

每个平台封装为独立 Adapter，统一接口：

```python
class PlatformAdapter(ABC):
    async def query(prompt: str) -> AIResponse
    async def extract_citations(response: str) -> list[str]
    async def detect_hallucination(response: str, ground_truth: dict) -> HallucinationReport
```

## 一、监测层

### 问题模板引擎

5 个维度 × 22 个标准问题模板：

| 维度 | 问题数 | 目的 | 示例 |
|---|---|---|---|
| 定义认知 | 4 | AI 的基本定义是否准确 | "{品牌} 是什么？" / "{品牌} 属于什么行业？" |
| 场景推荐 | 5 | 是否出现在推荐列表，排第几 | "最好用的{行业}工具有哪些？" |
| 对比评价 | 4 | AI 如何看待与竞品的差异 | "{品牌} 和 {竞品} 的区别？" |
| 信任验证 | 4 | 犹豫型问题中 AI 如何描述 | "{品牌} 靠谱吗？" / "{品牌} 用户口碑？" |
| 场景联想 | 5 | 场景描述时 AI 是否自然联想到品牌 | "想做跨境电商，用什么工具？" |

### 采集频率

- 默认：每周一次（Celery Beat，周一凌晨）
- 手动触发：品牌首次添加时立即全量采集
- 单次采集：4 平台 × 22 问题 × N 品牌，并发执行

## 二、分析层

### 指标一：体感覆盖率 SOV

```
SOV = (品牌被提及的 AI 回答数 / 总查询回答数) × 100%
维度：全局 SOV / 单平台 SOV / 单维度 SOV
```

### 指标二：首推率

```
首推率 = (品牌在推荐类问题中排第一的次数 / 推荐类问题总数) × 100%
判定：有序列表序号提取 + LLM 辅助段落首推位置判断
```

### 指标三：讲对率

校验 AI 是否形成了关于品牌稳定的语义锚点。8 字段分 3 级：

| 级别 | 字段 | 说明 |
|---|---|---|
| P0 身份锚点 | 行业归属、核心定位、产品/服务类型 | AI 能否在相关场景想到你 |
| P1 推荐依据 | 差异化优势、目标用户群、核心使用场景 | AI 推荐对比时直接引用 |
| P2 认知丰富度 | 技术/能力标签、行业阶段/市场地位 | 语义绑定的宽度和深度 |

计算：`讲对率 = (正确描述字段数 / AI 提及字段总数) × 100%`

### 指标四：引用感知率

```
引用感知率 = (AI 回答中明确引用品牌官网的次数 / 品牌被提及的上下文数) × 100%
判定：URL 匹配 + 中文引用句式识别
```

### 幻觉检测

```
AI 回答 → 实体提取 → 与 Ground Truth 比对 → 标记 ✅正确 / ❌错误 / ⚠️存疑
输出 Hallucination Report：错误项、严重等级(P0/P1/P2)、跨平台分布
```

### 竞品矩阵

按品牌 × 指标 × 时间维度做横切对比。

## 三、行动层

### Action Plan — 触发到行动的映射

| 触发条件 | 行动类型 | 示例 |
|---|---|---|
| P0 身份锚点错误 | 定义纠正 | 核心页面重写定位描述 |
| SOV 落后竞品 | 场景渗透 | 列出缺失的场景问题，逐个覆盖 |
| 首推率低 | 权威建设 | 行业文章 + 第三方评测 + FAQ |
| 引用率低 | 官网结构化 | Schema JSON-LD 标记 |
| 某维度完全缺失 | 内容新造 | 对比类内容从零创建 |

元数据：优先级(P0/P1/P2，从分析层继承)、行动类型、目标平台、状态流转(待执行→执行中→待验证→已完成)。

### Content Factory — 6 类 AI 优化内容

| # | 类型 | 格式 | AI 目的 |
|---|---|---|---|
| 1 | 结构化定义 | FAQ / Glossary | 无歧义的品牌定义锚点 |
| 2 | 场景问题库 | Q&A 矩阵 | 覆盖用户场景问题，嵌入品牌 |
| 3 | 对比清单 | Comparison Table | 对比类问题中占据格式优势 |
| 4 | 行业知识 | Tutorial / Guide | 成为领域知识源 |
| 5 | 信任信号 | Case Study / Review | 多源一致性的核心载体 |
| 6 | 结构化元数据 | Schema / JSON-LD | AI 直接解析品牌事实 |

### 验证闭环

```
行动执行 → 下次监测 → 指标前后对比 → 有效策略沉淀 / 无效追加二轮
```

## 数据模型（V1 核心表）

```
brands
  id, name, aliases[], industry, ground_truth(JSONB)
  competitors[], created_at, updated_at

query_templates
  id, dimension, template_text, priority, is_active

query_results
  id, brand_id, platform, template_id
  question, answer_text, citations[], model_version
  collected_at

metrics_snapshots
  id, brand_id, week_start, platform(null=global)
  sov, first_rec_rate, accuracy_rate, citation_rate
  details(JSONB)

hallucination_results
  id, brand_id, query_result_id
  field_name, severity(P0/P1/P2), verdict(正确/错误/存疑)
  ai_claim, ground_truth, detected_at

action_plans
  id, brand_id, trigger_type, action_type
  priority(P0/P1/P2), content_template
  status, created_at, completed_at, verified_at

content_library
  id, brand_id, action_plan_id
  content_type, title, body, platform_target
  status, created_at
```
