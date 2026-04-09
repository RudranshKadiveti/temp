from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, String, JSON, DateTime
from datetime import datetime
from scraper.config.settings import settings

Base = declarative_base()

class ScrapedItem(Base):
    __tablename__ = 'scraped_items'
    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, unique=True, index=True)
    type = Column(String, index=True)
    data = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

engine = create_async_engine(settings.POSTGRES_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def save_item(url: str, item_type: str, data: dict):
    async with AsyncSessionLocal() as session:
        # Simple UPSERT / Integrity check handling not fully implemented for brevity
        # in production, use on_conflict_do_update
        existing = await session.execute(
            "SELECT id FROM scraped_items WHERE url = :url", {"url": url}
        )
        if not existing.scalar():
            item = ScrapedItem(url=url, type=item_type, data=data)
            session.add(item)
            await session.commit()
