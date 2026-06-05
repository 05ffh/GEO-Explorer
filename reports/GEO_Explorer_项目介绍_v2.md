# GEO Explorer — 品牌 AI 可见度监测与优化平台

> **项目介绍文档 v2 | 生成时间: 2026-06-03 | 版本: P2 全完成 + ClaimNature v2**

---

## 一、项目概述

### 1.1 GEO Explorer 是什么

GEO Explorer 是一套**品牌 AI 认知资产管理平台**，系统性地监测、诊断并优化品牌在 AI 平台（DeepSeek、Kimi、豆包等）中的可见度和认知准确度。

它的核心命题是：**当用户向 AI 询问关于你的品牌、行业、产品的问题时，AI 回答正确吗？完整吗？有竞争力吗？**

**一句话概括：让你的品牌在 AI 眼中是正确、完整、有竞争力的。**

### 1.2 解决的核心问题

| 问题 | 具体表现 | GEO Explorer 的应对 |
|------|---------|-------------------|
| **品牌"黑盒"** | 你不知道 AI 怎么说你的品牌——有没有被提及？描述准确吗？ | 多平台系统性质询，量化 10 个 KPI |
| **AI"幻觉"** | AI 编造品牌信息（如总部地点、营收数据），误导消费者决策 | 4 层幻觉检测 + GT 核验 + 声明性质分类 |
| **认知"碎片化"** | 不同 AI 平台对同一品牌的描述互相矛盾 | 跨平台一致性监测 + 证据来源追溯 |
| **修复"无闭环"** | 发布纠正内容后不知道 AI 是否已更新认知 | 历史重归因 + Content Package + 人审反馈闭环 |
| **竞争"缺对标"** | 不知道竞品在 AI 中的表现如何 | 竞品对比 + 行业 KPI 基准 + 品牌差异化分析 |

### 1.3 适用对象

- **品牌方**：市场部/数字营销团队，监测品牌 AI 形象
- **代理机构**：为多个客户提供 GEO 诊断和优化服务（多租户架构）
- **平台运营**：监测 AI 平台的内容质量，识别系统性偏见
- **覆盖行业**：餐饮零售、金融保险、医疗健康、教育培训、SaaS、汽车、文旅等 11 个行业

---

## 二、系统架构

### 2.1 技术栈

| 层级 | 技术选型 | 说明 |
|------|---------|------|
| 语言 | Python 3.12 | 全异步 (async/await)，类型标注 |
| Web 框架 | FastAPI 0.136 | REST API + Jinja2 模板 + HTMX 2.0 |
| ORM + 迁移 | SQLAlchemy 2.0 async + Alembic | 异步查询，JSONB 支持，29 个迁移 |
| 数据库 | PostgreSQL 16 (Docker) | 主库 5432 + 测试库 5433 |
| 任务队列 | Celery + Redis 7 | 异步采集，长任务不阻塞 HTTP |
| 前端 | Jinja2 + HTMX + Chart.js 4.4 + Tailwind CDN | 42 个模板，真实后端集成 |
| AI 平台 | DeepSeek / Kimi / 豆包 / 文心 | 统一 OpenAI-compatible 适配器 |
| 报告输出 | Puppeteer + marked + python-docx | 三格式：Markdown + Word + PDF |
| 部署 | Systemd 守护进程 | geo-redis / geo-celery / geo-api |

### 2.2 项目规模

| 维度 | 数量 |
|------|------|
| Python 源文件 | 210+ |
| Jinja2 模板 | 42 |
| 数据库表 | 81 |
| Alembic 迁移 | 29 |
| 测试用例 | 613 (0 failures) |
| GitHub | https://github.com/05ffh/GEO-Explorer |

### 2.3 目录结构

