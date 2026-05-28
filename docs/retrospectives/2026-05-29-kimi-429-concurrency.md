# Kimi 429 并发限制导致 59% 查询失败

**日期:** 2026-05-29
**阶段:** Build

## 问题

首次手动采集 TestBrand 时，Kimi 平台 22 个查询中只有 9 个成功（41%），13 个返回 429 错误。根因是全局 Semaphore(4) 对 Kimi 的 org 级并发上限 3 无感知——4 个槽位同时发出请求，Kimi 拒绝第 4 个。retry_count 全为 0，说明 Collector 没有对 HTTP 错误做重试。

## 方案

在 Collector 中引入平台级并发上限 `PLATFORM_CONCURRENCY = {"kimi": 2, ...}`，Kimi 留余量设为 2。同时为 429 错误增加重试逻辑：最多 2 次，退避 `(retry_count + 1) * 2` 秒。不用全局统一并发值，因为不同平台的并发限制不同。

## 结果

待采集验证。预期 Kimi 成功率达到 100%（22/22），或至少重试耗尽后明确标记 error 并带 retry_count 记录。

## 教训

- 每个平台的并发模型不同——不能用一个全局 Semaphore 管所有平台
- HTTP 层错误（非网络异常）需要显式检查 status code 并重试，`return_exceptions=True` 的 gather 不会触发重试
