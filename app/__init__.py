import os

# If running under Electron, only expose the Flask app object here to avoid
# circular imports. Modules should import cache/rate_limiter from
# `app.__init___electron` directly in Electron mode.
if os.environ.get('ELECTRON_RUN_AS_NODE') == '1':
    from .__init___electron import app as app  # type: ignore
    celery = None
else:
    from dotenv import load_dotenv
    load_dotenv()

    import redis  # noqa: F401
    from flask import Flask
    from flask_caching import Cache
    from celery import Celery, Task
    # Application-level rate limiting removed. No RateLimiter.
    import sys
    import sentry_sdk
    from sentry_sdk.integrations.flask import FlaskIntegration
    from sentry_sdk.integrations.celery import CeleryIntegration

    app = Flask(__name__)

    SENTRY_DSN = os.environ.get('SENTRY_DSN')
    if SENTRY_DSN:
        sentry_sdk.init(
            dsn=SENTRY_DSN,
            integrations=[FlaskIntegration(), CeleryIntegration()],
            traces_sample_rate=1.0,
            profiles_sample_rate=1.0,
        )
        print("INFO: Sentry initialized.", file=sys.stderr)
    else:
        if os.environ.get('FLASK_ENV', 'production').lower() == 'production':
            print("WARNING: SENTRY_DSN is not set in a production-like environment. Sentry will not capture errors.", file=sys.stderr)
        else:
            print("INFO: SENTRY_DSN is not set. Sentry will not capture errors. This is acceptable for local development without Sentry.", file=sys.stderr)

    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
    if not app.config['SECRET_KEY'] and os.environ.get('FLASK_ENV', 'production').lower() == 'production':
        print("CRITICAL WARNING: SECRET_KEY is not set in a production-like environment. Please set the SECRET_KEY environment variable.", file=sys.stderr)
        app.config['SECRET_KEY'] = 'ensure-this-is-overridden-in-production'
    elif not app.config['SECRET_KEY']:
        app.config['SECRET_KEY'] = 'dev-secret-key-for-flask-CHANGE-ME-AND-SET-VIA-ENV'
        print("INFO: SECRET_KEY is not set via environment variable. Using a default development key. For production, set the SECRET_KEY environment variable.", file=sys.stderr)

    app.config['DEBUG'] = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    if app.config['DEBUG']:
        print("INFO: Flask DEBUG mode is ON.", file=sys.stderr)
    else:
        print("INFO: Flask DEBUG mode is OFF.", file=sys.stderr)

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

    app.config.update(
        CELERY_BROKER_URL=CELERY_BROKER_URL,
        CELERY_RESULT_BACKEND=CELERY_RESULT_BACKEND
    )
    celery = make_celery(app)

    # Application-level rate limiting removed. Provider limits only.

    # Cache
    from flask_caching import Cache as _Cache
    CACHE_TYPE = os.environ.get('CACHE_TYPE', 'RedisCache')
    CACHE_REDIS_URL = os.environ.get('CACHE_REDIS_URL', app.config.get('CELERY_BROKER_URL', 'redis://localhost:6379/1'))
    cache_config = {
        "CACHE_TYPE": CACHE_TYPE,
        "CACHE_DEFAULT_TIMEOUT": int(os.environ.get('CACHE_DEFAULT_TIMEOUT', 300)),
        "CACHE_REDIS_URL": CACHE_REDIS_URL,
    }
    app.config.from_mapping(cache_config)
    cache = _Cache(app)
    if CACHE_TYPE == 'RedisCache':
        print(f"INFO: Cache configured with RedisCache at {CACHE_REDIS_URL}", file=sys.stderr)
    else:
        print(f"INFO: Cache configured with {CACHE_TYPE}", file=sys.stderr)

    # Import routes
    from app import routes