```
explore geo/
├── src/
│   ├── models/          # 81 张数据表的 ORM 模型
│   ├── adapters/        # AI 平台适配器 (DeepSeek/Kimi/豆包/文心)
│   ├── collector/       # 采集引擎 + GT 自动采集
│   ├── analyzer/        # 10 KPI 计算 + 幻觉检测 + ClaimNature 分类
│   ├── actions/         # Action 引擎 + Content Package 生成
│   ├── api/             # REST API 端点 (20+ endpoint)
│   ├── services/        # 业务服务 (证据验证/人审反馈/模板校验/样本充分度)
│   ├── reports/         # 报告生成 + PDF/DOCX 导出
│   ├── schemas/         # GT v2 字段定义 + 行业配置 + 字段注册表
│   ├── view_models/     # 前端视图模型
│   ├── templates/       # 42 个 Jinja2 模板 (含 14 个 partial 组件)
│   ├── auth/            # JWT 认证 + 双层角色权限
│   ├── publishing/      # CMS 发布适配器
│   ├── queue/           # 任务队列监控
│   ├── benchmark/       # 性能基准测试
│   ├── seed/            # 种子数据 (行业模板/风险关键词)
│   └── infra/           # 基础设施 (缓存/限流/重试)
├── tests/               # 57 个测试文件, 613 tests
│   ├── fixtures/claim_taxonomy/  # ClaimNature 中文黄金样本集
│   └── regression/               # 回归测试
├── alembic/             # 29 个数据库迁移
├── deploy/              # systemd 服务文件
├── docs/superpowers/    # 设计规范 + 实现计划
└── reports/             # 品牌诊断报告输出
```

---

## 三、完整业务链路 — GEO 诊断的 7 个环节

```
┌──────────────────────────────────────────────────────────────────────────┐
│                     GEO Explorer 完整业务链路                              │
│                                                                          │
│  [1.GT采集] → [2.GT审核] → [3.品牌采集] → [4.幻觉检测+KPI]               │
│      ↓                            ↓                                     │
│  S/A/B/C/D来源分级        22模板×4平台=88次AI调用                         │
│      ↓                            ↓                                     │
│  自动证据聚合              4层幻觉+ClaimNature分类                        │
│      ↓                            ↓                                     │
│  [2.GT审核]                [5.多证据GT验证]                                │
│  Promote→Active GT         加权共识+冲突分级                              │
│      ↓                            ↓                                     │
│  [3.品牌采集]              [6.Action Themes+Content Package]              │
│                              LLM生成+Facts Check                          │
│                                     ↓                                    │
│                            [7.报告交付+人审闭环]                            │
│                              md/docx/pdf + feedback→校准                   │
└──────────────────────────────────────────────────────────────────────────┘
```

---

### 环节 1：GT 采集（Ground Truth — 品牌"事实档案"）

**目的**：建立品牌的可信事实基准，作为后续所有 KPI 计算和幻觉检测的依据。

**流程**：
1. 用户输入品牌名称 → 系统向多个 AI 平台发送预设查询（如"{{品牌}} 总部位于哪里""{{品牌}} 成立于哪一年"）
2. 同时通过 DuckDuckGo 搜索补充公开信息
3. 字段级证据聚合：每个 GT 字段（如 official_name、founded_year、store_count）独立评分
4. 生成 GroundTruthCandidate（候选事实），包含每个字段的值、置信度、证据来源

**来源等级体系**：
| 等级 | 含义 | 权重 | 示例 |
|------|------|------|------|
| S | 官方一手来源 | 5 | 品牌官网、年报、官方公告 |
| A | 权威第三方来源 | 4 | 政府备案、行业监管文件、权威媒体 |
| B | 可信媒体/专业机构 | 3 | 知名媒体、研究机构报告 |
| C | 普通网页/百科/二手 | 2 | Wikipedia、普通资讯站 |
| D | 未验证线索 | 1 | 论坛、社交媒体、AI 推测 |

**为什么重要**：GT 是整个系统的基石。如果 GT 不准确，所有 KPI 计算和幻觉判定都不可信。

---

### 环节 2：GT 审核（人工 + 证据双重阻断）

**目的**：确保 GT 的准确性——AI 采集的结果必须经过人工确认才能用于 KPI 计算。

**流程**：
1. 审核工作台展示每个 GT 字段的候选值和多条证据来源
2. 人工逐字段审核：接受 / 编辑 / 删除 / 标记不确定
3. 高风险字段（official_name、industry、category 等）强制确认
4. 冲突检测：同一字段不同来源给出不同值 → 标记需人工裁定
5. 审核通过 → Promote 为 active GroundTruthVersion（正式 GT）
6. 旧版本自动标记为 superseded，保留完整历史

