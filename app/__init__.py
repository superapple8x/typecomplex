from flask import Flask
from flask_caching import Cache # Import Cache

# Initialize the Flask application
app = Flask(__name__)

# Configure cache
# Using SimpleCache: In-memory cache per process. Suitable for development
# or single-process deployments. For multi-process/multi-server, consider
# RedisCache, MemcachedCache, or FileSystemCache.
cache_config = {
    "CACHE_TYPE": "SimpleCache",  # Use SimpleCache for now
    "CACHE_DEFAULT_TIMEOUT": 300 # Default timeout 5 minutes (adjust as needed)
}
app.config.from_mapping(cache_config)
cache = Cache(app) # Initialize Cache with the app

# Import routes after initializing the app and cache
# We will create the routes.py file next
from app import routes