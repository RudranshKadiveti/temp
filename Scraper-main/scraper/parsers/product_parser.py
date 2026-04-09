from bs4 import BeautifulSoup
from scraper.parsers.schemas import ProductSchema
from scraper.parsers.base_parser import BaseParser
import re

class ProductParser(BaseParser):
    def parse(self) -> dict:
        soup = BeautifulSoup(self.html, 'html.parser')
        
        # Heuristics based extraction
        name_tag = soup.find('h1')
        name = name_tag.get_text(strip=True) if name_tag else ""
        
        # Example price extraction
        price_tag = soup.find(text=re.compile(r'\$\d+'))
        price = price_tag.strip() if price_tag else ""
        
        # Example rating extraction
        rating_tag = soup.find(class_=re.compile(r'rating|stars', re.I))
        rating = rating_tag.get_text(strip=True) if rating_tag else ""
        
        schema = ProductSchema(
            name=name,
            price=price,
            rating=rating,
            url=self.url,
            source="scraper"
        )
        return schema.dict()
