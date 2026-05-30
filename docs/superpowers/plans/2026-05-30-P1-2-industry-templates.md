# P1-2 行业模板体系 实现计划 v2

**日期:** 2026-05-30 | **状态:** Plan | **审阅:** 15 行业升级方案已通过方向评审
**当前完成度:** 0%

---

## 一、目标

为 15 个高价值行业建立 GEO 诊断模板，让系统能根据不同行业判断：什么事实最重要、什么错误最危险、什么竞品最相关、什么内容最能修复 AI 认知。

---

## 二、15 个行业模块

### 阶段一：核心 8 个行业（优先）

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

### 阶段二：扩展 7 个行业

| # | 行业 | slug |
|---|------|------|
| 9 | 文旅酒店与本地生活 | travel_hospitality |
| 10 | 房地产与家居建材 | real_estate_home |
| 11 | 工业制造与 B2B 供应链 | industrial_b2b |
| 12 | 物流供应链与跨境贸易 | logistics_crossborder |
| 13 | AI / 云计算 / 开发者工具 | ai_cloud_devtools |
| 14 | 美妆个护与时尚生活 | beauty_fashion |
| 15 | 政府公共服务与城市品牌 | public_sector_city |

---

## 三、每个行业模板的 7 维度设计

| 维度 | 内容 |
|------|------|
| 核心 GT 字段 | required_gt_fields + industry_specific_fields |
| KPI 权重 | kpi_weights (sum=1.0)，不同行业侧重不同 KPI |
| 行业问题模板 | industry_query_templates (>=12 个) |
| 竞品规则 | competitor_rules（同品类/同价位/同区域/同场景） |
| 风险词库 | risk_keywords（P0/P1 分级） |
| 合规约束 | compliance_constraints（禁止声明 + 引用要求） |
| Content 模板 | content_templates（行业化内容生成方向） |

---

## 四、数据模型

```python
class IndustryTemplate(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "industry_templates"
    name: Mapped[str]
    slug: Mapped[str]
    description: Mapped[str]
    version: Mapped[str] = mapped_column(default="1.0")
    status: Mapped[str] = mapped_column(default="draft")  # draft/active/deprecated

    # GT
    required_gt_fields: Mapped[list] = mapped_column(JSONB, default=list)
    optional_gt_fields: Mapped[list] = mapped_column(JSONB, default=list)
    high_risk_gt_fields: Mapped[list] = mapped_column(JSONB, default=list)
    industry_specific_fields: Mapped[dict] = mapped_column(JSONB, default=dict)
    gt_field_weights: Mapped[dict] = mapped_column(JSONB, default=dict)

    # KPI
    kpi_weights: Mapped[dict] = mapped_column(JSONB, default=dict)

    # 竞品
    competitor_rules: Mapped[dict] = mapped_column(JSONB, default=dict)

    # 风险
    risk_keywords: Mapped[list] = mapped_column(JSONB, default=list)
    compliance_constraints: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Action & Content
    action_rules: Mapped[dict] = mapped_column(JSONB, default=dict)
    content_templates: Mapped[dict] = mapped_column(JSONB, default=dict)
```

Brand 扩展：
```python
primary_industry_template_id: Mapped[uuid.UUID | None]
secondary_industry_template_ids: Mapped[list] = mapped_column(JSONB, default=list)
```

---

## 五、实现任务

### Task 1: IndustryTemplate 模型 + Migration + 种子数据

创建模型，运行 migration，编写 15 个行业的完整种子数据脚本。

### Task 2: Brand 行业关联

Brand 增加 primary + secondary template_id，支持模板选择。

### Task 3: 行业规则接入分析管线

- Completeness 使用行业字段权重
- 综合评分使用行业 KPI 权重
- 幻觉检测使用行业 risk_keywords

### Task 4: 模板管理 API + Dashboard

模板列表、详情、品牌关联、行业诊断说明展示。

### Task 5: 测试

- 15 模板 seed 验证
- 行业字段/KPI 权重/风险规则测试
- 品牌模板变更审计测试

---

## 六、质量标准

每行业模板至少：>=10 required_gt_fields, >=6 industry_specific_fields, >=10 risk_keywords, >=5 compliance_constraints, >=4 content_templates, kpi_weights sum=1

---

## 七、验证标准

- [ ] 15 个行业模板种子数据可查询
- [ ] 每个模板满足质量标准
- [ ] 品牌可关联行业模板
- [ ] 131 现有 tests 继续通过
- [ ] 新增 >=15 个测试
