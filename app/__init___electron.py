"""
Flask app initialization for Electron version using LocalTaskQueue instead of Celery
"""

from dotenv import load_dotenv
load_dotenv()

from flask import Flask
from flask_caching import Cache
from app.local_task_queue import init_local_task_queue, get_local_task_queue
import os
import sys
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration
import logging
import re

# Initialize the Flask application
flask_app = Flask(__name__)

# --- Sentry Configuration ---
SENTRY_DSN = os.environ.get('SENTRY_DSN')
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[FlaskIntegration()],
        traces_sample_rate=1.0,
        profiles_sample_rate=1.0,
    )
    print("INFO: Sentry initialized.", file=sys.stderr)
else:
    if os.environ.get('FLASK_ENV', 'production').lower() == 'production':
        print("WARNING: SENTRY_DSN is not set in a production-like environment. Sentry will not capture errors.", file=sys.stderr)
    else:
        print("INFO: SENTRY_DSN is not set. Sentry will not capture errors. This is acceptable for local development without Sentry.", file=sys.stderr)

# --- Production/Development Configuration ---
flask_app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
if not flask_app.config['SECRET_KEY'] and os.environ.get('FLASK_ENV', 'production').lower() == 'production':
    print("CRITICAL WARNING: SECRET_KEY is not set in a production-like environment. Please set the SECRET_KEY environment variable.", file=sys.stderr)
    flask_app.config['SECRET_KEY'] = 'ensure-this-is-overridden-in-production' 
elif not flask_app.config['SECRET_KEY']:
    flask_app.config['SECRET_KEY'] = 'dev-secret-key-for-flask-CHANGE-ME-AND-SET-VIA-ENV' 
    print("INFO: SECRET_KEY is not set via environment variable. Using a default development key. For production, set the SECRET_KEY environment variable.", file=sys.stderr)

# Set DEBUG mode from environment variable FLASK_DEBUG. Defaults to False if not set or not 'true'.
flask_app.config['DEBUG'] = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
if flask_app.config['DEBUG']:
    print("INFO: Flask DEBUG mode is ON.", file=sys.stderr)
else:
    print("INFO: Flask DEBUG mode is OFF.", file=sys.stderr)

# --- LocalTaskQueue Configuration (replaces Celery) ---
# Detect if running in Electron environment
ELECTRON_MODE = os.environ.get('ELECTRON_RUN_AS_NODE') == '1'
ELECTRON_APP_PATH = os.environ.get('ELECTRON_APP_PATH', '.')

if ELECTRON_MODE:
    print("INFO: Running in Electron mode, using LocalTaskQueue instead of Celery.", file=sys.stderr)
    
    # Configure paths for Electron
    flask_app.config['BASE_DIR'] = ELECTRON_APP_PATH
    flask_app.config['USE_LOCAL_STORAGE'] = True
    
    # Initialize LocalTaskQueue
    db_path = os.path.join(ELECTRON_APP_PATH, 'tasks.db')
    max_workers = int(os.environ.get('LOCAL_TASK_WORKERS', '3'))
    local_task_queue = init_local_task_queue(max_workers=max_workers, db_path=db_path)
    
    print(f"INFO: LocalTaskQueue initialized with {max_workers} workers, database: {db_path}", file=sys.stderr)
else:
    # Use original Celery configuration for web mode
    from celery import Celery, Task
    
    CELERY_BROKER_URL = 'redis://localhost:6379/0'
    CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'

    def make_celery(app_instance):
        celery_app = Celery(
            app_instance.import_name,
            broker=app_instance.config['CELERY_BROKER_URL'],
            backend=app_instance.config['CELERY_RESULT_BACKEND'],
            include=['app.tasks']
        )
        celery_app.conf.update(app_instance.config)

        class ContextTask(Task):
            abstract = True
            def __call__(self, *args, **kwargs):
                with app_instance.app_context():
                    return self.run(*args, **kwargs)

        celery_app.Task = ContextTask
        return celery_app

    flask_app.config.update(
        CELERY_BROKER_URL=CELERY_BROKER_URL,
        CELERY_RESULT_BACKEND=CELERY_RESULT_BACKEND
    )
    celery = make_celery(flask_app)
    print("INFO: Celery initialized for web mode.", file=sys.stderr)

# --- Application-level rate limiting removed intentionally ---

# --- Cache Configuration ---
CACHE_TYPE = os.environ.get('CACHE_TYPE', 'FileSystemCache' if ELECTRON_MODE else 'RedisCache')

if ELECTRON_MODE:
    # Use FileSystemCache for Electron (no Redis dependency)
    cache_dir = os.path.join(ELECTRON_APP_PATH, 'cache')
    os.makedirs(cache_dir, exist_ok=True)
    cache_config = {
        "CACHE_TYPE": "FileSystemCache",
        "CACHE_DIR": cache_dir,
        "CACHE_DEFAULT_TIMEOUT": int(os.environ.get('CACHE_DEFAULT_TIMEOUT', '300')),
    }
    print(f"INFO: Cache configured with FileSystemCache at {cache_dir}", file=sys.stderr)
else:
    # Use RedisCache for web mode
    CACHE_REDIS_URL = os.environ.get('CACHE_REDIS_URL', 'redis://localhost:6379/1')
    cache_config = {
        "CACHE_TYPE": "RedisCache",
        "CACHE_DEFAULT_TIMEOUT": int(os.environ.get('CACHE_DEFAULT_TIMEOUT', '300')),
        "CACHE_REDIS_URL": CACHE_REDIS_URL
    }
    print(f"INFO: Cache configured with RedisCache at {CACHE_REDIS_URL}", file=sys.stderr)

flask_app.config.from_mapping(cache_config)
cache = Cache(flask_app)

# Alias for compatibility with existing imports/decorators
app = flask_app

# --- Logging redaction to avoid leaking secrets ---
class _SecretRedactionFilter(logging.Filter):
    _API_RE = re.compile(r'(\bapi_key\b\s*[:=]\s*[\"\'])(.*?)([\"\'])', re.IGNORECASE)
    _AUTH_RE = re.compile(r'(\bAuthorization\b\s*[:=]\s*[\"\'])(.*?)([\"\'])', re.IGNORECASE)

    def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
        try:
            msg = record.getMessage()
            if not msg:
                return True
            redacted = self._API_RE.sub(r'\1***\3', msg)
            redacted = self._AUTH_RE.sub(r'\1***\3', redacted)
            if redacted != msg:
                record.msg = redacted
                record.args = ()
        except Exception:
            pass
        return True

_filter = _SecretRedactionFilter()
for logger_name in (None, 'werkzeug'):
    lg = logging.getLogger(logger_name) if logger_name else flask_app.logger
    try:
        lg.addFilter(_filter)
    except Exception:
        pass

# Import routes after initializing the app, cache, and task system.
# In Electron mode, import the Electron-specific routes directly from this module
if ELECTRON_MODE:
    from . import routes_electron  # noqa: F401
else:
    from . import routes  # noqa: F401

# Expose a WSGI-friendly alias to avoid any name confusion
application = flask_app