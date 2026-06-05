# Module 1: 品牌管理前端补齐 — 设计规格

**日期:** 2026-06-04
**状态:** 已吸收补齐清单 (ActionContent 审阅文档 12 条通用原则)
**父项:** GEO Explorer 前端补齐 (9 模块中剩余 5 个)
**审阅参考:** `GEO_Explorer_ActionContent_补齐清单二次审阅与Build确认.md`

## 动机

品牌管理模块是用户操作品牌的入口。当前缺少三个关键前端功能：
1. 品牌信息不可编辑（API `PUT /api/brands/{id}` 已存在但无 UI）
2. GT 采集缺少触发按钮（API `POST /api/brands/{id}/gt-collect` 已存在但无 UI 入口）
3. 无品牌列表总览页（API `GET /api/brands` + `/search` 已存在，但只在侧边栏 dropdown 中使用）

全部补齐，后端 API 就绪，零后端改动。

---

## 设计原则

1. **HTMX 优先** — 编辑/状态反馈使用 HTMX 局部刷新，不跳页
2. **geoFetch 统一客户端** — 所有 API 调用走 `static/js/api.js`
3. **五态覆盖** — 每个交互覆盖 loading / empty / error / success / partial 状态
4. **复用现有组件** — empty_state / error_state / loading_skeleton / status_badge 等 partials
5. **不切设计系统** — 沿用 Data-Dense Dashboard, #1E40AF/#3B82F6/#F59E0B, Fira Code+Sans

---

## 1. 品牌编辑 (内联编辑)

### 1.1 交互流程

```
查看模式 (Dashboard 顶部品牌信息区)
  ┌──────────────────────────────────────────────────────┐
  │ 品牌名称                    行业           [编辑]     │
  │ 别名: xxx, xxx                         [GT采集]     │
  └──────────────────────────────────────────────────────┘
                          │ 点击 [编辑]
                          ▼
  ┌──────────────────────────────────────────────────────┐
  │ ┌──────────────┐ ┌──────────────┐                   │
  │ │ 品牌名称*     │ │ 行业 ▾       │                   │
  │ └──────────────┘ └──────────────┘                   │
  │ ┌──────────────────────────────────┐                 │
  │ │ 别名 (逗号分隔)                   │                 │
  │ └──────────────────────────────────┘                 │
  │             [保存] [取消]                             │
  └──────────────────────────────────────────────────────┘
```

### 1.2 状态

| 状态 | 视觉 |
|------|------|
| **view** | 品牌名 + 行业 + 别名列表 + 编辑/GT采集按钮 |
| **edit** | 表单替换品牌信息区：3 个字段 |
| **saving** | 保存按钮 disabled + spinner，取消按钮 disabled |
| **success** | toast "品牌信息已更新" + 自动切回 view |
| **error** | 表单上方 inline error + 保存按钮恢复 |

### 1.3 实现

- **模板:** `src/templates/partials/brand_header_edit.html` (HTMX fragment)
- **后端:** `PUT /api/brands/{id}` (已有) — 返回 `{id, name}`
- **触发:** Dashboard 页面 `/brands/{id}` 中的编辑按钮
- **字段:**
  - `name` (string, required) — `<input type="text">`
  - `aliases` (string, 逗号分隔) — `<input type="text">`，后端 `list[str]`
  - `industry` (string) — `<select>`，选项列表从 `src/schemas/industry_config.py` 获取

### 1.4 行业选项列表

复用 `brands/new.html` 中的行业 select。选项值使用 `IndustryProfile` 中的 industry key 列表。以 API 返回为准，前端不硬编码。

通过调用 `GET /api/ground-truth/industries` (如果不存在则新增，或直接在模板中从已有常量渲染)。

如果后端无此端点：在 view model 中注入 `INDUSTRY_CHOICES` 常量。

---

## 2. GT 采集按钮

### 2.1 交互流程

```
[idle]    点击「采集 GT」
              │
              ▼
[loading]  按钮 disabled + spinner「采集中...」
              │
     ┌────────┴────────┐
     ▼                 ▼
[success]           [error]
toast "GT采集       toast "启动失败:
已启动"              {error}"
按钮 →「查看任务」
```

**特殊状态: duplicate** — API 返回 `status: "duplicate"` → toast "已有采集任务执行中"，按钮仍为 idle。

### 2.2 位置

| 位置 | 页面 | 路由 |
|------|------|------|
| Dashboard 品牌信息区 | `dashboard/index.html` | `/brands/{id}` |
| GT 审核页顶部 | `gt_review/index.html` | `/brands/{id}/gt-review` |
| 品牌列表页每行 | `brands/list.html` (新增) | `/brands` |

