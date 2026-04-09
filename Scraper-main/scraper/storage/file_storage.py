import os
import aiofiles
from scraper.config.settings import settings
from scraper.utils.hashing import hash_url

async def save_html(url: str, html: str):
    """Save raw HTML asynchronously to the file system."""
    if not os.path.exists(settings.HTML_STORAGE_PATH):
        os.makedirs(settings.HTML_STORAGE_PATH)
        
    filename = f"{hash_url(url)}.html"
    filepath = os.path.join(settings.HTML_STORAGE_PATH, filename)
    
    async with aiofiles.open(filepath, mode='w', encoding='utf-8') as f:
        await f.write(html)
        
    return filepath
