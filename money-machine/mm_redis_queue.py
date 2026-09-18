"""Redis-backed queue manager for Money Machine.

Provides job queuing, retries, throttling, and deduplication.

Queues:
- audit_queue: Website audit jobs
- crawl_queue: Web crawling jobs
- screenshot_queue: Screenshot capture jobs
- email_verification_queue: Email verification jobs
- retry_queue: Failed jobs for retry

State:
- rate_limits: Provider rate limit tracking
- provider_cooldowns: Provider cooldown tracking
- temporary_cache: Short-lived cache
- deduplication: Job deduplication keys
"""
import json
import hashlib
import time
from typing import Optional, Any

REDIS_URL = "redis://localhost:6379/0"

QUEUE_NAMES = [
    'audit_queue',
    'crawl_queue',
    'screenshot_queue',
    'email_verification_queue',
    'retry_queue',
]


def get_redis():
    """Get Redis connection."""
    import redis
    return redis.Redis.from_url(REDIS_URL, decode_responses=True)


def enqueue(queue: str, job: dict, dedupe_key: str = None) -> bool:
    """Add a job to a queue.
    
    Args:
        queue: Queue name
        job: Job data dict
        dedupe_key: Optional deduplication key
    
    Returns:
        True if job was enqueued, False if duplicate
    """
    r = get_redis()
    
    if dedupe_key:
        # Check deduplication
        if r.exists(f"dedupe:{dedupe_key}"):
            return False
        r.setex(f"dedupe:{dedupe_key}", 3600, "1")  # 1 hour TTL
    
    job['_enqueued_at'] = time.time()
    r.lpush(queue, json.dumps(job))
    return True


def dequeue(queue: str, timeout: int = 30) -> Optional[dict]:
    """Get next job from queue (blocking).
    
    Args:
        queue: Queue name
        timeout: Block timeout in seconds
    
    Returns:
        Job dict or None if timeout
    """
    r = get_redis()
    result = r.brpop(queue, timeout=timeout)
    if result:
        _, data = result
        return json.loads(data)
    return None


def dequeue_nonblock(queue: str) -> Optional[dict]:
    """Get next job from queue (non-blocking)."""
    r = get_redis()
    data = r.rpop(queue)
    if data:
        return json.loads(data)
    return None


def queue_length(queue: str) -> int:
    """Get queue length."""
    r = get_redis()
    return r.llen(queue)


def all_queue_lengths() -> dict:
    """Get lengths of all queues."""
    r = get_redis()
    return {q: r.llen(q) for q in QUEUE_NAMES}


def retry_job(queue: str, job: dict, max_retries: int = 3) -> bool:
    """Retry a failed job.
    
    Args:
        queue: Original queue name
        job: Job data
        max_retries: Maximum retry attempts
    
    Returns:
        True if job was queued for retry, False if max retries exceeded
    """
    retries = job.get('_retries', 0) + 1
    if retries > max_retries:
        return False
    
    job['_retries'] = retries
    job['_last_retry'] = time.time()
    r = get_redis()
    r.lpush('retry_queue', json.dumps(job))
    return True


def throttle_check(provider: str, max_per_minute: int = 10) -> bool:
    """Check if a provider is rate limited.
    
    Args:
        provider: Provider name
        max_per_minute: Max calls per minute
    
    Returns:
        True if allowed, False if throttled
    """
    r = get_redis()
    key = f"ratelimit:{provider}"
    current = r.get(key)
    
    if current is None:
        r.setex(key, 60, "1")
        return True
    
    if int(current) >= max_per_minute:
        return False
    
    r.incr(key)
    return True


def set_cooldown(provider: str, seconds: int = 60):
    """Set a provider cooldown."""
    r = get_redis()
    r.setex(f"cooldown:{provider}", seconds, "1")


def is_cooldown(provider: str) -> bool:
    """Check if a provider is in cooldown."""
    r = get_redis()
    return r.exists(f"cooldown:{provider}") > 0


def cache_set(key: str, value: Any, ttl: int = 300):
    """Set a cache value."""
    r = get_redis()
    r.setex(f"cache:{key}", ttl, json.dumps(value))


def cache_get(key: str) -> Optional[Any]:
    """Get a cache value."""
    r = get_redis()
    data = r.get(f"cache:{key}")
    if data:
        return json.loads(data)
    return None


def dedupe_check(key: str) -> bool:
    """Check if a deduplication key exists."""
    r = get_redis()
    return r.exists(f"dedupe:{key}") > 0


def dedupe_set(key: str, ttl: int = 3600):
    """Set a deduplication key."""
    r = get_redis()
    r.setex(f"dedupe:{key}", ttl, "1")


def status_report() -> str:
    """Generate queue status report."""
    r = get_redis()
    lengths = all_queue_lengths()
    
    lines = ["=== Redis Queue Status ==="]
    for q, length in lengths.items():
        lines.append(f"  {q:30s} {length:3d} pending")
    
    lines.append("")
    lines.append("Provider throttling:")
    for key in r.scan_iter("ratelimit:*"):
        provider = key.split(":")[1]
        val = r.get(key)
        ttl = r.ttl(key)
        lines.append(f"  {provider:15s} {val}/min (TTL {ttl}s)")
    
    lines.append("")
    lines.append("Provider cooldowns:")
    for key in r.scan_iter("cooldown:*"):
        provider = key.split(":")[1]
        ttl = r.ttl(key)
        lines.append(f"  {provider:15s} cooldown {ttl}s remaining")
    
    return '\n'.join(lines)
