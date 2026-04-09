from scraper.utils.logger import logger
from scraper.parsers.content_detector import ContentDetector
from scraper.parsers.product_parser import ProductParser
from scraper.parsers.article_parser import ArticleParser
from scraper.parsers.listing_parser import ListingParser
from scraper.storage.db import save_item
from scraper.storage.elastic import elastic_storage
from scraper.storage.file_storage import save_html
from scraper.utils.hashing import hash_url
from scraper.core.queue_manager import queue_manager

class DataPipeline:
    @staticmethod
    async def process(url: str, html: str):
        # 1. Save Raw HTML
        await save_html(url, html)
        
        # 2. Detect Content Type
        content_type = ContentDetector.detect(url, html)
        logger.info(f"Detected {content_type} for URL: {url}")
        
        # 3. Parse Based on Type
        data = None
        if content_type == "product":
            parser = ProductParser(html, url)
            data = parser.parse()
        elif content_type == "article":
            parser = ArticleParser(html, url)
            data = parser.parse()
        elif content_type == "listing":
            parser = ListingParser(html, url)
            data = parser.parse()
            # Push listing URLs back to queue
            for link in data.get("extracted_urls", []):
                # Ensure fully qualified URL (omitted full urljoin for brevity, 
                # assumes relative URLs are handled in crawler or here)
                await queue_manager.add_job(link, priority=1)
        else:
            logger.warning(f"Unknown content type for {url}")
            return
            
        # 4. Storage & Indexing (if valid structured data)
        if data and content_type in ["product", "article"]:
            try:
                # PostgreSQl
                await save_item(url, content_type, data)
                # Elasticsearch
                doc_id = hash_url(url)
                await elastic_storage.index_document(doc_id, data)
                logger.debug(f"Successfully processed and stored: {url}")
            except Exception as e:
                logger.error(f"Failed to store data for {url}: {e}")
                
pipeline = DataPipeline()
