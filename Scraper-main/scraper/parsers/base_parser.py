from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseParser(ABC):
    def __init__(self, html: str, url: str):
        self.html = html
        self.url = url
        
    @abstractmethod
    def parse(self) -> Dict[str, Any]:
        """Parse raw HTML and return structured dictionary."""
        pass
