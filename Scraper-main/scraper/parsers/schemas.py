from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime

class ProductSchema(BaseModel):
    type: str = "product"
    name: str = ""
    price: str = ""
    currency: str = ""
    rating: str = ""
    reviews_count: str = ""
    availability: str = ""
    url: str
    source: str
    scraped_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

class ArticleSchema(BaseModel):
    type: str = "article"
    title: str = ""
    author: str = ""
    publish_date: str = ""
    content: str = ""
    tags: List[str] = []
    url: str
    source: str
    scraped_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
