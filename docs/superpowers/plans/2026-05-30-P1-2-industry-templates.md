# P1-2 行业模板体系 实现计划

**日期:** 2026-05-30 | **状态:** Plan | **当前完成度:** 0%

---

## 一、目标

不同行业的企业，GT 字段优先级、KPI 权重、问题模板、竞品逻辑、风险词库差异巨大。当前系统对所有品牌一视同仁——星巴克（餐饮）和 SaaS 企业用同一套模板。需要建立行业模板体系，让 GEO 诊断对不同行业更精准。

---

## 二、核心设计

### 行业模板包含 6 个维度

| 维度 | 说明 | 示例（金融 vs 餐饮） |
|------|------|---------------------|
| **GT 字段权重** | 哪些字段对该行业最关键 | 金融: 资质许可(P0) vs 餐饮: 门店覆盖(P1) |
| **问题模板** | 行业特有的查询问题 | 金融: "有牌照吗" vs 餐饮: "在哪有店" |
| **KPI 权重** | 不同 KPI 对该行业的重要性 | 金融: Accuracy 权重最高 vs 餐饮: SOV 权重最高 |
| **竞品规则** | 该行业如何定义竞品 | 金融: 同牌照类型 vs 餐饮: 同品类+同价格带 |
| **风险词库** | 行业禁止/敏感声明 | 金融: 保证收益/无风险 vs 餐饮: 包治百病 |
| **合规提醒** | 行业特有的法规要求 | 金融: 不得承诺收益 vs 餐饮: 食品安全 |

### 首批 4 个行业模板

1. **金融** (Finance)
2. **餐饮** (F&B)
3. **SaaS** (SaaS)
4. **新能源** (EV/New Energy)

---

## 三、数据模型

**文件:** `src/models/industry_template.py`（新建）

```python
class IndustryTemplate(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "industry_templates"
    name: Mapped[str]                # 金融 / 餐饮 / SaaS / 新能源
    slug: Mapped[str]                # finance / fnb / saas / ev
    gt_field_weights: Mapped[dict]   # {field_name: weight (0-1)}
    kpi_weights: Mapped[dict]        # {kpi_key: weight (0-1)}
    query_dimension_overrides: Mapped[dict]  # 行业特有的问题维度
    competitor_rules: Mapped[dict]   # 竞品匹配规则
    risk_keywords: Mapped[list]      # 风险关键词
    compliance_notes: Mapped[list]   # 合规提醒
```

Migration + 种子数据（4 条记录）。

---

## 四、实现任务

### Task 1: 行业模板模型 + Migration + 种子数据

**文件:** `src/models/industry_template.py` + Migration + `src/seed/industry_templates.py`

4 个行业的种子数据，每个含完整的 6 维度配置。

### Task 2: 行业模板注入品牌

**文件:** `src/models/brand.py`（扩展）

Brand 增加 `industry_template_id` 外键。创建品牌时可选择行业模板。

### Task 3: GT 字段权重读取

**文件:** `src/analyzer/completeness.py`（扩展）

根据品牌的行业模板，调整 GT 字段的 completeness 权重。

### Task 4: KPI 权重配置

**文件:** `src/analyzer/pipeline.py`（扩展）

综合评分时按行业 KPI 权重加权。

### Task 5: 模板管理 API + Dashboard 展示

**文件:** `src/api/industry.py` + Dashboard 新增配置入口

列出可用模板、查看模板详情、品牌关联模板。

### Task 6: 测试

- 种子数据验证（4 模板 + 必需字段）
- 权重读取验证
- 无模板时兜底策略

---

## 五、验证标准

- [ ] 4 个行业模板种子数据可查询
- [ ] 品牌可关联行业模板
- [ ] 无模板时使用默认权重
- [ ] 现有 131 tests 继续通过
- [ ] 新增 >=10 个测试
