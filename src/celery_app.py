"""GEO Explorer — Celery app with production-grade queue config (P1-5)."""
from celery import Celery
from kombu import Exchange, Queue
from src.config import settings

app = Celery("geo_explorer", broker=settings.redis_url)

# Result backend
app.conf.result_backend = settings.redis_url
app.conf.result_extended = True
app.conf.result_expires = settings.celery_result_expires

# Queues — default + DLQ + per-platform
default_exchange = Exchange("geo_explorer", type="direct")
dlq_exchange = Exchange("geo_explorer_dlq", type="direct")

app.conf.task_queues = (
    Queue("geo_default", default_exchange, routing_key="default"),
    Queue("geo_dlq", dlq_exchange, routing_key="dlq"),
    Queue("geo_deepseek", default_exchange, routing_key="deepseek"),
    Queue("geo_kimi", default_exchange, routing_key="kimi"),
    Queue("geo_doubao", default_exchange, routing_key="doubao"),
)

app.conf.task_default_queue = "geo_default"
app.conf.task_default_exchange = "geo_explorer"
app.conf.task_default_routing_key = "default"

# Per-platform task routes
app.conf.task_routes = {
    "src.collector.tasks.collect_platform_task": {
        "queue": "geo_default",
    },
}

# Reliability — NO autoretry_for, manual retry only
app.conf.task_acks_late = True
app.conf.task_reject_on_worker_lost = True
app.conf.task_track_started = True
app.conf.worker_prefetch_multiplier = settings.celery_worker_prefetch_multiplier

# Timeouts
app.conf.task_soft_time_limit = settings.celery_task_soft_time_limit
app.conf.task_time_limit = settings.celery_task_time_limit

# Broker transport
app.conf.broker_transport_options = {
    "visibility_timeout": settings.celery_broker_visibility_timeout,
    "max_retries": 5,
    "interval_start": 0,
    "interval_step": 0.2,
    "interval_max": 0.5,
}

# Beat schedule
app.conf.beat_schedule = {
    "weekly-collection": {
        "task": "src.collector.tasks.weekly_collect",
        "schedule": 604800.0,
    },
    "dlq-monitor": {
        "task": "src.queue.dlq.dlq_monitor_task",
        "schedule": 300.0,  # every 5 minutes
    },
    "benchmark-compute": {
        "task": "src.benchmark.tasks.compute_all_benchmarks",
        "schedule": 86400.0,  # daily
    },
    "benchmark-freshness-check": {
        "task": "src.benchmark.tasks.check_benchmark_freshness",
        "schedule": 14400.0,  # every 4 hours
    },
}
app.conf.timezone = "Asia/Shanghai"

app.autodiscover_tasks(['src.collector', 'src.queue', 'src.benchmark'])

celery_app = app  # alias for direct import
