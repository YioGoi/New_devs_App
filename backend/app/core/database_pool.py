import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import AsyncAdaptedQueuePool
import logging
from ..config import settings

logger = logging.getLogger(__name__)

class DatabasePool:
    def __init__(self):
        self.engine = None
        self.session_factory = None
        self._initialized = False

    def _database_url(self) -> str:
        database_url = settings.database_url
        if database_url.startswith("postgresql://"):
            return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return database_url
        
    async def initialize(self):
        """Initialize database connection pool"""
        if self._initialized and self.session_factory:
            return
        try:
            database_url = self._database_url()

            self.engine = create_async_engine(
                database_url,
                poolclass=AsyncAdaptedQueuePool,
                pool_size=settings.database_pool_size,
                max_overflow=settings.database_max_overflow,
                pool_pre_ping=True,
                pool_recycle=settings.database_pool_recycle,
                echo=False,
            )
            
            self.session_factory = async_sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            self._initialized = True
            
            logger.info("✅ Database connection pool initialized")
            
        except Exception as e:
            logger.error(f"❌ Database pool initialization failed: {e}")
            self.engine = None
            self.session_factory = None
            self._initialized = False
    
    async def close(self):
        """Close database connections"""
        if self.engine:
            await self.engine.dispose()
        self.engine = None
        self.session_factory = None
        self._initialized = False
    
    def get_session(self) -> AsyncSession:
        """Get database session from pool"""
        if not self.session_factory:
            raise Exception("Database pool not initialized")
        return self.session_factory()

# Global database pool instance
db_pool = DatabasePool()

async def get_db_session() -> AsyncSession:
    """Dependency to get database session"""
    await db_pool.initialize()
    async with db_pool.get_session() as session:
        yield session