**v2 增强**：
- 字段类型标签（string / list / number / object）
- 单字段内联编辑 UI
- 来源 tier 徽标（S/A/B/C/D）直观展示证据质量

---

### 环节 3：品牌 GEO 采集（系统性 AI 质询）

**目的**：了解 AI 平台在当前状态下如何描述目标品牌。

**流程**：
1. 使用 **22 个标准查询模板** 覆盖 8 种问题类型：
   - 品牌定义（"{{品牌}} 是什么"）
   - 品牌属性（"{{品牌}} 的核心特点"）
   - 品牌对比（"{{品牌A}} 和 {{品牌B}} 哪个更好"）
   - 品牌信任（"{{品牌}} 靠谱吗"）
   - 品类推荐（"推荐几个咖啡品牌"）
   - 场景方案（"上班困了喝什么咖啡"）
   - 用户推荐（"你推荐星巴克吗"）
   - 通用建议（"如何选择咖啡品牌"）
2. 向 **4 个 AI 平台**（DeepSeek/Kimi/豆包/文心）并发发送查询
3. 采集 AI 的完整回复，记录延迟、引用来源、渲染状态
4. 模板健康前置检查：无效模板 >20% 则阻断采集

**模板版本化**：模板修改后自动生成新版本，正在进行的采集不受影响，支持历史版本查看和回滚。

---

### 环节 4：幻觉检测 + KPI 计算（引擎核心）

**目的**：量化品牌 AI 认知质量，检测 AI 对品牌的错误表述。

#### 4.1 幻觉检测（4 层架构）

**第 1 层 — 声明提取**：
从 AI 回复中提取品牌相关的事实性声明片段。例如："星巴克总部位于西雅图" → 提取声明 `总部=西雅图`，匹配 GT 字段 `headquarters`。

**第 2 层 — 声明性质分类（ClaimNature v2）**：
每条声明标注认知性质：
| 分类 | 含义 | 处理方式 |
|------|------|---------|
| **FACT** | 可验证的客观事实 | 进入事实准确率校验，与 GT 对比 |
| **OPINION** | 主观评价/判断 | 不进入事实准确率分母，标注观点倾向 |
| **SPECULATION** | 前瞻性/未证实推测 | 独立风险评级，不等于幻觉 |
| **UNKNOWN** | 无法判定 | 进入人审队列 |

分类器采用**加权评分制**：强信号 +2 分、弱信号 +1 分、数字/结构模式 +1 分，冲突阈值 1.3x → UNKNOWN。否定窗口检测（信号词前后 5 字符）、n-gram 回退匹配、行业高风险词库（金融/医疗/教育）。

**评估指标**（100 样本中文黄金集）：准确率 77.0%，UNKNOWN 率 20.0%，推测召回 85.7%，事实精确 86.0%。

**第 3 层 — 事实核验（n-gram + LLM-as-Judge）**：
- 声明与 GT 进行分词模糊匹配（n-gram overlap）
- 边界案例（相似度 0.05-0.35）由 LLM-as-Judge 二次判定
- Severity 输出：P0（严重错误）、P1（重要偏差）、P2（细微差异）、Info（非错误）
- Verdict 输出：supported / contradicted / unsupported / not_checkable / ambiguous 等 9 种判定

**第 4 层 — 多证据 GT 交叉验证（P2-2）**：
- 同一字段的多条 GT 证据加权共识（S=5/A=4/B=3/C=2/D=1 + 官方来源 ×1.2）
- 冲突分级：none / weak / moderate / strong / critical
- 证据冲突不等于 AI 幻觉——来源间争议单独标注，不计入幻觉计数
- 证据强度：strong / moderate / weak / disputed / insufficient_evidence

#### 4.2 10 个核心 KPI

