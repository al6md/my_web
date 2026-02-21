import time
import logging
from functools import wraps
from typing import Callable
import prometheus_client as prom

logger = logging.getLogger(__name__)

# Prometheus metrics
REQUEST_TIME = prom.Histogram(
    'recommendation_request_duration_seconds',
    'Time spent generating recommendations',
    ['algorithm', 'user_segment']
)

CACHE_HITS = prom.Counter(
    'cache_hits_total',
    'Total cache hits',
    ['cache_type']
)

ALGORITHM_CALLS = prom.Counter(
    'algorithm_calls_total',
    'Total algorithm calls',
    ['algorithm', 'status']
)


def track_performance(algorithm_name: str):
    """Decorator to track algorithm performance"""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            
            try:
                # We need to await if the function is async
                result = await func(*args, **kwargs)
                
                elapsed = time.perf_counter() - start_time
                REQUEST_TIME.labels(
                    algorithm=algorithm_name,
                    user_segment='active' # Placeholder for segmentation logic
                ).observe(elapsed)
                
                ALGORITHM_CALLS.labels(
                    algorithm=algorithm_name,
                    status='success'
                ).inc()
                
                # logger.debug(f"[{algorithm_name}] Completed in {elapsed*1000:.2f}ms")
                
                return result
                
            except Exception as e:
                elapsed = time.perf_counter() - start_time
                ALGORITHM_CALLS.labels(
                    algorithm=algorithm_name,
                    status='error'
                ).inc()
                
                logger.error(f"[{algorithm_name}] Error after {elapsed*1000:.2f}ms: {e}")
                raise
        
        return wrapper
    return decorator
