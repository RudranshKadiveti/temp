import json
from redis.asyncio import Redis
from scraper.config.settings import settings
from scraper.utils.logger import logger

class QueueManager:
    def __init__(self):
        self.queue_name = "crawl_jobs"
        self.dead_letter_queue = "crawl_jobs_dlq"
        self.visited_set = "visited_urls"
        self._redis = None
        
    @property
    def redis(self):
        if self._redis is None:
            self._redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        return self._redis
        
    async def add_job(self, url: str, priority: int = 0):
        """Add job to queue if not visited."""
        # Simple deduplication
        if await self.redis.sismember(self.visited_set, url):
            logger.debug(f"URL already visited: {url}")
            return False
            
        job_data = {"url": url, "retry_count": 0}
        await self.redis.lpush(self.queue_name, json.dumps(job_data))
        logger.info(f"Added job for URL: {url}")
        return True

    async def get_job(self):
        """Get next job from queue."""
        result = await self.redis.brpop(self.queue_name, timeout=2)
        if result:
            _, item = result
            return json.loads(item)
        return None

    async def mark_visited(self, url: str):
        """Mark URL as visited."""
        await self.redis.sadd(self.visited_set, url)

    async def add_to_dlq(self, url: str, error: str):
        """Add failed job to DLQ."""
        job_data = {"url": url, "error": error}
        await self.redis.lpush(self.dead_letter_queue, json.dumps(job_data))
        logger.warning(f"Added to DLQ: {url}")

    async def close(self):
        if self._redis is not None:
            await self._redis.close()

queue_manager = QueueManager()
