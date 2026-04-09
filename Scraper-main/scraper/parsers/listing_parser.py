from scraper.parsers.base_parser import BaseParser
from bs4 import BeautifulSoup
import re

class ListingParser(BaseParser):
    def parse(self) -> dict:
        soup = BeautifulSoup(self.html, 'html.parser')
        # Simple extraction of possible product links
        links = []
        for a_tag in soup.find_all('a', href=True):
            if re.search(r'/product/|/item/', a_tag['href']):
                links.append(a_tag['href'])
        
        return {
            "type": "listing",
            "extracted_urls": list(set(links)),
            "url": self.url
        }
