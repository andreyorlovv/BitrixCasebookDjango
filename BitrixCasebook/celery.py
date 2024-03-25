import os

from celery import Celery, shared_task
from celery.schedules import crontab

from BitrixCasebook import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'BitrixCasebook.settings')

app = Celery('BitrixCasebook')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()


@shared_task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')


app.conf.beat_schedule = {
    'update_filters': {
        'task': 'casebook.tasks.update_filters',
        'schedule': crontab(minute='*/60')
    },
    'get_tasks_from_db': {
        'task': 'casebook.tasks.get_tasks_from_db',
        'schedule': crontab(minute='*/30'),
        'options': {'expires': 25}
    }
}
