from flask import Flask
from flask_caching import Cache # Import Cache
from celery import Celery, Task # Import Celery and Task

Initialize the Flask application

app = Flask(name)

--- Celery Configuration ---
Update this with your actual Redis URL if different

CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'

def make_celery(app_instance):
celery_app = Celery(
app_instance.import_name,
broker=app_instance.config['CELERY_BROKER_URL'],
backend=app_instance.config['CELERY_RESULT_BACKEND'],
include=['app.tasks'] # Add your tasks module here
)
celery_app.conf.update(app_instance.config)

class ContextTask(Task):
    abstract = True
    def __call__(self, *args, **kwargs):
        with app_instance.app_context():
            return self.run(*args, **kwargs)

celery_app.Task = ContextTask
return celery_app
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
IGNORE_WHEN_COPYING_END

app.config.update(
CELERY_BROKER_URL=CELERY_BROKER_URL,
CELERY_RESULT_BACKEND=CELERY_RESULT_BACKEND
)
celery = make_celery(app)

--- End Celery Configuration ---
Configure cache
Using SimpleCache: In-memory cache per process. Suitable for development
or single-process deployments. For multi-process/multi-server, consider
RedisCache, MemcachedCache, or FileSystemCache.

cache_config = {
"CACHE_TYPE": "SimpleCache", # Use SimpleCache for now
"CACHE_DEFAULT_TIMEOUT": 300 # Default timeout 5 minutes (adjust as needed)
}
app.config.from_mapping(cache_config) # This will merge with existing app.config
cache = Cache(app) # Initialize Cache with the app

Import routes after initializing the app, cache, and celery
We will create the routes.py file next

from app import routes # Ensure tasks.py is created and imported by Celery