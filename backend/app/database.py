from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
import redis.asyncio as aioredis
from motor.motor_asyncio import AsyncIOMotorClient
from app.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG, pool_size=20, max_overflow=10)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

redis_client: aioredis.Redis | None = None
mongodb_client: AsyncIOMotorClient | None = None
mongodb_db = None


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_redis():
    global redis_client
    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)


async def get_redis() -> aioredis.Redis:
    return redis_client


async def init_mongodb():
    global mongodb_client, mongodb_db
    mongodb_client = AsyncIOMotorClient(settings.MONGODB_URL)
    # Extract database name from connection URL or use default
    db_name = settings.MONGODB_URL.split('/')[-1].split('?')[0]
    mongodb_db = mongodb_client[db_name]


def get_mongodb():
    """Get MongoDB database instance."""
    return mongodb_db


async def close_mongodb():
    global mongodb_client
    if mongodb_client:
        mongodb_client.close()


async def init_db():
    async with engine.begin() as conn:
        from app.models import user, model_config, agent, agent_model, task, log, api_key, skill, memory, system_setting, chat, thinking_protocol, agent_protocol, autonomous_run  # noqa
        await conn.run_sync(Base.metadata.create_all)

        # ── Inline migrations for new columns ──
        await conn.execute(
            text("""
                ALTER TABLE agents ADD COLUMN IF NOT EXISTS self_thinking BOOLEAN DEFAULT FALSE;
            """)
        )
