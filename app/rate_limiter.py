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
            'best': current_app.config.get('RATE_LIMIT_BEST_PER_DAY', 2),
            'llm_synonym': current_app.config.get('RATE_LIMIT_LLM_SYNONYM_PER_DAY', 5),
            'llm_rewrite': current_app.config.get('RATE_LIMIT_LLM_REWRITE_PER_DAY', 5)
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
            # This mode is not configured for rate limiting (e.g., not 'better' or 'best')
            # Depending on policy, you could allow or deny. Allowing seems safer.
            current_app.logger.warn(f"RateLimiter: No limit explicitly configured for analysis mode '{analysis_mode}'. Allowing request from {ip_address}.")
            return True # Default to allow if mode is unknown to prevent accidental blocking

        today_iso = datetime.date.today().isoformat()
        key = f"ratelimit:{ip_address}:{analysis_mode}:{today_iso}"

        try:
            current_count_val = self.redis_client.get(key)
            if current_count_val is None:
                current_count = 0
            else:
                current_count = int(current_count_val)

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

    def get_current_usage(self, ip_address: str) -> dict:
        """
        Gets the current usage counts for all rate-limited modes for a given IP.
        Returns a dictionary like {'fast': count, 'better': count, 'best': count}.
        """
        usage = {}
        today_iso = datetime.date.today().isoformat()
        configured_limits = self.get_limits() # To know which modes to check

        for mode in configured_limits.keys():
            key = f"ratelimit:{ip_address}:{mode}:{today_iso}"
            try:
                count_val = self.redis_client.get(key)
                if count_val is None:
                    usage[mode] = 0
                else:
                    usage[mode] = int(count_val)
            except redis.exceptions.ConnectionError as e:
                current_app.logger.error(f"RateLimiter: Redis connection error in get_current_usage for {mode}: {e}. Returning 0 for this mode.")
                usage[mode] = 0 # Assume 0 usage if Redis fails for a key
            except Exception as e:
                current_app.logger.error(f"RateLimiter: Error in get_current_usage for {mode}: {e}. Returning 0 for this mode.")
                usage[mode] = 0
        return usage

    def reset_limits_for_ip(self, ip_address: str) -> bool:
        """
        Resets all rate limits for a given IP address for the current day.

        Args:
            ip_address (str): The IP address for which to reset limits.

        Returns:
            bool: True if keys were found and attempted to be deleted, False otherwise.
        """
        today_iso = datetime.date.today().isoformat()
        # Pattern to match all rate limit keys for the IP for today
        # Covers all modes: fast, better, best, llm_synonym, llm_rewrite, etc.
        key_pattern = f"ratelimit:{ip_address}:*:{today_iso}"
        
        keys_to_delete = []
        try:
            # Ensure redis_client is available
            if not hasattr(self, 'redis_client') or self.redis_client is None:
                current_app.logger.error("RateLimiter: Redis client not available for reset_limits_for_ip.")
                return False

            # Fetch all keys matching the pattern
            # Note: SCAN is generally preferred over KEYS in production for large datasets
            # to avoid blocking, but for a limited number of rate limit keys, KEYS might be acceptable.
            # If performance becomes an issue, consider implementing SCAN.
            keys_to_delete = self.redis_client.keys(key_pattern)
            
            if keys_to_delete:
                num_deleted = self.redis_client.delete(*keys_to_delete)
                current_app.logger.info(f"RateLimiter: Reset {num_deleted} rate limit entries for IP {ip_address} using pattern {key_pattern}. Keys deleted: {keys_to_delete}")
                return True
            else:
                current_app.logger.info(f"RateLimiter: No rate limit entries found to reset for IP {ip_address} with pattern {key_pattern}.")
                return False
        except redis.exceptions.ConnectionError as e:
            current_app.logger.error(f"RateLimiter: Redis connection error during limit reset for IP {ip_address}: {e}")
            return False
        except Exception as e:
            current_app.logger.error(f"RateLimiter: Error during limit reset for IP {ip_address}: {e}")
            return False

# Global instance (optional, can be managed by Flask app factory)
# rate_limiter_instance = RateLimiter() 