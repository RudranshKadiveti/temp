import asyncio
import aiohttp
from typing import Optional
from scraper.config.settings import settings
from scraper.utils.logger import logger
from scraper.crawlers.anti_bot import get_headers
from scraper.core.queue_manager import queue_manager
from scraper.pipelines.data_pipeline import pipeline

class AsyncCrawler:
    def __init__(self):
        self.semaphore = asyncio.Semaphore(settings.CONCURRENCY)
        
    async def fetch(self, session: aiohttp.ClientSession, url: str) -> Optional[str]:
        async with self.semaphore:
            headers = get_headers() if settings.USER_AGENT_ROTATION_ENABLED else {}
            try:
                # Add delay or rotation logic here using async sleep
                await asyncio.sleep(0.5)
                
                async with session.get(
                    url, 
                    headers=headers, 
                    timeout=settings.REQUEST_TIMEOUT
                ) as response:
                    # Check status
                    if response.status == 200:
                        return await response.text()
                    elif response.status in [403, 429]:
                        logger.warning(f"Blocked or rate-limited on {url}: status {response.status}")
                        return None
                    else:
                        logger.error(f"Failed to fetch {url}: status {response.status}")
                        return None
            except asyncio.TimeoutError:
                logger.error(f"Timeout while fetching {url}")
                return None
            except Exception as e:
                logger.error(f"Error fetching {url}: {str(e)}")
                return None

    async def run(self):
        logger.info("Starting Async Crawler Worker...")
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=settings.CONCURRENCY)
        ) as session:
            while True:
                job = await queue_manager.get_job()
                if not job:
                    # Queue is empty, wait
                    await asyncio.sleep(1)
                    continue

                url = job['url']
                retry_count = job.get('retry_count', 0)
                
                logger.debug(f"Fetched job from queue: {url}")
                
                # Deduplication logic handled in queue_manager
                await queue_manager.mark_visited(url)
                
                html = await self.fetch(session, url)
                if html:
                    # Push to processing pipeline
                    asyncio.create_task(pipeline.process(url, html))
                else:
                    if retry_count < settings.RETRY_COUNT:
                        logger.debug(f"Retrying URL: {url} ({retry_count + 1})")
                        await queue_manager.redis.lpush(
                            queue_manager.queue_name, 
                            str({"url": url, "retry_count": retry_count + 1}).replace("'", '"')
                        )
                    else:
                        logger.warning(f"Max retries reached for {url}")
                        await queue_manager.add_to_dlq(url, "Max retries reached")
