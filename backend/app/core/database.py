import asyncio
import json
import logging
from typing import AsyncGenerator, Optional
import redis.asyncio as redis
from redis.exceptions import ConnectionError, RedisError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.sql import text
from sqlalchemy.orm import declarative_base
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from sqlalchemy.exc import OperationalError, DatabaseError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.core.config import settings
from app.core.enums import (
    AttendanceStatus, LeaveRequestStatus, LeaveType,
    CorrectionStatus, OvertimeStatus, EmployeeType, ShiftType, SystemAction,
    RoleName, PermissionGroup, Permission
)

logger = logging.getLogger(__name__)

Base = declarative_base()

if not settings.DATABASE_URL.startswith("postgresql+asyncpg://"):
    logger.error("DATABASE_URL must use asyncpg driver (e.g., postgresql+asyncpg://)")
    raise ValueError("DATABASE_URL must use asyncpg driver (e.g., postgresql+asyncpg://)")

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((OperationalError, DatabaseError)),
    before_sleep=lambda retry_state: logger.warning(
        f"Database connection attempt {retry_state.attempt_number} failed, retrying..."
    )
)
async def create_engine_with_retry():
    return create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG, future=True)

engine = None
AsyncSessionLocal = None
redis_client = None

def ensure_session_factory():
    if AsyncSessionLocal is None:
        raise RuntimeError("Database not initialized. Call startup() before using DB operations.")
    return AsyncSessionLocal

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((ConnectionError, RedisError)),
    before_sleep=lambda retry_state: logger.warning(
        f"Redis connection attempt {retry_state.attempt_number} failed, retrying..."
    )
)
async def initialize_redis():
    global redis_client
    redis_client = redis.from_url(settings.REDIS_URL)
    await redis_client.ping()
    logger.info("Redis client initialized")

async def initialize_engine_and_session():
    global engine, AsyncSessionLocal
    try:
        engine = await create_engine_with_retry()
        AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
        try:
            await initialize_redis()
            logger.info("Database engine, session factory, and Redis initialized")
        except Exception as redis_error:
            logger.warning(f"Redis initialization failed: {redis_error}")
            logger.info("Database engine initialized (Redis disabled)")
    except Exception as e:
        logger.error(f"Failed to initialize database: {str(e)}")
        raise

async def startup():
    """Initialize database engine and Redis on application startup."""
    await initialize_engine_and_session()
    logger.info("Application startup completed")

async def shutdown():
    """Close database engine and Redis connections on application shutdown."""
    global engine, redis_client
    try:
        if engine:
            await engine.dispose()
            logger.info("Database engine closed")
        if redis_client:
            await redis_client.aclose()
            logger.info("Redis connection closed")
    except Exception as e:
        logger.error(f"Error during shutdown: {str(e)}")

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    session_factory = ensure_session_factory()
    async with session_factory() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            raise
        finally:
            await session.close()

# Cache utility functions
async def get_cache(key: str) -> Optional[dict]:
    try:
        if redis_client:
            cached = await redis_client.get(key)
            if cached:
                return json.loads(cached)
        return None
    except RedisError as e:
        logger.error(f"Error retrieving cache: {str(e)}")
        return None

async def set_cache(key: str, value: dict, ttl: int) -> None:
    try:
        if redis_client:
            await redis_client.set(key, json.dumps(value), ex=ttl)
    except RedisError as e:
        logger.error(f"Error setting cache: {str(e)}")

async def invalidate_cache_prefix(prefix: str) -> None:
    try:
        if redis_client:
            async for key in redis_client.scan_iter(f"{prefix}:*"):
                await redis_client.delete(key)
    except RedisError as e:
        logger.error(f"Error invalidating cache: {str(e)}")

async def is_key_cached(key: str) -> bool:
    try:
        if redis_client:
            return bool(await redis_client.exists(key))
        return False
    except RedisError as e:
        return False

# Enum SQLAlchemy type mapping
ENUM_CLASS_LIST = [
    (AttendanceStatus, "attendance_status"),
    (LeaveRequestStatus, "leave_request_status"),
    (LeaveType, "leave_type"),
    (CorrectionStatus, "correction_status"),
    (OvertimeStatus, "overtime_status"),
    (EmployeeType, "employee_type"),
    (ShiftType, "shift_type"),
    (SystemAction, "system_action"),
    (RoleName, "role_name"),
    (PermissionGroup, "permission_group"),
    (Permission, "permission"),
]

ENUM_CLASSES = {
    name: PG_ENUM(
        *[member.value for member in enum_class],
        name=name,
        create_type=False
    )
    for (enum_class, name) in ENUM_CLASS_LIST
}

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((OperationalError, DatabaseError))
)
async def background_refresh_materialized_views():
    """Refresh all materialized views."""
    materialized_views = ["leave_request_summary"]
    if AsyncSessionLocal is None:
        return
    
    async with AsyncSessionLocal() as session:
        try:
            for view_name in materialized_views:
                view_exists = await session.execute(text(f"""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables 
                        WHERE table_name = '{view_name}' AND table_type = 'VIEW'
                    );
                """))
                if view_exists.scalar():
                    await session.execute(text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view_name}"))
            await session.commit()
        except Exception:
            await session.rollback()
            raise

async def start_background_refresh():
    asyncio.create_task(background_refresh_materialized_views())

async def validate_enum_value(enum_class, value: str) -> bool:
    try:
        if hasattr(enum_class, '__members__'):
            return value in [member.value for member in enum_class]
        return value in enum_class if hasattr(enum_class, '__contains__') else False
    except Exception:
        return False

async def get_enum_values(enum_class) -> list[str]:
    try:
        if hasattr(enum_class, '__members__'):
            return [member.value for member in enum_class]
        elif hasattr(enum_class, '__iter__'):
            return list(enum_class)
        return []
    except Exception:
        return []