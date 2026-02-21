import redis
import json
import asyncio
from typing import Any, Optional
from ..config import settings

class RedisCacheManager:
    """
    Robust Redis Cache Manager for high-speed retrieval of cached recommendations.
    """
    def __init__(self, redis_url: str = settings.REDIS_URL):
        try:
            self.client = redis.from_url(redis_url, decode_responses=True)
            self.redis_available = True
            # Simple check
            self.client.ping()
        except Exception as e:
            print(f"Warning: Redis not available at {redis_url}. Caching disabled. {e}")
            self.redis_available = False
            self.client = None

    async def get(self, key: str) -> Optional[Any]:
        """Async wrapper for getting from Redis."""
        if not self.redis_available:
            return None
        
        loop = asyncio.get_running_loop()
        try:
            # Redis-py is blocking, so run in executor
            data = await loop.run_in_executor(None, self.client.get, key)
            if data:
                return json.loads(data)
        except Exception as e:
            print(f"Redis READ Error: {e}")
        return None

    async def set(self, key: str, value: Any, ttl: int = settings.CACHE_TTL):
        """Async wrapper for setting to Redis."""
        if not self.redis_available:
            return
            
        loop = asyncio.get_running_loop()
        try:
            json_val = json.dumps(value)
            await loop.run_in_executor(None, self.client.setex, key, ttl, json_val)
        except Exception as e:
            print(f"Redis WRITE Error: {e}")

    def get_sync(self, key: str) -> Optional[Any]:
        """Synchronous get for non-async parts."""
        if not self.redis_available: return None
        try:
            data = self.client.get(key)
            return json.loads(data) if data else None
        except: return None

    def set_sync(self, key: str, value: Any, ttl: int = settings.CACHE_TTL):
        """Synchronous set."""
        if not self.redis_available: return
        try:
            self.client.setex(key, ttl, json.dumps(value))
        except: pass

# Global instance
cache_manager = RedisCacheManager()
