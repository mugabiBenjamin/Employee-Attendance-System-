import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.sql import text
from sqlalchemy.ext.declarative import declarative_base
from app.core.config import settings
import logging
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from sqlalchemy.exc import OperationalError, DatabaseError
import aioredis
from aioredis.exceptions import ConnectionError, RedisError
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

async def set_cache(key: str, value: dict, ttl: int):
    try:
        if redis:
            await redis.set(key, json.dumps(value), expire=ttl)
            logger.debug(f"Cache set for key: {key} with TTL {ttl}s")
    except RedisError as e:
        logger.error(f"Error setting cache for key {key}: {str(e)}")

async def invalidate_cache_prefix(prefix: str):
    try:
        if redis:
            keys = await redis.keys(f"{prefix}:*")
            if keys:
                await redis.delete(*keys)
                logger.debug(f"Invalidated cache for prefix: {prefix}")
    except RedisError as e:
        logger.error(f"Error invalidating cache for prefix {prefix}: {str(e)}")

# Individual enum creation SQL statements
ENUM_CREATION_SQLS = [
    """
    DO $$ BEGIN
        CREATE TYPE attendance_status AS ENUM (
            'present', 'absent', 'late', 'early_departure', 'on_leave', 'half_day', 'sick'
        );
    EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """,
    """
    DO $$ BEGIN
        CREATE TYPE leave_request_status AS ENUM (
            'draft', 'under_review', 'approved', 'rejected', 'cancelled', 'completed'
        );
    EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """,
    """
    DO $$ BEGIN
        CREATE TYPE leave_type AS ENUM (
            'annual', 'sick', 'maternity', 'paternity', 'emergency', 'unpaid',
            'casual', 'compensatory', 'bereavement', 'leave_of_absence', 'public_holiday'
        );
    EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """,
    """
    DO $$ BEGIN
        CREATE TYPE correction_status AS ENUM (
            'draft', 'under_review', 'approved', 'rejected', 'cancelled', 'completed'
        );
    EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """,
    """
    DO $$ BEGIN
        CREATE TYPE system_action AS ENUM (
            'INSERT', 'UPDATE', 'DELETE', 'LOGIN', 'LOGOUT', 'CLOCK_IN', 'CLOCK_OUT',
            'password_change', 'profile_update', 'data_export', 'data_import',
            'assign_role', 'revoke_role', 'view_report', 'approve_leave',
            'reject_leave', 'create_department', 'delete_department'
        );
    EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """,
    """
    DO $$ BEGIN
        CREATE TYPE employee_type AS ENUM (
            'full_time', 'part_time', 'contract', 'intern', 'temporary'
        );
    EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """,
    """
    DO $$ BEGIN
        CREATE TYPE shift_type AS ENUM (
            'morning', 'afternoon', 'night', 'flexible', 'split'
        );
    EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """
]

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

# Initialize database tables and enums with retry logic
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
        # Create enums
        for enum_sql in ENUM_CREATION_SQLS:
            await conn.execute(text(enum_sql))
        
        # Ensure job_title column in users table
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
        
        # Create tables
        await conn.run_sync(Base.metadata.create_all)
        
        # Create materialized views
        for view_sql in MATERIALIZED_VIEW_SQLS:
            await conn.execute(text(view_sql))
        
        logger.info("Database initialized with enums, tables, and materialized view")

# Periodically refresh materialized view with retry logic
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((OperationalError, DatabaseError)),
    before_sleep=lambda retry_state: logger.warning(
        f"Materialized view refresh attempt {retry_state.attempt_number} failed, retrying..."
    )
)
async def refresh_materialized_view():
    while True:
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY attendance_summary"))
                await session.commit()
                logger.info("Materialized view 'attendance_summary' refreshed successfully")
        except Exception as e:
            logger.error(f"Error refreshing materialized view: {str(e)}")
            raise
        # Wait for the configured interval
        await asyncio.sleep(settings.MATERIALIZED_VIEW_REFRESH_INTERVAL)

# Start the materialized view refresh task
async def start_materialized_view_refresh():
    logger.info("Starting materialized view refresh task")
    asyncio.create_task(refresh_materialized_view())