| KPI | 中文名 | 计算逻辑 |
|-----|--------|---------|
| **SOV** | 声量份额 | 品牌在 AI 回复中被提及的频率 / 总查询数 |
| **First Recommendation Rate** | 首次推荐率 | 非品牌场景问题中首个被推荐的比率 |
| **Accuracy** | 事实准确率 | AI 品牌声明与 GT 一致的比例（仅 FACTS 进入分母） |
| **Completeness** | 信息完备性 | GT 关键字段在 AI 回复中的覆盖率 |
| **Citation Rate** | 来源引用率 | AI 回复中引用官方来源的比率 |
| **Scenario Recall** | 场景联想率 | 非品牌场景词下品牌被提及的比例 |
| **Semantic Stability** | 语义锚点稳定度 | 不同平台对品牌核心描述的相似度 |
| **Differentiation** | 差异化程度 | 品牌独特卖点在 AI 表述中的出现率 |
| **Cross-Platform Consistency** | 跨平台一致性 | 品牌关键声明的跨平台稳定性 |
| **Recommendation Quality** | 推荐理由质量 | AI 推荐理由的实质性和准确度 |

每个 KPI 包含：数值、样本量（denominator）、置信度、按平台/问题类型的分维数据。

---

### 环节 5：Action Themes + Content Package（从诊断到修复）

**目的**：诊断发现问题后，自动生成修复方案。

#### 5.1 Action Theme 聚合
- 将幻觉结果按字段维度聚合为 Action Theme（如 official_name / industry / category）
- 每个 Theme 包含：影响的 AI 声明列表、GT 正确值、建议纠正内容
- P0/P1/P2 优先级分级，生成状态机看板（pending → in_progress → completed → verified）

#### 5.2 Content Package 生成
- 基于 Action Themes 按内容主题聚类
- **LLM（DeepSeek）生成完整可发布内容**：
  - 品牌介绍（结构化事实描述）
  - FAQ（常见问题 + 基于 GT 的标准答案）
  - 场景推荐（品牌适用场景）
  - 竞品对比（与竞品的主要差异）
- 每个 Package 包含：风险分级、事实检查标注、发布检查清单、Schema.org JSON-LD

---

### 环节 6：报告交付

**三格式输出**（缺一不可）：
| 格式 | 用途 | 工具 |
|------|------|------|
| `.md` | 技术审阅、版本控制 | marked |
| `.docx` | 企业汇报、协作编辑 | python-docx |
| `.pdf` | 正式交付、演示分发 | Puppeteer + marked |

**报告内容**：诊断摘要 + 10 KPI 仪表板 + 幻觉详情（P0/P1/P2 分级） + 声明性质分布 + 证据强度分析 + 行业高风险检查 + Action Theme 清单 + 优化建议 + Go/No-Go 发布判定。

**报告质量闸门**：
- 8 个硬阻断条件（如模板健康度 <60%、核心 KPI 分母为 0）
- 声明性质阻断：推测占比 >50% / UNKNOWN 占比过高
- 证据强度阻断：关键字段 A/S 级来源冲突 / 弱证据占比 >60%
- 4 个软警告（如可选模板跳过、单平台覆盖率 <50%）

---

### 环节 7：人审闭环 + 持续优化

**目的**：分类器不可能一次完美，必须接入人工审核形成持续改进飞轮。

**审核流**：
```
needs_human_review → pending → claimed → completed / skipped
                                                    ↓
                                          GT更新建议 / 模板修正 / 检测器校准
                                                    ↓
                                          ReviewFeedbackItem 落库
```

**3 类反馈动作**：
1. **GT 修正**：人工判 contradicted 且有修正值 → 生成 GTUpdateCandidate → GT reviewer 二次审核（不自动修改 GT）
2. **模板优化**：同一 pattern 反复出现 → 标记模板需调整
3. **检测器校准**：误报/漏报模式 → 导出校准样本供分类器改进

**审计追溯**：HallucinationReviewLog 为 append-only 不可变审计日志，记录每次审核的完整 before/after snapshot（verdict / severity / claim_nature / evidence_strength）。

---

## 四、辅助模块

### 4.1 模板审核工作台（P2-3）

- 状态机：draft → in_review → active / changes_requested → archived
- 变量/类型/行业/KPI 全校验（TemplateValidationService）
- 渲染预览（示例值替换，发布前必须通过校验）
- 版本历史 + 回滚 + 克隆
- KPI 矩阵：8 种 question_type × 5 KPI 的 recommended / allowed / blocked

### 4.2 行业差异化配置（P1-9）

