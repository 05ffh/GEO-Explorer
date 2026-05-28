from celery import Celery
from src.config import settings

app = Celery("geo_explorer", broker=settings.redis_url)
app.conf.update(
    beat_schedule={
        "weekly-collection": {
            "task": "src.collector.tasks.weekly_collect",
            "schedule": 604800.0,
        },
    },
    timezone="Asia/Shanghai",
)