### 2.3 实现

- **JS 函数:** `triggerGTCollect(brandId)` — 调用 `POST /api/brands/{brand_id}/gt-collect`，已定义于 `static/js/api.js`
- **后端:** `POST /api/brands/{brand_id}/gt-collect` (已有)，返回: `{status: "queued"|"duplicate"|"enqueue_failed", task_id, brand_id}`
- **按钮 class:** `gt-collect-btn` 带 `data-brand-id` 属性

### 2.4 按钮样式

```
idle:    bg-cta text-white rounded-lg px-4 py-2 text-sm font-medium
         hover:opacity-90 transition-colors cursor-pointer
loading: bg-gray-400 text-white rounded-lg px-4 py-2 text-sm cursor-not-allowed
         (内含 SVG spinner + "采集中...")
```

---

## 3. 品牌列表页

### 3.1 路由

**新页面:** `GET /brands` — 品牌列表页

注意：`GET /api/brands` 已有 (API)，路由不冲突。`/brands` 是 HTML 页面，`/api/brands` 是 JSON API。

### 3.2 布局

```
┌─ 页面标题 "品牌管理" ──────────── [+ 创建品牌] ────┐
│                                                     │
│ ┌─ 搜索品牌名称... ────┐ ┌─ 全部行业 ▾ ────┐       │
│ └─────────────────────┘ └─────────────────┘       │
│                                                     │
│ ┌─ 品牌卡片 (× N) ────────────────────────────────┐ │
│ │                                                  │ │
│ │  [品牌名]    行业标签    GT: 8/10 字段             │ │
│ │  别名: ...                                       │ │
│ │  最近采集: 2026-06-03  ·  最近诊断: 2026-06-02    │ │
│ │                                                  │ │
│ │  [编辑] [启动诊断] [GT采集] [查看Dashboard]       │ │
│ │                                                  │ │
│ └──────────────────────────────────────────────────┘ │
│                                                     │
│ ┌─ 分页 ───────────────────────────────────────────┐ │
│ │  < 上一页   1  2  3  4  5   下一页 >    共 12 个  │ │
│ └──────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

### 3.3 状态

| 状态 | 视觉 |
|------|------|
| **loading** | 卡片区显示 `loading_skeleton.html` |
| **empty (无品牌)** | `empty_state.html` — "还没有品牌，创建第一个品牌开始 GEO 诊断" + CTA 按钮 |
| **empty (搜索无结果)** | `empty_state.html` — "没有找到匹配的品牌，试试其他关键词" |
| **error** | `error_state.html` — "加载失败，请重试" |
| **data** | 品牌卡片列表 + 分页 |
| **partial** | `partial_data_banner.html` — 部分数据加载失败 |

### 3.4 搜索与筛选

- **搜索:** 输入框 onChange (300ms debounce) → 更新 query param `?q=xxx` → HTMX 局部刷新列表
- **行业筛选:** `<select>` onChange → 更新 `?industry=xxx` → HTMX 刷新
- **分页:** URL query param `?page=1&page_size=20`
- **组合:** `?q=星巴克&industry=restaurant_chain&page=1`

### 3.5 实现

- **模板:** `src/templates/brands/list.html` (新增)
- **View Model:** `src/view_models/brands.py` (新增) — `build_brand_list_vm(user, filters, db)`
- **后端 API 复用:**
  - `GET /api/brands?page=1&page_size=20` — 分页列表
  - `GET /api/brands/search?q=xxx` — 搜索
- **后端可能需要扩展:** 列表 API 返回的 Brand 对象需要包含 GT 覆盖状态和最近采集时间。如果当前 `GET /api/brands` 返回的 Brand 不含这些字段，有两种方案：
  - **方案 A:** 扩展 API 返回计算字段 (view model 查询聚合)
  - **方案 B:** 新增 `/api/brands/list-enhanced` 端点
  - **推荐方案 A:** 在 view model 中做 JOIN 查询，不动现有 API

### 3.6 列表页需要展示的字段

| 字段 | 来源 | 显示格式 |
|------|------|---------|
| 品牌名 | `Brand.name` | 粗体文字 |
| 行业 | `Brand.industry` | 彩色标签 (badge) |
| 别名 | `Brand.aliases` | 逗号分隔，最多显示 3 个 |
| GT 覆盖度 | `GT.active_gt` 的字段计数 | "8/10 字段" + 百分比 |
| 最近采集 | `CollectionRun.started_at` (最新一条) | 相对时间 "3天前" 或日期 |
| 最近诊断 | `CollectionRun` 中 trigger_type=manual 的最新 | 同格式 |
| 品牌 ID | `Brand.id` | 用于操作链接 |

---

## 4. 文件清单

### 4.1 新增文件

| 文件 | 内容 |
|------|------|
| `src/templates/brands/list.html` | 品牌列表页 |
| `src/templates/partials/brand_header_edit.html` | 品牌编辑 HTMX fragment |
| `src/templates/partials/brand_header_view.html` | 品牌信息查看 HTMX fragment (从 dashboard 拆分) |
| `src/view_models/brands.py` | `build_brand_list_vm()` |
| `src/static/js/brands.js` | `triggerGTCollect()`, 搜索 debounce |

### 4.2 修改文件

| 文件 | 改动 |
|------|------|
| `src/main.py` | 新增 `GET /brands` 路由 + 品牌 header 路由 (edit fragment) |
| `src/templates/dashboard/index.html` | 集成品牌 header view/edit toggle |
| `src/templates/gt_review/index.html` | 添加 GT 采集按钮 |
| `src/static/js/api.js` | 添加 `triggerGTCollect()` 函数 |
| `src/view_models/dashboard.py` | 注入 `brand.editable=True` + 行业选项列表 |

---

## 5. API 绑定表

Build 前必须用真实后端响应确认此表。如果某个 API 不存在或返回字段不匹配，前端不能做假按钮。

| 页面 | 按钮/操作 | API | Method | 权限 | 危险操作 | reason | idempotency | 成功后动作 |
|------|----------|-----|--------|------|:--:|:--:|:--:|------|
| Dashboard | 编辑品牌 | `/api/brands/{id}` | `PUT` | `brand:edit` | 否 | 否 | 否 | Toast + 切回 view |
| Dashboard | 触发 GT 采集 | `/api/brands/{id}/gt-collect` | `POST` | `brand:gt_collect` | 是 | 否 | **是** (已有) | Toast + 查看任务 |
| GT 审核页 | 触发 GT 采集 | 同上 | `POST` | 同上 | 是 | 否 | **是** | Toast + 查看任务 |
| 品牌列表 | 查看品牌列表 | `/api/brands` | `GET` | `brand:list` | 否 | 否 | 否 | 展示列表 |
| 品牌列表 | 搜索品牌 | `/api/brands/search` | `GET` | `brand:list` | 否 | 否 | 否 | HTMX 局部刷新 |
| 品牌列表 | 按行 GT 采集 | `/api/brands/{id}/gt-collect` | `POST` | `brand:gt_collect` | 是 | 否 | **是** | Toast |

### 4.1 API 响应结构确认

**`PUT /api/brands/{id}`** (已有)
```json
// Request:  { "name": "string?", "aliases": ["string"]?, "industry": "string?" }
// Response: { "id": "uuid", "name": "string" }
// Errors:   404 (brand not found), 403 (forbidden)
```

**`POST /api/brands/{id}/gt-collect`** (已有)
```json
// Request:  (no body), Query: ?force=false
// Response: { "status": "queued"|"duplicate"|"enqueue_failed", "task_id": "string", "brand_id": "uuid" }
//           或 { "task_id": "...", "status": "duplicate", "message": "已有相同任务在执行中" }
// Errors:   404, 403
```

**`GET /api/brands`** (已有，需扩展)
```json
// Request:  Query: ?page=1&page_size=20
// Response: { "items": [...], "page": 1, "page_size": 20 }
// 当前 Brand 对象不包含 GT 覆盖度和最近采集时间——
// 由 ViewModel 做 JOIN 查询补齐，不动 API 契约
```

**`GET /api/brands/search`** (已有)
```json
// Request:  Query: ?q=xxx
// Response: { "items": [...], "query": "xxx" }
```

---

## 6. 不考虑 (YAGNI)

- 品牌删除功能 (数据安全，需独立设计)
- 批量编辑/批量 GT 采集
- 品牌排序 (按创建时间降序即可)
- 品牌头像/Logo 上传
- 高级筛选 (按 GT 覆盖率/采集状态) — 留到后续迭代
- 品牌列表导出

---

## 7. 边缘情况

| 场景 | 处理 |
|------|------|
| 编辑时网络断开 | geoFetch 自动 toast 错误，表单保持 edit 模式，不丢失输入 |
| GT 采集已有任务运行中 | API 返回 duplicate → toast 提示，不重复触发 |
| 品牌名称为空提交 | 前端 required 校验 + 后端 `BrandUpdate.name is not None` 不变 |
| 行业值不在选项列表中 | select 允许任意输入，后端接受字符串 |
| 列表页无品牌 | empty_state 带 CTA 引导创建 |
| 搜索无结果 | empty_state "没有找到匹配的品牌" |
| 列表页大数据量 | 分页 page_size=20，不预加载全部 |
| 并发编辑 | 后保存覆盖先保存 (Last-Write-Wins)，不做乐观锁 |

---

## 8. Build 前硬性执行清单

在进入 Build 前，agent worker 必须先完成以下 10 项确认：

```text
1.  API CONTRACT — 用 curl 验证上表 4 个 API 的真实响应，确认字段名与 Spec 一致
2.  NO FAKE BUTTONS — 如果按钮对应的 API 返回非预期响应，不显示该按钮
3.  EDIT FORM — 内联编辑切换不跳页，取消丢弃修改，保存失败保留输入
4.  GT TRIGGER IDEMPOTENCY — POST gt-collect 已有幂等键，重复点击不创建重复任务
5.  GT SUCCESS ROUTING — GT 采集成功后必须有 "查看任务" 入口，不只 toast
6.  EMPTY STATES — 品牌列表页 3 种空状态 (无品牌/搜索无结果/加载失败) 各有明确 CTA
7.  BRAND LIST VM — ViewModel 负责 JOIN 查询 GT 覆盖度 + 最近采集时间，不动 API 契约
8.  CONTENT SECURITY — 所有用户输入和品牌名渲染必须经过 Jinja2 自动转义
9.  PERMISSION BUTTONS — 编辑/GT采集按钮由 ViewModel 返回的 can_edit/can_gt_collect 控制
10. E2E — 跑通最小闭环 (见第 8 节)，不能只验证按钮出现
```

---

## 9. E2E 验收链路

### E2E-1: 编辑品牌名称

```text
Given: 品牌存在
When:  进入 Dashboard → 点击编辑 → 修改名称 → 点击保存
Then:  PUT /api/brands/{id} 返回 200
Then:  Toast "品牌信息已更新"
Then:  品牌信息区自动切回查看模式，显示新名称
```

### E2E-2: 触发 GT 采集

```text
Given: 品牌存在，无正在运行的 GT 采集任务
When:  点击 GT 采集按钮
Then:  按钮进入 loading 状态 (spinner + "采集中...")
Then:  POST /api/brands/{id}/gt-collect 返回 { status: "queued" }
Then:  Toast "GT采集已启动" + 按钮变为 "查看任务"
```

### E2E-3: GT 采集去重

```text
Given: GT 采集任务正在运行中
When:  再次点击 GT 采集按钮
Then:  POST /api/brands/{id}/gt-collect 返回 { status: "duplicate" }
Then:  Toast "已有采集任务在执行中"
Then:  按钮保持 idle 状态
```

### E2E-4: 品牌列表页 (有数据)

```text
Given: 组织下有 ≥1 个品牌
When:  进入 /brands
Then:  展示品牌卡片列表，每张含: 品牌名/行业/GT覆盖度/最近采集/操作按钮
Then:  搜索框可用，行业筛选可用
Then:  每个品牌有 [编辑] [诊断] [GT采集] [Dashboard] 按钮
```

### E2E-5: 品牌列表页 (无数据)

```text
Given: 组织下 0 个品牌
When:  进入 /brands
Then:  展示 empty_state
Then:  文案: "还没有品牌，创建第一个品牌开始 GEO 诊断"
Then:  CTA 按钮 → /diagnostics/new
```

### E2E-6: 搜索无结果

```text
Given: 品牌列表有数据
When:  搜索 "不存在的品牌名"
Then:  展示 empty_state: "没有找到匹配的品牌，试试其他关键词"
Then:  清除搜索 → 恢复完整列表
```

### E2E-7: 无假按钮

```text
Given: 每个按钮
When:  点击按钮
Then:  必须有真实 API 调用和反馈
Then:  不存在 disabled 但无原因提示的按钮
Then:  不存在可见但不可用的按钮
```

---

## 10. 测试清单

| 测试 | 类型 |
|------|------|
| `GET /brands` 返回 200 + HTML | 集成测试 (curl) |
| `GET /brands?q=xxx` 搜索过滤 | 集成测试 |
| `GET /brands?page=2` 分页 | 集成测试 |
| 编辑表单 toggle 正常切换 | 集成测试 (curl 验证 HTML fragment) |
| `PUT /api/brands/{id}` 更新成功 200 | 已有测试覆盖 |
| `POST /api/brands/{id}/gt-collect` 触发成功 202 | 已有测试覆盖 |
| 品牌列表页空状态显示 empty_state | 集成测试 |
| GT采集按钮 loading → success toast | 集成测试 (curl + 验证 toast) |
