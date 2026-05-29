# Phase 12: Dashboard 运营工作台 设计规范 v2

**日期:** 2026-05-29 | **状态:** Define  
**审阅:** GEO 产品体验架构负责人 / B2B SaaS 数据工作台设计评审专家 / 前端信息架构审查人  
**结论:** 方向通过。补齐本文 P0/P1 后进入实现。

---

## 一、设计系统

| 要素 | 选择 |
|------|------|
| 风格 | Data-Dense Dashboard |
| 主色 #1E40AF | 辅色 #3B82F6 | 强调 #F59E0B |
| 背景 #F8FAFC | 文字 #1E3A8A |
| 字体 | Fira Code (标题) + Fira Sans (正文) |
| 图标 | Heroicons SVG |
| 图表 | Chart.js |
| 技术 | Jinja2 + HTMX + Tailwind CDN (Phase 12), Tailwind CLI (Phase 13+) |

---

## 二、用户角色与权限

### 6 类角色

| 角色 | 核心任务 | 权限边界 |
|------|----------|----------|
| Owner/Admin | 管理品牌、成员、权限、API、额度 | 全部 |
| Analyst | 查看 KPI、证据、幻觉、趋势 | 读全部，不能修改 GT/Content |
| GT Reviewer | 审核 GT 候选字段、Promote | GT 字段确认/编辑，不能修改 Content |
| Content Editor | 生成、编辑、导出 Content Package | 内容 CRUD，不能审核高风险内容 |
| Legal Reviewer | 审核高风险内容、竞品对比 | 只有高风险内容的 approve 权 |
| Viewer | 只读 Dashboard 和报告 | 纯读，不能触发操作 |

### 页面权限矩阵

| 页面 | Viewer | Analyst | GT Reviewer | Content Editor | Legal Reviewer | Admin |
|------|--------|---------|-------------|----------------|----------------|-------|
| Dashboard | 读 | 读 | 读 | 读 | 读 | 全部 |
| GT 审核 | 读 | 读 | 确认/编辑 | 读 | 读 | 全部 |
| AI 证据 | 读 | 读 | 读 | 读 | 读 | 导出 |
| 幻觉风险 | 读 | 确认/忽略 | 确认/忽略 | 读 | 读 | 全部 |
| Action 工作台 | 读 | 确认 | 读 | 生成内容 | 读 | 全部 |
| Content 管理 | 读 | 读 | 读 | 编辑/导出 | 审核高风险 | 全部 |
| 趋势归因 | 读 | 读 | 读 | 读 | 读 | 触发复测 |

---

## 三、核心用户主路径（13 步）

```
1. 用户进入品牌总览页
2. 查看 AI 认知健康分和最大风险
3. 点击 GT 覆盖率不足 → 进入 GT 审核页逐字段确认
4. Promote 为 active GT
5. 触发正式采集
6. 查看 10 KPI 与指标解释卡
7. 进入幻觉风险页确认 P0/P1 风险
8. 进入 Action 工作台确认优先行动
9. 生成 Content Package
10. 在 Content 管理页审核内容和风险
11. 导出 / 标记发布
12. 在趋势归因页复测效果
13. 确认改善或继续迭代
```

### 页面跳转关系

| 起点 | 触发 | 目标页面 |
|------|------|----------|
| Dashboard 最大风险卡片 | 点击 P0 幻觉数 | 幻觉风险页 |
| KPI 卡片 | 点击"查看证据" | AI 证据页 (预筛选) |
| GT 覆盖率卡片 | 点击"补齐 GT" | GT 审核页 |
| 幻觉 Cluster | 点击"生成行动" | Action 工作台 |
| Action Theme | 点击"生成内容" | Content 管理页 |
| Content Package | 点击"复测" | 趋势归因页 |

---

## 四、全局状态设计

**每个页面必须处理的 8 种状态:**

| 状态 | 何时出现 | UI 表现 |
|------|----------|---------|
| `loading` | API 请求中 | 骨架屏/Spinner |
| `empty` | 无数据 | 引导提示 + 触发按钮 |
| `error` | API 失败 | 错误信息 + 重试按钮 |
| `permission_denied` | 无权限 | 锁图标 + 说明 |
| `partial_data` | 部分平台失败 | 黄色警告条 |
| `stale_data` | 数据超 7 天 | 刷新提示 |
| `success` | 数据就绪 | 正常展示 |

**示例:**
- GT 审核空状态: "当前品牌还没有 GT Candidate，请先触发 GT 自动采集。 [触发采集]"
- Dashboard partial: "本轮采集仅 2/3 平台成功，KPI 置信度为 medium，请谨慎解读。"
- Content 空状态: "暂无 Content Package。请先确认 Action Theme 并生成内容。 [前往 Action 工作台]"

---

## 五、7 个页面详细设计

### 页面 1: 品牌总览 (Dashboard) — 决策总览

**路由:** `/`  
**目标:** 回答"品牌 AI 认知健康吗？我今天应该做什么？"

