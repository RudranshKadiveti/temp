from elasticsearch import AsyncElasticsearch
from scraper.config.settings import settings
from scraper.utils.logger import logger

class ElasticStorage:
    def __init__(self):
        self.index_name = "scraped_data"
        self._es = None
        
    @property
    def es(self):
        if self._es is None:
            self._es = AsyncElasticsearch([settings.ELASTICSEARCH_URL])
        return self._es

    async def init_index(self):
        if not await self.es.indices.exists(index=self.index_name):
            await self.es.indices.create(index=self.index_name)
            logger.info(f"Created Elasticsearch index: {self.index_name}")

    async def index_document(self, doc_id: str, data: dict):
        try:
            await self.es.index(index=self.index_name, id=doc_id, document=data)
        except Exception as e:
            logger.error(f"Failed to index document {doc_id} in ES: {e}")

    async def close(self):
        if self._es is not None:
            await self._es.close()

elastic_storage = ElasticStorage()