每个行业独立配置：
- KPI 权重（金融行业 accuracy 权重更高，SaaS 行业 scenario_recall 权重更高）
- 幻觉阈值（金融/医疗行业 stricter）
- 声明性质阈值（UNKNOWN 上限、推测阻断阈值）
- 受监管行业模式（max_unknown_ratio=0.10 vs 默认 0.20）
- 行业高风险词库（金融：保本/刚兑/无风险；医疗：治愈/根治/无副作用；教育：保过/包就业）

### 4.3 历史重归因（P1-8）

- 检测器升级后，对历史数据重新运行检测
- original vs corrected 双视图，不覆盖原始结果
- 重归因批次状态：draft → in_progress → completed / cancelled
- dry_run 模式：完整计算但不写入业务结果

### 4.4 前端操作台（完整后端集成）

| 页面 | 功能 |
|------|------|
| **品牌总览 Dashboard** | 10 KPI + GT 统计 + 采集状态 |
| **GT 审核** | 字段审核 + 证据展示 + 内联编辑 + Promote |
| **AI 证据** | 声明核验链 + 证据强度 + 来源追溯 + 冲突展示 |
| **幻觉风险** | 幻觉结果列表 + 审核队列 + 人审工作台 |
| **Action 工作台** | Kanban 5 列看板 + ActionPlan 表格 + 状态流转 |
| **趋势归因** | Chart.js 双面板 + HTMX 范围切换 + 事件时间线 |
| **Content 管理** | 内容包列表 + 状态分布 + 风险徽标 + 发布操作 |
| **模板管理** | 模板列表 + 编辑器 + 校验报告 + 版本历史 |
| **报告下载** | 历史报告列表 + 三格式下载 |
| **队列监控** | Celery 任务状态 |
| **组织设置** | 多租户管理 |

---

## 五、系统的价值

### 5.1 对品牌的直接价值

1. **消除 AI 黑盒**：首次让你看到 AI 如何描述你的品牌，量化了原本不可见的"认知资产"
2. **发现并修复幻觉**：AI 编造的品牌信息可能影响消费者决策——GEO Explorer 让你在客户看到之前先发现并修复
3. **竞品对标**：知道竞品在 AI 中的表现，发现差异化机会
4. **持续监测**：不是一次性诊断，而是持续监测 + 闭环优化

### 5.2 技术架构价值

1. **GT 三层模型**：Candidate → Review → Version，AI 采集结果不直接用于 KPI 计算，必须人工确认
2. **OPINION ≠ 幻觉，SPECULATION ≠ 幻觉**：不会因为 AI 说"星巴克最好喝"就标记为事实错误——声明性质分类是这个判断的基础
3. **证据冲突 ≠ AI 幻觉**：GT 来源间争议单独标注，不混淆"来源不确定"和"AI 说错"
4. **声明级 traceability**：每条 AI 声明可以追溯到 GT 来源、证据等级、审核历史
5. **异步任务架构**：品牌采集（88 次 AI 调用）和 GT 采集（30+ 次 AI 调用）异步执行，API 立即返回 202

### 5.3 工程方法价值

1. **Define → Plan → Build → Verify → Review → Ship**：6 阶段工程师模式，不跳步
2. **Spec → 桌面审阅 → 补齐清单 → Build → 有效性验证**：需求对齐机制，避免方向性返工
3. **613 tests, 0 failures**：核心逻辑由测试护卫，重构有底气
4. **完整踩坑记录 + Retrospective**：知识沉淀，跨会话可复用

---

## 六、当前局限与不足之处

### 6.1 数据采集层

| 问题 | 影响 | 优先级 |
|------|------|--------|
| **Wenxin API Key 过期** | 4 个 AI 平台中仅 3 个可用（DeepSeek/Kimi/豆包），文心 0/23 全失败 | 🔴 高 |
| **Doubao/Kimi 限流严重** | 采集成功率低（Doubao 3/23, Kimi 5/23），需间隔 >30min | 🔴 高 |
| **GT 来源以 C 级为主** | 证据强度普遍 weak，依赖 AI 采集和搜索结果，缺少 S/A/B 级官方来源 | 🔴 高 |
| **DeepSeek 是唯一稳定平台** | 22/23 成功率，但单平台依赖有风险 | 🟡 中 |

### 6.2 检测与分类

