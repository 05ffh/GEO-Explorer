# Collector 并发风暴与适配器空白兜底

**日期:** 2026-05-31 | **严重程度:** P0 — 阻采集

## 现象

触发星巴克 GEO 诊断，4 平台 × 23 查询 = 92 并发 API 调用。结果：
- DeepSeek/Kimi/Doubao: 69 条全部 "Request timed out."
- Wenxin: 23 条 status=success 但 answer_text 全为空

## 根因

1. **并发过高**: `collector_concurrency=4` + Celery worker concurrency=4 → 92 个 API 调用几乎同时发出 → OpenAI SDK 自带的限流重试机制触发 → 所有调用在重试中耗尽时间 → 最终超时。Celery 日志显示数百行 "Retrying request to /chat/completions in X seconds"。

2. **Wenxin 空回答无报错**: 适配器 `query()` 在 `data.get("result", "")` 返回空串时，不设 `error` 字段，导致 `AIResponse` 以 `error=None` 返回。采集器据此标记 `status="success"`，但实际无数据。

3. **Wenxin token 失败无检测**: `_get_access_token()` 直接 `data["access_token"]`，API 返回错误时不抛明确异常。

## 修复

- `config.py`: `collector_concurrency: 4→2`, `collector_timeout: 30→60`, `collector_max_retries: 2→1`
- `wenxin.py`: token 获取增加 error/access_token 校验；query 增加 error_msg 和空 result 检测

## 防止再犯

- 适配器必须对空响应显式报错，不可静默成功
- `AIResponse.error=None` 应等价于成功，但 `answer_text=""` 时应有 warning
- 并发测试: 正式上线前需用 Locust/k6 验证 23 queries × 4 platforms 并发场景
