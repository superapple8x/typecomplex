import os

# Workers
workers = int(os.environ.get('GUNICORN_WORKERS', '2')) # Default to 2 for 4GB RAM, configurable
worker_class = os.environ.get('GUNICORN_WORKER_CLASS', 'sync') # e.g., 'sync', 'gevent', 'meinheld_worker'

# Binding
# Bind to port from PORT env var (used by Flask app.run), or GUNICORN_PORT, or default to 5001
# Gunicorn itself doesn't use FLASK_RUN_PORT, so we use PORT or a Gunicorn specific one.
_port = os.environ.get('PORT', os.environ.get('GUNICORN_PORT', '5001'))
bind = f"0.0.0.0:{_port}"

# Logging
# Log to stdout/stderr by default. In production, you might write to files:
# accesslog = '/var/log/gunicorn/access.log'
# errorlog = '/var/log/gunicorn/error.log'
# Ensure these directories/files are writable by the Gunicorn process.
accesslog = '-' # Log access to stdout
errorlog = '-'  # Log errors to stderr
loglevel = os.environ.get('GUNICORN_LOGLEVEL', 'info') # 'debug', 'info', 'warning', 'error', 'critical'

# Preload app for better memory usage with multiple workers
# This loads the application code before forking worker processes.
# Advantages: Can save memory (resources shared via copy-on-write).
# Disadvantages:
#   - Any resources initialized at import time that are not fork-safe (e.g., some DB connections,
#     background threads that don't respawn correctly) can cause issues.
#   - Can make zero-downtime restarts more complex if not handled carefully.
# Test thoroughly if you enable this. Your app seems to load ML models at startup,
# so --preload could be beneficial for memory but needs testing.
preload_app = True

# Timeout settings
timeout = int(os.environ.get('GUNICORN_TIMEOUT', '120')) # Workers silent for more than this are killed.
keepalive = int(os.environ.get('GUNICORN_KEEPALIVE', '5')) # Seconds to wait for requests on a Keep-Alive connection.

# Example of setting environment variables for the Flask app directly from Gunicorn config
# This is an alternative to setting them in the shell environment where Gunicorn runs.
# raw_env = [
#     f"FLASK_ENV={os.environ.get('FLASK_ENV', 'production')}",
#     f"FLASK_DEBUG={os.environ.get('FLASK_DEBUG', 'false')}",
#     # If SECRET_KEY is managed outside (e.g., systemd unit, Docker env), no need to set here.
#     # If you want Gunicorn to enforce it if not set elsewhere:
#     # f"SECRET_KEY={os.environ.get('SECRET_KEY', 'default_gunicorn_secret_key_if_not_externally_set')}"
# ]

# --- Sanity checks and info logging ---
# This print statement will appear when Gunicorn starts and reads this config.
print(f"[gunicorn.conf.py] Effective settings: workers={workers}, class='{worker_class}', bind='{bind}', loglevel='{loglevel}'")
if preload_app:
    print("[gunicorn.conf.py] --preload_app is ENABLED (experimental for your app, test thoroughly)")
else:
    print("[gunicorn.conf.py] --preload_app is DISABLED")

# Check critical Flask environment variables
flask_env = os.environ.get('FLASK_ENV', 'not_set (will default to production in app)')
flask_debug = os.environ.get('FLASK_DEBUG', 'not_set (will default to false in app)')
secret_key_status = "SET in environment" if os.environ.get('SECRET_KEY') else "NOT SET in environment (app will use default or warn)"

print(f"[gunicorn.conf.py] Flask env check: FLASK_ENV='{flask_env}', FLASK_DEBUG='{flask_debug}', SECRET_KEY status: {secret_key_status}")

# Note: To use this file, run: gunicorn -c gunicorn.conf.py "app:app"
# Ensure "app:app" correctly points to your Flask application instance.
# If your app instance is `myapp` in `project/run.py`, it would be `run:myapp`.
# Based on previous findings, "app:app" (referring to app object in app/__init__.py) should be correct. 