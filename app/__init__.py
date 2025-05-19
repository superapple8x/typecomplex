import redis # Add redis import for RateLimiter
from flask import Flask
from flask_caching import Cache # Import Cache
from celery import Celery, Task # Import Celery and Task
from app.rate_limiter import RateLimiter # Import RateLimiter

# Initialize the Flask application
app = Flask(__name__)

# --- Celery Configuration ---
# Update this with your actual Redis URL if different
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'

def make_celery(app_instance):
    celery_app = Celery(
        app_instance.import_name,
        broker=app_instance.config['CELERY_BROKER_URL'],
        backend=app_instance.config['CELERY_RESULT_BACKEND'],
        include=['app.tasks']  # Add your tasks module here
    )
    celery_app.conf.update(app_instance.config)

    class ContextTask(Task):
        abstract = True
        def __call__(self, *args, **kwargs):
            with app_instance.app_context():
                return self.run(*args, **kwargs)

    celery_app.Task = ContextTask
    return celery_app

app.config.update(
    CELERY_BROKER_URL=CELERY_BROKER_URL,
    CELERY_RESULT_BACKEND=CELERY_RESULT_BACKEND
)
celery = make_celery(app)
# --- End Celery Configuration ---

# --- Rate Limiter Configuration ---
# Use the same Redis as Celery for simplicity, or define a new one.
app.config['RATE_LIMITER_REDIS_URL'] = app.config['CELERY_BROKER_URL'] 
app.config['RATE_LIMIT_FAST_PER_DAY'] = 10  
app.config['RATE_LIMIT_BETTER_PER_DAY'] = 5 
app.config['RATE_LIMIT_BEST_PER_DAY'] = 2   
app.config['RATE_LIMIT_LLM_SYNONYM_PER_DAY'] = 5 # New LLM Synonym Limit
app.config['RATE_LIMIT_LLM_REWRITE_PER_DAY'] = 5 # New LLM Rewrite Limit

# It's good practice to allow overriding from environment variables
import os
app.config['RATE_LIMIT_FAST_PER_DAY'] = int(os.environ.get('RATE_LIMIT_FAST_PER_DAY', app.config['RATE_LIMIT_FAST_PER_DAY']))
app.config['RATE_LIMIT_BETTER_PER_DAY'] = int(os.environ.get('RATE_LIMIT_BETTER_PER_DAY', app.config['RATE_LIMIT_BETTER_PER_DAY']))
app.config['RATE_LIMIT_BEST_PER_DAY'] = int(os.environ.get('RATE_LIMIT_BEST_PER_DAY', app.config['RATE_LIMIT_BEST_PER_DAY']))
app.config['RATE_LIMIT_LLM_SYNONYM_PER_DAY'] = int(os.environ.get('RATE_LIMIT_LLM_SYNONYM_PER_DAY', app.config['RATE_LIMIT_LLM_SYNONYM_PER_DAY']))
app.config['RATE_LIMIT_LLM_REWRITE_PER_DAY'] = int(os.environ.get('RATE_LIMIT_LLM_REWRITE_PER_DAY', app.config['RATE_LIMIT_LLM_REWRITE_PER_DAY']))

# Initialize RateLimiter
# We can initialize it directly here, or use Flask's extension pattern if it gets more complex.
# For now, direct instantiation is fine. It will use current_app.config.
# The RateLimiter class itself will create the redis client using the URL from app.config
rate_limiter = RateLimiter()
# --- End Rate Limiter Configuration ---


# Configure cache
# Using SimpleCache: In-memory cache per process. Suitable for development
# or single-process deployments. For multi-process/multi-server, consider
# RedisCache, MemcachedCache, or FileSystemCache.
cache_config = {
    "CACHE_TYPE": "SimpleCache",  # Use SimpleCache for now
    "CACHE_DEFAULT_TIMEOUT": 300 # Default timeout 5 minutes (adjust as needed)
}
app.config.from_mapping(cache_config) # This will merge with existing app.config
cache = Cache(app) # Initialize Cache with the app

# Import routes after initializing the app, cache, and celery
# We will create the routes.py file next
from app import routes # Ensure tasks.py is created and imported by Celery

    