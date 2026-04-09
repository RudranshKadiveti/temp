import re
from bs4 import BeautifulSoup

class ContentDetector:
    @staticmethod
    def detect(url: str, html: str) -> str:
        """Classify page into product, listing, article, or unknown."""
        url_lower = url.lower()
        
        if '/product/' in url_lower or '/item/' in url_lower or '/p/' in url_lower:
            return "product"
        if '/category/' in url_lower or '/list' in url_lower or '/shop' in url_lower:
            return "listing"
        if '/article/' in url_lower or '/blog/' in url_lower or '/news/' in url_lower:
            return "article"
            
        soup = BeautifulSoup(html, 'html.parser')
        
        # Check JSON-LD
        json_ld_tags = soup.find_all('script', type='application/ld+json')
        for tag in json_ld_tags:
            if tag.string and 'Product' in tag.string:
                return "product"
            if tag.string and ('Article' in tag.string or 'NewsArticle' in tag.string or 'BlogPosting' in tag.string):
                return "article"
                
        # Fallback to DOM Structure Heuristics
        if soup.find(class_=re.compile(r'add-to-cart|price', re.I)):
            return "product"
        if soup.find('article') or soup.find(class_=re.compile(r'author|byline', re.I)):
            return "article"
        if soup.find(class_=re.compile(r'product-list|grid', re.I)):
            return "listing"
            
        return "unknown"
