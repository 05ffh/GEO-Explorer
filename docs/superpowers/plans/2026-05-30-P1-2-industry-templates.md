# P1-2 行业模板体系 实现计划 v2.1

**日期:** 2026-05-30 | **状态:** Plan | **审阅:** 已通过三轮专家评审
**当前完成度:** 0%

---

## 一、目标

为 15 个高价值行业建立 GEO 诊断模板体系，让系统能根据不同行业判断：什么事实最重要、什么错误最危险、什么竞品最相关、什么内容最能修复 AI 认知。

核心原则：行业模板不只是配置表，而是系统面向不同行业交付专业诊断的核心资产。

---

## 二、15 个行业模块

**阶段一：核心 8 个**

| # | 行业 | slug |
|---|------|------|
| 1 | 金融服务 | finance |
| 2 | 餐饮与食品饮料 | fnb |
| 3 | SaaS 与企业服务 | saas_b2b |
| 4 | 新能源汽车与智能出行 | ev_mobility |
| 5 | 消费电子与智能硬件 | consumer_electronics |
| 6 | 医疗健康与医药 | healthcare_pharma |
| 7 | 教育培训与知识服务 | education |
| 8 | 电商零售与消费品牌 | ecommerce_retail |

**阶段二：扩展 7 个**

| # | 行业 | slug |
|---|------|------|
| 9 | 文旅酒店与本地生活 | travel_hospitality |
| 10 | 房地产与家居建材 | real_estate_home |
| 11 | 工业制造与 B2B 供应链 | industrial_b2b |
| 12 | 物流供应链与跨境贸易 | logistics_crossborder |
| 13 | AI / 云计算 / 开发者工具 | ai_cloud_devtools |
| 14 | 美妆个护与时尚生活 | beauty_fashion |
| 15 | 政府公共服务与城市品牌 | public_sector_city |

**兜底模板：** general / unknown / hybrid

---

## 三、数据模型

### IndustryTemplate

```python
class IndustryTemplate(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "industry_templates"
    name, slug, description: str
    parent_id: uuid | None               # 层级继承
    level: str                            # domain / category / subcategory
    domain, category, subcategory: str
    version: str (default="1.0")
    status: str (draft/active/deprecated)
    region: str (CN/SG/US/Global)
    locale: str (zh-CN/en-US)
    business_model_tags: list             # platform/subscription/offline_chain/...
    # GT
    required_gt_fields, optional_gt_fields, high_risk_gt_fields: list
    industry_specific_fields, field_evidence_requirements, gt_field_weights: dict
    # KPI
    kpi_weights: dict                     # sum=1
    # 竞品
    competitor_rules: dict                # direct/substitute/category_peer/price_band/...
    # 风险
    risk_rules: list                      # [{term,risk_level,risk_type,match_type,applies_to,action}]
    compliance_constraints: dict          # {forbidden_claims,required_disclaimers,source_required_rules,...}
    # Action & Content
    action_rules, content_templates, review_rules: dict
    # 审计
    created_by, updated_by: uuid | None
    change_log: list
```

### IndustryQueryTemplate（独立模型）

```python
class IndustryQueryTemplate(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "industry_query_templates"
    industry_template_id: uuid
    dimension, intent: str
    question_text: str                    # "{brand} 是否有正规金融牌照？"
    uses_brand_name: bool
    target_kpis, target_gt_fields: list
    risk_level: str (P0/P1/P2)
    weight: float
    enabled: bool
```

### Brand 扩展

```python
primary_industry_template_id: uuid | None
secondary_industry_template_ids: list
industry_template_version: str | None
industry_template_changed_at: datetime | None
industry_template_changed_by: uuid | None
industry_template_change_reason: str
```

---

## 四、实现任务（9 个）

### Task 1: 行业模型 + Migration

创建 IndustryTemplate + IndustryQueryTemplate 模型，Brand 扩展，运行 migration。

### Task 2: 风险与合规规则结构化

risk_keywords → risk_rules（含 risk_type 枚举：financial_return_claim/medical_claim/education_outcome_claim/...）。compliance_constraints 拆为 5 类：forbidden_claims/required_disclaimers/source_required_rules/review_required_rules/content_generation_constraints。

### Task 3: 竞品规则分层

competitor_rules 拆为：direct/substitute/category_peer/price_band/scenario_peer/region_peer/wrong_competitor_types。

### Task 4: 行业问题库

每行业 >=12 个 IndustryQueryTemplate，每条绑定 dimension/intent/target_kpis/target_gt_fields/risk_level。

### Task 5: 种子数据（分阶段）

阶段一：核心 8 行业完整种子数据；阶段二：扩展 7 行业 + 3 兜底模板。每行业满足：>=10 required_gt_fields, >=6 industry_specific_fields, >=10 risk_rules, >=5 compliance_constraints, >=4 content_templates, kpi_weights 和为 1。

### Task 6: 行业规则接入分析管线

Completeness/综合评分/幻觉检测/Action 生成/Content 生成/审核流 全部按行业规则执行。

### Task 7: 行业模板选择与推荐

手动选择 + 系统推荐（基于品牌名/官网/产品/GT 字段）+ general/unknown/hybrid 兜底 + primary+secondary。变更写入 AuditLog。

### Task 8: Dashboard + 报告行业解释

Dashboard 行业诊断说明卡 + KPI 权重解释 + 报告行业口径说明。

### Task 9: 测试（>=45 个）

seed 质量 15 + 问题模板 4 + 风险规则 5 + 品牌关联 6 + Action/Content 5 + 行业推荐 5 + 变更审计 5。

---

## 五、验证标准

- [ ] 15 行业 + 3 兜底模板种子数据
- [ ] IndustryQueryTemplate 独立模型可用
- [ ] risk_rules + compliance_constraints 结构化
- [ ] competitor_rules 分层
- [ ] 品牌行业关联含版本+审计
- [ ] 行业模板推荐机制可用
- [ ] Dashboard 行业解释卡
- [ ] 131 现有 tests 继续通过
- [ ] 新增 >=45 个测试
