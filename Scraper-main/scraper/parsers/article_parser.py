from bs4 import BeautifulSoup
from scraper.parsers.schemas import ArticleSchema
from scraper.parsers.base_parser import BaseParser
import re

class ArticleParser(BaseParser):
    def parse(self) -> dict:
        soup = BeautifulSoup(self.html, 'html.parser')
        
        title_tag = soup.find('h1')
        title = title_tag.get_text(strip=True) if title_tag else ""
        
        author_tag = soup.find(class_=re.compile(r'author|byline', re.I))
        author = author_tag.get_text(strip=True) if author_tag else ""
        
        # Usually articles use <article> tag or specific class names
        content_tag = soup.find('article') or soup.find(class_=re.compile(r'content|post', re.I))
        content = content_tag.get_text(separator=' ', strip=True) if content_tag else ""
        
        schema = ArticleSchema(
            title=title,
            author=author,
            content=content,
            url=self.url,
            source="scraper"
        )
        return schema.dict()
