from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "email_classifier",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "sync-inboxes": {
            "task": "app.workers.tasks.sync_all_users",
            "schedule": float(settings.fetch_interval_seconds),
        },
        "purge-old-mail": {
            "task": "app.workers.tasks.purge_old_mail",
            "schedule": 86_400.0,
        },
    },
)

import app.workers.tasks  # noqa: E402  — register tasks after the app exists