| 问题 | 影响 | 优先级 |
|------|------|--------|
| **OPINION recall 偏低 (43.5%)** | 部分观点声明因信号词不匹配被归为 UNKNOWN | 🟡 中 |
| **UNKNOWN precision 偏低 (30%)** | 14 个 fp—— 部分事实/观点被误归为 UNKNOWN | 🟡 中 |
| **英文分类未独立评估** | 当前验证集仅中文，英文分类精度未知 | 🟢 低 |

### 6.3 部署与运维

| 问题 | 影响 |
|------|------|
| **无 Docker Compose 一键部署** | 当前需手动配置 PostgreSQL Docker + Redis systemd + Celery + API 四个服务 |
| **无 CI/CD** | 没有自动化测试流水线，依赖手动 pytest |
| **无监控告警** | API/采集异常无自动通知 |

### 6.4 业务覆盖

| 问题 | 影响 |
|------|------|
| **尚未覆盖 Google AI Overview / SGE** | 搜索引擎 AI 摘要（如 Google SGE）是重要的 GEO 场景但尚未接入 |
| **尚未接入社交媒体 AI** | 小红书/抖音的 AI 搜索和推荐场景未覆盖 |
| **Content Package 仅 DeepSeek 生成** | Kimi/Doubao 因 failover 设计不参与内容生成（与采集的多平台并发不同） |

---

## 七、如何运行

### 7.1 环境要求

- Python 3.12 + .venv
- PostgreSQL 16（Docker 容器 `exploregeo-db-1`，端口 5432）
- Redis 7（systemd 服务 `geo-redis`，端口 6379）
- Node.js 22（PDF 生成用 Puppeteer）

### 7.2 启动

```bash
# 启动数据库和 Redis
docker start exploregeo-db-1 exploregeo-test_db-1
sudo systemctl start geo-redis geo-celery geo-api

# 访问
open http://localhost:8000/login
# 一键登录: test@geo.com / test123
```

### 7.3 运行诊断

```bash
# 创建品牌
curl -X POST http://localhost:8000/api/brands \
  -H "Authorization: Bearer <token>" \
  -d '{"name":"你的品牌","industry":"餐饮"}'

# 触发 GT 自动采集（异步）
curl -X POST http://localhost:8000/api/brands/{brand_id}/gt-collect

# 等待完成后，审核 GT → Promote

# 触发 GEO 诊断采集（异步）
curl -X POST http://localhost:8000/api/brands/{brand_id}/collections

# 查看 Dashboard → 审核幻觉 → 生成报告
```

---

## 八、文件索引

| 文件/目录 | 说明 |
|-----------|------|
| `src/analyzer/claim_taxonomy.py` | ClaimNature v2 分类器（评分+否定窗口+n-gram+行业词库） |
| `src/analyzer/hallucination.py` | 4 层幻觉检测 + ClaimNature 集成 |
| `src/analyzer/quality.py` | 报告质量闸门（8 hard blocks + 4 soft warnings） |
| `src/analyzer/pipeline.py` | 分析管线（KPI→幻觉→Action→Content→报告） |
| `src/collector/engine.py` | 品牌采集引擎（异步+限流+重试） |
| `src/services/evidence_cross_validator.py` | 多证据 GT 交叉验证 |
| `src/services/review_feedback_service.py` | 人审反馈闭环 |
| `src/services/template_validation_service.py` | 模板校验 |
| `src/api/ground_truth.py` | GT 审核 + Promote + 单字段编辑 API |
| `src/api/hallucinations.py` | 幻觉结果 + 审核队列 API (13 endpoints) |
| `src/api/templates.py` | 模板 CRUD + 校验 + 预览 API (11 endpoints) |
| `src/reports/delivery.py` | 统一报告交付（三格式） |
| `src/templates/gt_review/index.html` | GT 审核工作台 v2 |
| `src/templates/hallucinations/index.html` | 幻觉审核工作台 |
| `tests/fixtures/claim_taxonomy/zh_claim_nature_golden.jsonl` | 100 样本中文黄金集 |
| `tests/test_claim_taxonomy_eval.py` | ClaimNature 评估脚本（per-class metrics） |

---

*GEO Explorer v2 | 2026-06-03 | 210+ 源文件 | 42 模板 | 81 数据表 | 29 迁移 | 613 tests (0 failures)*
