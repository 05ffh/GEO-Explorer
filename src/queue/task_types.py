"""Per-task-type configuration: timeouts, retries, priorities."""
from dataclasses import dataclass

@dataclass(frozen=True)
class TaskTypeConfig:
    max_retries: int = 3
    soft_time_limit: int = 600     # seconds
    time_limit: int = 900          # seconds
    idempotency_ttl: int = 3600    # seconds
    default_priority: int = 5      # 1-10, lower = higher priority


TASK_TYPE_CONFIG: dict[str, TaskTypeConfig] = {
    "gt_collection": TaskTypeConfig(
        max_retries=3,
        soft_time_limit=600,
        time_limit=900,
        idempotency_ttl=3600,
        default_priority=5,
    ),
    "brand_geo_collection": TaskTypeConfig(
        max_retries=3,
        soft_time_limit=900,
        time_limit=1200,
        idempotency_ttl=3600,
        default_priority=5,
    ),
    "report_generation": TaskTypeConfig(
        max_retries=1,
        soft_time_limit=300,
        time_limit=420,
        idempotency_ttl=1800,
        default_priority=7,
    ),
    "weekly_collection": TaskTypeConfig(
        max_retries=2,
        soft_time_limit=1800,
        time_limit=2400,
        idempotency_ttl=7200,
        default_priority=3,
    ),
}


def get_task_config(task_name: str) -> TaskTypeConfig:
    for key, cfg in TASK_TYPE_CONFIG.items():
        if key in task_name:
            return cfg
    return TaskTypeConfig()
