from celery import Celery
from app.core.config import settings

# Create the celery application
celery_app = Celery(
    "anime_site_tasks",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.media_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_concurrency=4,  # Limit ffmpeg workers
    worker_prefetch_multiplier=1,  # Prevent one worker from grabbing all tasks
    task_time_limit=600,  # Hard kill after 10 min
    task_soft_time_limit=540,  # Soft kill after 9 min
)
