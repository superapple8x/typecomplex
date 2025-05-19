import redis
import datetime
from flask import current_app

class RateLimiter:
    def __init__(self, redis_client=None):
        if redis_client:
            self.redis_client = redis_client
        else:
            # This fallback is mostly for direct instantiation outside Flask app context.
            # In a Flask app, we expect redis_client to be provided.
            try:
                self.redis_client = redis.StrictRedis.from_url(current_app.config['RATE_LIMITER_REDIS_URL'])
            except RuntimeError: # Outside of application context
                 # This is a fallback for cases where current_app is not available
                 # and no client was passed. You might need a default URL or raise an error.
                self.redis_client = redis.StrictRedis(host='localhost', port=6379, db=0) # Default, adjust as needed

    def get_limits(self):
        return {
            'fast': current_app.config.get('RATE_LIMIT_FAST_PER_DAY', 10),
            'better': current_app.config.get('RATE_LIMIT_BETTER_PER_DAY', 5),
            'best': current_app.config.get('RATE_LIMIT_BEST_PER_DAY', 2)
        }

    def check_and_update_limit(self, ip_address: str, analysis_mode: str) -> bool:
        """
        Checks if the given IP address and analysis mode are within limits.
        If allowed, increments the count and sets an expiry.

        Returns:
            bool: True if allowed, False if rate-limited.
        """
        if not analysis_mode:
            # Or handle as an error, but for now, if no mode specified, don't limit.
            current_app.logger.warn(f"RateLimiter: No analysis mode specified. Allowing request from {ip_address}.")
            return True

        # Ensure analysis_mode is lowercase for consistency in keys and limit fetching
        analysis_mode = analysis_mode.lower()
        
        limits = self.get_limits()
        limit_for_mode = limits.get(analysis_mode)

        if limit_for_mode is None:
            # This mode is not configured for rate limiting (e.g., might be a typo or new unconfigured mode)
            current_app.logger.warn(f"RateLimiter: No limit explicitly configured for analysis mode '{analysis_mode}'. Allowing request from {ip_address}.")
            return True # Default to allow if mode is unknown to prevent accidental blocking

        today_iso = datetime.date.today().isoformat()
        key = f"ratelimit:{ip_address}:{analysis_mode}:{today_iso}"

        try:
            current_count = self.redis_client.get(key)
            if current_count is None:
                current_count = 0
            else:
                current_count = int(current_count)

            if current_count >= limit_for_mode:
                current_app.logger.info(f"Rate limit exceeded for {ip_address} on mode '{analysis_mode}'. Count: {current_count}, Limit: {limit_for_mode}")
                return False
            else:
                # Increment and set expiry
                # Use a pipeline for atomicity
                pipe = self.redis_client.pipeline()
                pipe.incr(key)
                # Calculate seconds until end of day for expiry
                now = datetime.datetime.now()
                midnight = now.replace(hour=23, minute=59, second=59, microsecond=999999)
                seconds_until_eod = int((midnight - now).total_seconds()) + 1 # +1 to ensure it covers the whole day
                pipe.expire(key, seconds_until_eod) # Expires at the end of the current day
                pipe.execute()
                current_app.logger.info(f"Rate limit check passed for {ip_address} on mode '{analysis_mode}'. New count: {current_count + 1}, Limit: {limit_for_mode}")
                return True
        except redis.exceptions.ConnectionError as e:
            current_app.logger.error(f"RateLimiter: Redis connection error: {e}. Allowing request as a fallback.")
            # Fallback: If Redis is down, do we block or allow? Allowing is often preferred.
            return True
        except Exception as e:
            current_app.logger.error(f"RateLimiter: Error during rate limit check: {e}. Allowing request as a fallback.")
            return True # Fallback for other unexpected errors

# Global instance (optional, can be managed by Flask app factory)
# rate_limiter_instance = RateLimiter() 