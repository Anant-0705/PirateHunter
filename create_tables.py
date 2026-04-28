import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from piratehunt.db.models import Base
from piratehunt.config import settings
from piratehunt.db.engine import _async_database_url

async def main():
    engine = create_async_engine(_async_database_url(settings.database_url))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        print("Created missing tables!")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