**内容区块:**

1. **本轮结论摘要 (新增)**
   ```
   整体认知: 🟢 良好 / 🟡 一般 / 🔴 高风险
   主要问题: AI 能提到品牌，但推荐理由较弱
   最紧急: P0 品类误判 3 条
   建议动作: 修正官网定位 + 补充场景 FAQ
   ```

2. **AI 认知健康分** — 环形进度条 + 趋势箭头

3. **10 KPI 卡片** — 2 行 × 5 列
   - 每张: 指标名、得分(大号)、分子/分母(小号)、置信度标签
   - 点击 → KPI 解释卡 (HTMX): 定义、业务含义、平台拆分、排除规则、主要证据、相关 Action

4. **数据可信度卡片 (新增)**
   - 采集完成度、成功平台数、GT 覆盖率、高风险 GT 审核完成率、KPI 置信度

5. **阻塞事项 (新增)**
   ```
   ⚠ GT 未 Promote，无法正式计算准确率 → [去审核]
   ⚠ P0 幻觉未复核，不能生成高优先级 Action → [去复核]
   ⚠ Content Package 高风险，需 Legal Review → [去审核]
   ```

6. **本轮最大风险** — P0 幻觉数 + 最严重 Action Theme

7. **最优先行动** — 1-3 个 Action Theme 卡片

8. **最近变化 (新增)** — 相比上次: SOV +8.2%, Accuracy -5.1%

---

### 页面 2: GT 审核页

**路由:** `/brands/{id}/gt-review`

**新增内容:**

1. **审核进度条 (新增)**
   ```
   已审核: 12/22 | 高风险完成: 3/12 | Uncertain: 4 | 冲突: 2
   Promote 条件: ❌ official_name 未审核 | ❌ positioning 缺少 S 级来源
   ```

2. **字段列表 (增强)**
   - 状态标签: pending/accepted/edited/deleted/uncertain/blocked
   - 风险等级标签: 高(红)/中(黄)/低(绿)
   - 筛选: 只看冲突 / 只看高风险 / 只看缺证据 / 只看未审核

3. **批量操作 (新增)**
   - [接受所有低风险 high confidence 字段]
   - [折叠已审核字段]

4. **字段详情面板**
   - 候选值 + 置信度 + 来源等级标签(S/A/B/C/D)
   - 证据来源列表 (可展开 URL + excerpt)
   - 冲突来源 (红色高亮)
   - 操作: [接受] [编辑] [删除] [标记不确定]
   - 编辑历史 (原始值 → 编辑值, 编辑人, 时间)

5. **Promote 按钮**
   - 不可用 → 显示阻断原因列表
   - 可用 → [Promote 为正式 GT]

---

### 页面 3: AI 回答证据页

**路由:** `/brands/{id}/evidence`

**新增内容:**

1. **证据与分析的串联 (新增)** — 每条 AI 回答显示:
   - 参与了哪些 KPI、是否计入分子/分母
   - 触发了哪些幻觉 (可点击跳转)
   - 触发了哪些 Action Theme
   - 是否有官方引用、置信度

2. **筛选项 (扩展):**
   - 平台 | 问题维度 | 是否提及品牌 | 是否有 P0 幻觉 | 是否生成 Action | 采集批次

3. **详情面板:**
   - 问题、平台、模型版本、采集时间
   - AI 原文 (品牌提及高亮)
   - 引用 URL
   - 字段级 GT 对比表
   - 幻觉判定结果
   - KPI 计入情况
   - 相关 Action Theme 链接

---

### 页面 4: 幻觉风险页

**路由:** `/brands/{id}/hallucinations`

**新增内容:**

1. **人工复核状态 (新增)**
   ```
   每条幻觉/Cluster: pending_review / confirmed / dismissed / resolved
   ```

2. **误判纠正 (新增)** — 用户可标记:
   - "这不是错误" / "这是部分正确" / "这是 GT 错了" / "这是低风险表达偏差"

3. **复核后影响 (新增):**
   - 是否生成 Action Theme
   - 是否计入风险统计
   - 是否更新 GT

4. **Cluster 证据 (增强):**
   - 涉及平台数、涉及问题数、典型 AI 原句、GT 正确值
   - 错误类型、严重等级、相关 KPI 影响

5. **视图切换:** 聚合 Cluster 视图 ↔ 详细列表视图

---

### 页面 5: Action 工作台

**路由:** `/brands/{id}/actions`

**新增内容:**

1. **状态流转规则 (增强):**
   ```
   detected → confirmed → content_generating → content_ready
   → needs_review → approved → published_marked
   → verification_pending → verified | dismissed
   ```

2. **每张卡片显示 (增强):**
   - 优先级(P0/P1/P2)、影响 KPI、涉及字段、涉及平台
   - 证据数量、预计收益、执行难度
   - 负责人、截止日期

