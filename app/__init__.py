from dotenv import load_dotenv # Add this line
load_dotenv() # Add this line to load .env file

import redis # Add redis import for RateLimiter
from flask import Flask
from flask_caching import Cache # Import Cache
from celery import Celery, Task # Import Celery and Task
from app.rate_limiter import RateLimiter # Import RateLimiter
import os # Added for environment variables
import sys # Added for stderr warning output
import sentry_sdk # Add Sentry SDK
from sentry_sdk.integrations.flask import FlaskIntegration # Add Sentry Flask integration
from sentry_sdk.integrations.celery import CeleryIntegration # Add Sentry Celery integration

# Initialize the Flask application
app = Flask(__name__)

# --- Sentry Configuration ---
SENTRY_DSN = os.environ.get('SENTRY_DSN')
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            FlaskIntegration(),
            CeleryIntegration()
        ],
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        # Adjust as needed for production.
        traces_sample_rate=1.0,
        # Set profiles_sample_rate to 1.0 to profile 100%
        # of sampled transactions.
        # Adjust as needed for production.
        profiles_sample_rate=1.0,
        # Consider sending PII data if appropriate for your application
        # send_default_pii=True
    )
    print("INFO: Sentry initialized.", file=sys.stderr)
else:
    if os.environ.get('FLASK_ENV', 'production').lower() == 'production':
        print("WARNING: SENTRY_DSN is not set in a production-like environment. Sentry will not capture errors.", file=sys.stderr)
    else:
        print("INFO: SENTRY_DSN is not set. Sentry will not capture errors. This is acceptable for local development without Sentry.", file=sys.stderr)
# --- End Sentry Configuration ---

# --- Production/Development Configuration ---
# For SECRET_KEY, it's crucial to set this in your production environment.
# For development, you can use a default, but warn if it's not set.
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
if not app.config['SECRET_KEY'] and os.environ.get('FLASK_ENV', 'production').lower() == 'production': # Default to 'production' if FLASK_ENV not set
    # In a real production setup, you might prefer to fail hard here.
    # For now, we'll print an error and proceed with a default if it's somehow missed in prod,
    # but the goal is that the environment variable *must* be set.
    print("CRITICAL WARNING: SECRET_KEY is not set in a production-like environment. Please set the SECRET_KEY environment variable.", file=sys.stderr)
    # Fallback to a clearly insecure key if not set, to avoid crashing, but this is NOT for production.
    app.config['SECRET_KEY'] = 'ensure-this-is-overridden-in-production' 
elif not app.config['SECRET_KEY']:
    app.config['SECRET_KEY'] = 'dev-secret-key-for-flask-CHANGE-ME-AND-SET-VIA-ENV' 
    print("INFO: SECRET_KEY is not set via environment variable. Using a default development key. For production, set the SECRET_KEY environment variable.", file=sys.stderr)

# Set DEBUG mode from environment variable FLASK_DEBUG. Defaults to False if not set or not 'true'.
app.config['DEBUG'] = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
if app.config['DEBUG']:
    print("INFO: Flask DEBUG mode is ON.", file=sys.stderr)
else:
    print("INFO: Flask DEBUG mode is OFF.", file=sys.stderr)
# --- End Production/Development Configuration ---

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
app.config['RATE_LIMIT_BETTER_PER_DAY'] = 10 
app.config['RATE_LIMIT_BEST_PER_DAY'] = 5   
app.config['RATE_LIMIT_LLM_SYNONYM_PER_DAY'] = 5 # New LLM Synonym Limit
app.config['RATE_LIMIT_LLM_REWRITE_PER_DAY'] = 5 # New LLM Rewrite Limit

# It's good practice to allow overriding from environment variables
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
# Switch to RedisCache for production
CACHE_TYPE = os.environ.get('CACHE_TYPE', 'RedisCache') # Default to RedisCache for prod
CACHE_REDIS_URL = os.environ.get('CACHE_REDIS_URL', app.config.get('CELERY_BROKER_URL', 'redis://localhost:6379/1'))

if CACHE_TYPE == 'SimpleCache' and os.environ.get('FLASK_ENV', 'production').lower() == 'production':
    print("WARNING: CACHE_TYPE is 'SimpleCache' in a production-like environment. Consider using 'RedisCache' or another distributed cache.", file=sys.stderr)

cache_config = {
    "CACHE_TYPE": CACHE_TYPE,
    "CACHE_DEFAULT_TIMEOUT": int(os.environ.get('CACHE_DEFAULT_TIMEOUT', 300)), # Default timeout 5 minutes
    "CACHE_REDIS_URL": CACHE_REDIS_URL
}
app.config.from_mapping(cache_config) # This will merge with existing app.config
cache = Cache(app) # Initialize Cache with the app
if CACHE_TYPE == 'RedisCache':
    print(f"INFO: Cache configured with RedisCache at {CACHE_REDIS_URL}", file=sys.stderr)
else:
    print(f"INFO: Cache configured with {CACHE_TYPE}", file=sys.stderr)

# Import routes after initializing the app, cache, and celery
# We will create the routes.py file next
from app import routes # Ensure tasks.py is created and imported by Celery

    