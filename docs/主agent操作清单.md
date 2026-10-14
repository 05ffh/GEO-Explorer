# 主 agent 操作清单

> 系统做不了的事（**知识 / 判断 / 调度**）由主 agent 做，不硬编码成系统数据。
> 统一模式：**系统 `generate` 待处理 → 主 agent 判定 → 系统 `apply` 写回**。
> 各脚本跑完会把「介入点清单」打印出来；本文件是**全流程汇总**，防漏步。

---

## A. P2 段（GT / 定位）— `scripts/run_gt_diagnosis.py <品牌> <城市>`

跑完自动打印「主 agent 介入点清单」，逐项：

1. **档位确认** — 品牌表内已按行政档位定档；需 ADR/星级精修时：
   `python scripts/finalize_tier.py <run_id> --adr 850 --star 五星`（或 `--tier 高端` 直接指定）
2. **竞品识别**（P3 归因题前置）— 系统判档位/ADR 带，主 agent 复核 ring/format/去重 →
   `python scripts/write_competitor.py <run_id> '福州世茂洲际酒店:核心:高端:700:标准'`
3. **场景竞对分配** — 系统检测到多场景未分配时提示 →
   `python scripts/assign_scenario_competitors.py <run_id> --apply`（归因题文本变 → 自动开新基线）
4. **字段提取 + 可信度评定** — 每字段归一化后构建 Evidence 调 `assess_credibility`（verified/consensus 才写正文）
5. **🎯 负面终判**（spec 4.5，**最易漏**）— 舆情负面率出炉时为 `preliminary`（粗筛下界，含误判），须终判：
   ```
   python scripts/finalize_sentiment.py <run_id> --generate   # 生成候选（URL/内容/主题）
   # 主 agent 逐条标 verdict: negative（真负面）/ exclude（误判：主语不符/地名歧义/跨国/评分摘要/无关主题）+ reason
   python scripts/finalize_sentiment.py <run_id> --apply /tmp/verdict_xxx.json   # 重算写回 status=confirmed
   ```
   ⚠️ **报告闸门**：`build_geo_report` 硬校验 `sentiment.status==confirmed`，未终判**拒绝出报告**。
6. **人群推断** — 读官网定位/房型/设施/地理四信号 → `python scripts/finalize_personas.py <run_id> 商务差旅 3 亲子家庭 1`
7. **采集不足 / 后端失败** — 按提示补采或记录缺口

---

## B. P3 段（测量）— `scripts/run_measure.py <品牌> <城市> [run_id] [--system B]`

跑完自动打印「主 agent 介入点清单（P3 测量段）」：

1. **命中判定**（子 agent）—
   `python scripts/finalize_hit.py --generate <run_id>` → 按 `dispatch_prompts.HIT_DISPATCH` 派子 agent → `--apply <run_id>`
2. **归因提取**（子 agent）—
   `python scripts/finalize_attribution.py generate <run_id> --out 待提取.json` → 按 `ATTRIBUTION_DISPATCH` 派子 agent → `apply <run_id>`
3. **盖章**（一次收口，算齐全部派生指标）— `python scripts/finalize_v4.py seal <run_id> <归因patch.json>`

> 判定规范（`_HIT_SPEC`/`_ATTRIBUTION_SPEC`）随待判文件 `spec` 字段**自动下发**，主 agent 不用手写规范——只用固化模板写调度外壳。

---

## C. CDP 段（国内 OTA 专线，补甲方事实）

1. **三平台同次重抓**（携程→同程→飞猪背靠背，同 Chrome/同 run）—
   `python scripts/fetch_ota_cdp.py --platform <X>`（用户先手动打开并登录酒店页）
2. **中间层归类**（**主 agent 判，非脚本**）—
   `python scripts/ingest_cdp_facts.py --generate` → 主 agent 按 `_CDP_MIDLAYER_SPEC` 归 8 类 + 跨平台一致性核对 + 去重 → `--from <json>`
   （⚠️ `write_cdp_facts` 全量覆盖 → **必须三平台一起 ingest**）

---

## D. 报告段 — `scripts/build_geo_report.py <run_id>`

1. **撰写业务叙述** — 新客户需新建 `src/report/narratives/<品牌>.py` 的 `NARRATIVE`（业务语言、无技术词、AI 原话逐字）
2. **生成** — CLI 先过**终判闸门**（status≠confirmed → 拒绝），再渲染 HTML
3. **预览 → 转 PDF**（用户确认后）

---

## 通用约束

- **子 agent 无写文件权限** → 派发 prompt 必须含「若写文件被拒，把完整 JSON 放回复里，主 agent 落盘」
- **派发用固化模板**（`src/collector/dispatch_prompts.py`），防主 agent 手写 prompt 漂移
- **判定规范不用手写**（已随待判文件 `spec` 字段自动下发）
- **换甲方 SOP**：`run_gt_diagnosis` →（可选）`clean_gt_content.py --apply` → 报告层新建 narrative