3. **权限限制:**
   - Viewer 不能操作 | Analyst 可确认 | Content Editor 可生成内容
   - Legal Reviewer 可审核高风险 | Admin 可标记发布

4. **视图:** Kanban 看板 (默认) | 列表视图

---

### 页面 6: Content Package 管理

**路由:** `/brands/{id}/content`

**新增内容:**

1. **内容治理信息 (新增):**
   - 关联 Action Theme、目标 KPI
   - 内容风险等级 (低/中/高)
   - 事实检查通过率、禁止声明检查结果
   - 使用的 GT 字段、使用的证据来源

2. **事实来源映射 (新增):**
   ```
   句子 → GT 字段 → 来源 URL → Source Tier → 是否人工确认
   ```

3. **发布检查清单 (增强) — 按平台区分:**
   - 官网 CMS: 是否符合品牌口径
   - Schema JSON-LD: 是否通过结构化数据校验
   - 知乎/百度百科/小红书: 是否适配平台

4. **操作:** [审核通过] [导出 MD] [导出 JSON] [标记已发布(填写 URL)]

---

### 页面 7: 趋势与归因

**路由:** `/brands/{id}/trends`

**新增内容:**

1. **Action 效果验证表 (新增):**
   ```
   Action Theme | 发布时间 | 目标 KPI | 发布前均值 | 发布后均值 | 变化 | 归因置信度 | 结论
   ```

2. **归因标签 (新增):**
   - 可能由 Action 导致 / 可能由模型波动 / 样本不足 / 平台失败影响 / GT 更新导致

3. **趋势图标记 (增强):** Action 发布时间、GT 版本变更、Prompt 变更、模型版本变更、Content Package 发布时间

4. **时间范围:** 周/月/季 | 对比上轮

---

## 六、布局与响应式

### 桌面 (1024px+)
```
┌──────────────────────────────────────────┐
│  Logo GEO Explorer  [品牌选择器▼] [用户] │  ← 顶栏 h-14
├────────┬─────────────────────────────────┤
│ 导航    │  <main>                         │
│ 📊 总览 │  面包屑                          │
│ 📋 GT   │  页面标题 + 数据时间               │
│ 💬 证据 │  ──────────────────              │
│ ⚠ 幻觉 │  页面内容 (HTMX 局部刷新)           │
│ ✅ Action│                                  │
│ 📦 Content│                                 │
│ 📈 趋势 │                                   │
├────────┴─────────────────────────────────┤
│  GEO Explorer | {brand} | 采集时间        │  ← 状态栏
└──────────────────────────────────────────┘
```

### 响应式断点
- **375px:** 侧栏隐藏(hamburger), KPI 卡片单列, 表格→卡片
- **768px:** 侧栏可折叠, KPI 2 列
- **1024px:** 侧栏固定, KPI 3-4 列
- **1440px:** KPI 5 列, 数据表密集布局

---

## 七、API 需求

```text
GET  /api/brands/{id}/overview           ← 决策摘要数据
GET  /api/brands/{id}/kpi-cards          ← 完整 KPI 解释卡
GET  /api/brands/{id}/gt-review          ← GT 审核数据
POST /api/gt-candidates/{id}/fields/{field}/accept|edit|uncertain
GET  /api/brands/{id}/evidence           ← AI 证据列表 (支持筛选)
GET  /api/brands/{id}/hallucination-clusters
POST /api/hallucination-clusters/{id}/confirm|dismiss
GET  /api/brands/{id}/action-themes
POST /api/action-themes/{id}/transition  ← 状态流转
GET  /api/brands/{id}/trends
GET  /api/brands/{id}/attribution        ← 归因数据
```

---

## 八、实施阶段

| 阶段 | 内容 | 页面 |
|------|------|------|
| 1: 信息架构 | base.html, 导航, 品牌选择器, Dashboard | 1 |
| 2: 审核证据链 | GT 审核, AI 证据, 幻觉风险 | 2-4 |
| 3: 行动内容流 | Action 工作台, Content 管理, 状态流转 | 5-6 |
| 4: 趋势归因 | 趋势页, 效果验证, 归因标签 | 7 |
| 5: 生产体验 | 响应式, 空/错/权限态, 可访问性, Tailwind 本地化 | 全部 |

---

## 九、验证标准

- [ ] 7 页面正常渲染 + 8 种状态覆盖
- [ ] 品牌选择器切换 + HTMX 局部刷新
- [ ] 10 KPI 卡片含分子分母 + 解释卡可展开
- [ ] GT 审核: 字段级状态 + 批量操作 + Promote 阻断提示
- [ ] AI 证据: 与 KPI/幻觉/Action 串联展示
- [ ] 幻觉: 人工复核状态 + 误判纠正
- [ ] Action: 状态流转规则 + 权限限制
- [ ] Content: 风险等级 + 事实来源映射
- [ ] 趋势: 效果验证表 + 归因标签
- [ ] 响应式: 375/768/1024/1440
- [ ] 89 tests 继续通过
- [ ] 无 emoji 图标
