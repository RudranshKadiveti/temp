import asyncio
from scraper.core.queue_manager import queue_manager
from scraper.utils.logger import logger

class Scheduler:
    def __init__(self):
        # Example seeds
        self.seed_urls = [
            "https://books.toscrape.com/",
            "https://news.ycombinator.com/",
        ]

    async def start(self):
        logger.info("Starting Scheduler...")
        # Add seeds initially
        for url in self.seed_urls:
            await queue_manager.add_job(url)
            
        # Optional: Add recurring scheduling logic here
        while True:
            # Example: reload seeds every 24 hours
            await asyncio.sleep(86400)
            for url in self.seed_urls:
                await queue_manager.add_job(url)

scheduler = Scheduler()
