import asyncio
from typing import AsyncGenerator, Optional
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.sql import text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from app.core.config import settings
from app.core.enums import (
    AttendanceStatus, LeaveRequestStatus, LeaveType,
    CorrectionStatus, OvertimeStatus, EmployeeType, ShiftType, SystemAction,
    RoleName
)
import logging
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from sqlalchemy.exc import OperationalError, DatabaseError
from redis import asyncio as aioredis
from redis.exceptions import ConnectionError, RedisError
import json

logger = logging.getLogger(__name__)

# Create SQLAlchemy Base
Base = declarative_base()

# Validate DATABASE_URL for async driver
if not settings.DATABASE_URL.startswith("postgresql+asyncpg://"):
    logger.error("DATABASE_URL must use asyncpg driver (e.g., postgresql+asyncpg://)")
    raise ValueError("DATABASE_URL must use asyncpg driver (e.g., postgresql+asyncpg://)")

# Create async engine with retry logic
@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((OperationalError, DatabaseError)),
    before_sleep=lambda retry_state: logger.warning(
        f"Database connection attempt {retry_state.attempt_number} failed, retrying..."
    )
)
async def create_engine_with_retry():
    return create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DEBUG,
        future=True
    )

# Initialize engine (to be awaited at startup)
engine = None

# Create async session factory
AsyncSessionLocal = None

# Redis client
redis = None

# Initialize Redis with retry logic
@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((ConnectionError, RedisError)),
    before_sleep=lambda retry_state: logger.warning(
        f"Redis connection attempt {retry_state.attempt_number} failed, retrying..."
    )
)
async def initialize_redis():
    global redis
    redis = await aioredis.create_redis_pool(settings.REDIS_URL)
    logger.info("Redis client initialized")

async def initialize_engine_and_session():
    global engine, AsyncSessionLocal
    try:
        engine = await create_engine_with_retry()
        AsyncSessionLocal = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
        await initialize_redis()
        logger.info("Database engine, session factory, and Redis initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database or Redis: {str(e)}")
        raise

# Startup and shutdown helpers
async def startup():
    """Initialize database engine, session factory, and Redis on application startup."""
    await initialize_engine_and_session()
    await init_db()
    logger.info("Application startup completed: database and Redis initialized")

async def shutdown():
    """Close database engine and Redis connections on application shutdown."""
    global engine, redis
    try:
        if engine:
            await engine.dispose()
            logger.info("Database engine closed")
        if redis:
            redis.close()
            await redis.wait_closed()
            logger.info("Redis connection closed")
    except Exception as e:
        logger.error(f"Error during shutdown: {str(e)}")

# Database dependency for FastAPI
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

# Cache utility functions
async def get_cache(key: str) -> Optional[dict]:
    try:
        if redis:
            cached = await redis.get(key)
            if cached:
                logger.debug(f"Cache hit for key: {key}")
                return json.loads(cached)
        return None
    except RedisError as e:
        logger.error(f"Error retrieving cache for key {key}: {str(e)}")
        return None

async def set_cache(key: str, value: dict, ttl: int) -> None:
    try:
        if redis:
            await redis.set(key, json.dumps(value), expire=ttl)
            logger.debug(f"Cache set for key: {key} with TTL {ttl}s")
    except RedisError as e:
        logger.error(f"Error setting cache for key {key}: {str(e)}")

async def invalidate_cache_prefix(prefix: str) -> None:
    try:
        if redis:
            keys = await redis.keys(f"{prefix}:*")
            if keys:
                await redis.delete(*keys)
                logger.debug(f"Invalidated cache for prefix: {prefix}")
    except RedisError as e:
        logger.error(f"Error invalidating cache for prefix {prefix}: {str(e)}")

async def is_key_cached(key: str) -> bool:
    try:
        if redis:
            result = await redis.exists(key)
            return bool(result)
        return False
    except RedisError as e:
        logger.error(f"Error checking cache existence for key {key}: {str(e)}")
        return False

# Enum types list (for creating DB types)
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
]

# Enum SQLAlchemy type mapping (for model columns)
ENUM_CLASSES = {
    name: PG_ENUM(enum_class, name=name, create_type=False)
    for (enum_class, name) in ENUM_CLASS_LIST
}

# Materialized view and index creation SQL statements
MATERIALIZED_VIEW_SQLS = [
    """
    CREATE MATERIALIZED VIEW IF NOT EXISTS attendance_summary AS
    SELECT u.user_id,
        u.employee_id,
        CONCAT(u.first_name, ' ', u.last_name) AS full_name,
        d.department_name,
        ar.date,
        ar.status,
        ar.total_hours,
        ar.overtime_hours,
        ar.clock_in_time,
        ar.clock_out_time
    FROM users u
        JOIN user_departments ud ON u.user_id = ud.user_id AND ud.is_primary = TRUE
        JOIN departments d ON ud.department_id = d.department_id
        LEFT JOIN attendance_records ar ON u.user_id = ar.user_id
    WHERE u.is_active = TRUE AND u.deleted_at IS NULL
    WITH DATA;
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_attendance_summary_user_date ON attendance_summary(user_id, date)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_attendance_summary_department ON attendance_summary(department_name)
    """
]

# Initialize database tables, enums, and views
@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((OperationalError, DatabaseError)),
    before_sleep=lambda retry_state: logger.warning(
        f"Database initialization attempt {retry_state.attempt_number} failed, retrying..."
    )
)
async def init_db():
    async with engine.begin() as conn:
        # Create enums from Python Enum classes
        for enum_class, enum_name in ENUM_CLASS_LIST:
            values = [member.value for member in enum_class]
            await conn.execute(text(f"""
                DO $$ BEGIN
                    CREATE TYPE {enum_name} AS ENUM ({', '.join(f"'{v}'" for v in values)});
                EXCEPTION WHEN duplicate_object THEN NULL; END $$;
            """))

        # Ensure job_title column exists
        await conn.execute(text("""
            DO $$ BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'users' AND column_name = 'job_title'
                ) THEN
                    ALTER TABLE users ADD COLUMN job_title VARCHAR(100);
                END IF;
            END $$;
        """))

        # Create all tables for registered models
        await conn.run_sync(Base.metadata.create_all)

        # Create materialized views and indexes
        for view_sql in MATERIALIZED_VIEW_SQLS:
            await conn.execute(text(view_sql))

        logger.info("Database initialized with enums, tables, and materialized views")

# Background task for refreshing materialized view
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((OperationalError, DatabaseError)),
    before_sleep=lambda retry_state: logger.warning(
        f"Materialized view refresh attempt {retry_state.attempt_number} failed, retrying..."
    )
)
async def background_refresh_materialized_view():
    async with AsyncSessionLocal() as session:
        try:
            await session.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY attendance_summary"))
            await session.commit()
            logger.info("Materialized view 'attendance_summary' refreshed successfully")
        except Exception as e:
            logger.error(f"Error refreshing materialized view: {str(e)}")
            await session.rollback()
            raise

async def start_background_refresh():
    logger.info("Starting materialized view refresh task")
    asyncio.create_task(background_refresh_materialized_view())