import asyncio
from typing import AsyncGenerator, Optional
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.sql import text
from sqlalchemy.orm import declarative_base
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from app.core.config import settings
from app.core.enums import (
    AttendanceStatus, LeaveRequestStatus, LeaveType,
    CorrectionStatus, OvertimeStatus, EmployeeType, ShiftType, SystemAction,
    RoleName, PermissionGroup, Permission
)
import logging
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from sqlalchemy.exc import OperationalError, DatabaseError
import redis.asyncio as redis
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

def ensure_session_factory():
    """Ensure AsyncSessionLocal is initialized before use."""
    if AsyncSessionLocal is None:
        raise RuntimeError(
            "Database not initialized. Make sure to call startup() before using database operations."
        )
    return AsyncSessionLocal

# Redis client
redis_client = None

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
    global redis_client
    redis_client = redis.from_url(settings.REDIS_URL)
    # Test the connection
    await redis_client.ping()
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
        try:
            await initialize_redis()
            logger.info("Database engine, session factory, and Redis initialized")
        except Exception as redis_error:
            logger.warning(f"Redis initialization failed, continuing without caching: {redis_error}")
            logger.info("Database engine and session factory initialized (Redis disabled)")
    except Exception as e:
        logger.error(f"Failed to initialize database: {str(e)}")
        raise

# Startup and shutdown helpers
async def startup():
    """Initialize database engine, session factory, and Redis on application startup."""
    await initialize_engine_and_session()
    await init_db()
    logger.info("Application startup completed: database and Redis initialized")

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

# Database dependency for FastAPI
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    session_factory = ensure_session_factory()
    async with session_factory() as session:
        logger.debug(f"New database session created: {id(session)}")
        try:
            yield session
        except Exception as e:
            logger.error(f"Error in session {id(session)}: {str(e)}")
            await session.rollback()
            raise
        finally:
            logger.debug(f"Closing session {id(session)}")
            await session.close()

# Cache utility functions
async def get_cache(key: str) -> Optional[dict]:
    try:
        if redis_client:
            cached = await redis_client.get(key)
            if cached:
                logger.debug(f"Cache hit for key: {key}")
                return json.loads(cached)
        return None
    except RedisError as e:
        logger.error(f"Error retrieving cache for key {key}: {str(e)}")
        return None

async def set_cache(key: str, value: dict, ttl: int) -> None:
    try:
        if redis_client:
            await redis_client.set(key, json.dumps(value), ex=ttl)
            logger.debug(f"Cache set for key: {key} with TTL {ttl}s")
    except RedisError as e:
        logger.error(f"Error setting cache for key {key}: {str(e)}")

async def invalidate_cache_prefix(prefix: str) -> None:
    try:
        if redis_client:
            async for key in redis_client.scan_iter(f"{prefix}:*"):
                await redis_client.delete(key)
            logger.debug(f"Invalidated cache for prefix: {prefix}")
    except RedisError as e:
        logger.error(f"Error invalidating cache for prefix {prefix}: {str(e)}")

async def is_key_cached(key: str) -> bool:
    try:
        if redis_client:
            result = await redis_client.exists(key)
            return bool(result)
        return False
    except RedisError as e:
        logger.error(f"Error checking cache existence for key {key}: {str(e)}")
        return False

# Complete enum types list (including all enums from the enums file)
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

# Enum SQLAlchemy type mapping (for model columns)
ENUM_CLASSES = {
    name: PG_ENUM(
        *[member.value for member in enum_class],
        name=name,
        create_type=False
    )
    for (enum_class, name) in ENUM_CLASS_LIST
}

# Materialized view and table creation SQL statements
MATERIALIZED_VIEW_SQLS = [
    # Drop and create leave_request_summary materialized view
    "DROP MATERIALIZED VIEW IF EXISTS leave_request_summary;",
    """
    CREATE MATERIALIZED VIEW leave_request_summary AS
    SELECT 
        lr.leave_id AS leave_request_id,
        u.user_id,
        u.employee_id,
        CONCAT(u.first_name, ' ', u.last_name) AS employee_name,
        d.department_name,
        lr.leave_type::leave_type,
        lr.status::leave_request_status,
        lr.start_date,
        lr.end_date,
        lr.days_requested AS total_days,
        lr.reason,
        lr.created_at,
        lr.updated_at
    FROM leave_requests lr
        JOIN users u ON lr.user_id = u.user_id
        JOIN user_departments ud ON u.user_id = ud.user_id AND ud.is_primary = TRUE
        JOIN departments d ON ud.department_id = d.department_id
    WHERE lr.deleted_at IS NULL
    WITH DATA;
    """,
    "CREATE INDEX IF NOT EXISTS idx_leave_request_summary_user ON leave_request_summary(user_id);",
    "CREATE INDEX IF NOT EXISTS idx_leave_request_summary_status ON leave_request_summary(status);",
    "CREATE INDEX IF NOT EXISTS idx_leave_request_summary_dates ON leave_request_summary(start_date, end_date);",
    # Ensure attendance_summary table exists
    """
    CREATE TABLE IF NOT EXISTS attendance_summary (
        user_id INTEGER NOT NULL,
        employee_id VARCHAR(20),
        full_name TEXT,
        department_name VARCHAR(100),
        attendance_summary_date DATE NOT NULL,
        status attendance_status,
        total_hours NUMERIC(4,2),
        overtime_hours NUMERIC(4,2),
        clock_in_time TIMESTAMP WITH TIME ZONE,
        clock_out_time TIMESTAMP WITH TIME ZONE,
        supervisor_id INTEGER,
        supervisor_name TEXT,
        is_active BOOLEAN DEFAULT TRUE NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE,
        updated_at TIMESTAMP WITH TIME ZONE,
        CONSTRAINT pk_attendance_summary PRIMARY KEY (user_id, attendance_summary_date),
        CONSTRAINT unique_user_summary_date UNIQUE (user_id, attendance_summary_date)
    );
    """,
    # Ensure all required columns exist in attendance_summary
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'attendance_summary' AND column_name = 'employee_id'
        ) THEN
            ALTER TABLE attendance_summary ADD COLUMN employee_id VARCHAR(20);
        END IF;
    END $$;
    """,
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'attendance_summary' AND column_name = 'full_name'
        ) THEN
            ALTER TABLE attendance_summary ADD COLUMN full_name TEXT;
        END IF;
    END $$;
    """,
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'attendance_summary' AND column_name = 'department_name'
        ) THEN
            ALTER TABLE attendance_summary ADD COLUMN department_name VARCHAR(100);
        END IF;
    END $$;
    """,
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'attendance_summary' AND column_name = 'status'
        ) THEN
            ALTER TABLE attendance_summary ADD COLUMN status attendance_status;
        END IF;
    END $$;
    """,
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'attendance_summary' AND column_name = 'total_hours'
        ) THEN
            ALTER TABLE attendance_summary ADD COLUMN total_hours NUMERIC(4,2);
        END IF;
    END $$;
    """,
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'attendance_summary' AND column_name = 'overtime_hours'
        ) THEN
            ALTER TABLE attendance_summary ADD COLUMN overtime_hours NUMERIC(4,2);
        END IF;
    END $$;
    """,
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'attendance_summary' AND column_name = 'clock_in_time'
        ) THEN
            ALTER TABLE attendance_summary ADD COLUMN clock_in_time TIMESTAMP WITH TIME ZONE;
        END IF;
    END $$;
    """,
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'attendance_summary' AND column_name = 'clock_out_time'
        ) THEN
            ALTER TABLE attendance_summary ADD COLUMN clock_out_time TIMESTAMP WITH TIME ZONE;
        END IF;
    END $$;
    """,
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'attendance_summary' AND column_name = 'supervisor_id'
        ) THEN
            ALTER TABLE attendance_summary ADD COLUMN supervisor_id INTEGER;
        END IF;
    END $$;
    """,
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'attendance_summary' AND column_name = 'supervisor_name'
        ) THEN
            ALTER TABLE attendance_summary ADD COLUMN supervisor_name TEXT;
        END IF;
    END $$;
    """,
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'attendance_summary' AND column_name = 'is_active'
        ) THEN
            ALTER TABLE attendance_summary ADD COLUMN is_active BOOLEAN DEFAULT TRUE NOT NULL;
        END IF;
    END $$;
    """,
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'attendance_summary' AND column_name = 'created_at'
        ) THEN
            ALTER TABLE attendance_summary ADD COLUMN created_at TIMESTAMP WITH TIME ZONE;
        END IF;
    END $$;
    """,
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'attendance_summary' AND column_name = 'updated_at'
        ) THEN
            ALTER TABLE attendance_summary ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE;
        END IF;
    END $$;
    """,
    # Ensure constraints exist
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.table_constraints
            WHERE constraint_name = 'pk_attendance_summary'
        ) THEN
            ALTER TABLE attendance_summary ADD CONSTRAINT pk_attendance_summary PRIMARY KEY (user_id, attendance_summary_date);
        END IF;
    END $$;
    """,
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.table_constraints
            WHERE constraint_name = 'unique_user_summary_date'
        ) THEN
            ALTER TABLE attendance_summary ADD CONSTRAINT unique_user_summary_date UNIQUE (user_id, attendance_summary_date);
        END IF;
    END $$;
    """,
    # Create indexes for attendance_summary
    "CREATE INDEX IF NOT EXISTS idx_attendance_summary_user_date ON attendance_summary(user_id, attendance_summary_date);",
    "CREATE INDEX IF NOT EXISTS idx_attendance_summary_department ON attendance_summary(department_name);",
    "CREATE INDEX IF NOT EXISTS idx_attendance_summary_status ON attendance_summary(status);"
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
            try:
                # Handle both standard Enum and string-based enums
                if hasattr(enum_class, '__members__'):
                    # Standard Python Enum
                    values = [member.value for member in enum_class]
                else:
                    # Handle other enum-like structures
                    values = list(enum_class) if hasattr(enum_class, '__iter__') else []
                
                if not values:
                    logger.warning(f"No values found for enum {enum_name}, skipping")
                    continue
                    
                # Check if enum exists
                enum_exists = await conn.execute(text(f"""
                    SELECT EXISTS (
                        SELECT 1 FROM pg_type WHERE typname = '{enum_name}'
                    );
                """))
                
                if not enum_exists.scalar():
                    await conn.execute(text(f"""
                        CREATE TYPE {enum_name} AS ENUM ({', '.join(f"'{v}'" for v in values)});
                    """))
                    logger.info(f"Created enum type: {enum_name} with values: {values}")
                else:
                    # Verify existing enum values
                    existing_values = await conn.execute(text(f"""
                        SELECT unnest(enum_range(NULL::{enum_name}))::text as enum_value;
                    """))
                    existing_set = set(row[0] for row in existing_values)
                    required_set = set(values)
                    
                    missing_values = required_set - existing_set
                    extra_values = existing_set - required_set
                    
                    if missing_values:
                        logger.warning(f"Enum {enum_name} is missing values: {missing_values}")
                        for value in missing_values:
                            await conn.execute(text(f"""
                                ALTER TYPE {enum_name} ADD VALUE '{value}';
                            """))
                            logger.info(f"Added value '{value}' to enum {enum_name}")
                    
                    if extra_values:
                        logger.warning(f"Enum {enum_name} has unexpected values: {extra_values}")
                        # Note: PostgreSQL does not support dropping enum values; log for manual intervention
            except Exception as e:
                logger.error(f"Error creating/updating enum {enum_name}: {str(e)}")
                raise

        # Create all tables for registered models BEFORE creating views
        await conn.run_sync(Base.metadata.create_all)

        # Ensure required columns exist AFTER tables are created
        table_column_updates = [
            ("users", "job_title", "VARCHAR(100)"),
            ("roles", "permissions", "JSONB DEFAULT '{}'::jsonb"),
            ("users", "employee_type", f"employee_type DEFAULT 'full_time'")
        ]
        
        for table_name, column_name, column_definition in table_column_updates:
            try:
                await conn.execute(text(f"""
                    DO $$ BEGIN
                        IF NOT EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_name = '{table_name}' AND column_name = '{column_name}'
                        ) THEN
                            ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition};
                        END IF;
                    END $$;
                """))
                logger.info(f"Ensured column {column_name} exists in table {table_name}")
            except Exception as e:
                logger.error(f"Error adding column {column_name} to {table_name}: {str(e)}")
                raise

        # Create materialized views, tables, and indexes
        for view_sql in MATERIALIZED_VIEW_SQLS:
            try:
                await conn.execute(text(view_sql))
                logger.info(f"Successfully executed: {view_sql.splitlines()[0]}")
            except Exception as e:
                logger.error(f"Error creating materialized view/table/index: {str(e)}")
                raise

        # Create indexes for better performance
        performance_indexes = [
            "CREATE INDEX IF NOT EXISTS idx_users_active ON users(is_active) WHERE deleted_at IS NULL;",
            "CREATE INDEX IF NOT EXISTS idx_user_roles_active ON user_roles(user_id, is_active);",
            "CREATE INDEX IF NOT EXISTS idx_roles_active ON roles(is_active) WHERE deleted_at IS NULL;",
            "CREATE INDEX IF NOT EXISTS idx_attendance_records_date ON attendance_records(date, user_id);",
            "CREATE INDEX IF NOT EXISTS idx_leave_requests_status ON leave_requests(status, user_id);",
        ]
        
        for index_sql in performance_indexes:
            try:
                await conn.execute(text(index_sql))
                logger.info(f"Successfully created index: {index_sql.splitlines()[0]}")
            except Exception as e:
                logger.error(f"Error creating index: {str(e)}")
                raise

        logger.info("Database initialized with enums, tables, materialized views, and indexes")

# Background task for refreshing materialized views
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((OperationalError, DatabaseError)),
    before_sleep=lambda retry_state: logger.warning(
        f"Materialized view refresh attempt {retry_state.attempt_number} failed, retrying..."
    )
)
async def background_refresh_materialized_views():
    """Refresh all materialized views."""
    materialized_views = ["leave_request_summary"]  # Only refresh leave_request_summary
    
    if AsyncSessionLocal is None:
        logger.warning("Database not initialized, skipping materialized view refresh")
        return
    
    async with AsyncSessionLocal() as session:
        try:
            for view_name in materialized_views:
                try:
                    # Check if view exists before trying to refresh
                    view_exists = await session.execute(text(f"""
                        SELECT EXISTS (
                            SELECT 1 FROM information_schema.tables 
                            WHERE table_name = '{view_name}' AND table_type = 'VIEW'
                        );
                    """))
                    
                    if view_exists.scalar():
                        await session.execute(text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view_name}"))
                        logger.info(f"Materialized view '{view_name}' refreshed successfully")
                    else:
                        logger.warning(f"Materialized view '{view_name}' does not exist, skipping refresh")
                except Exception as e:
                    logger.error(f"Error refreshing materialized view {view_name}: {str(e)}")
                    raise
            
            await session.commit()
        except Exception as e:
            logger.error(f"Error in materialized view refresh task: {str(e)}")
            await session.rollback()
            raise

async def start_background_refresh():
    """Start background task for refreshing materialized views."""
    logger.info("Starting materialized view refresh task")
    asyncio.create_task(background_refresh_materialized_views())

# Utility functions for enum validation
async def validate_enum_value(enum_class, value: str) -> bool:
    """Validate that a value exists in the given enum class."""
    try:
        if hasattr(enum_class, '__members__'):
            # Standard Python Enum
            return value in [member.value for member in enum_class]
        else:
            # Handle other enum-like structures
            return value in enum_class if hasattr(enum_class, '__contains__') else False
    except Exception:
        logger.error(f"Error validating enum value {value} for {enum_class.__name__}")
        return False

async def get_enum_values(enum_class) -> list[str]:
    """Get all values from an enum class."""
    try:
        if hasattr(enum_class, '__members__'):
            # Standard Python Enum
            return [member.value for member in enum_class]
        elif hasattr(enum_class, '__iter__'):
            # Handle other iterable enum-like structures
            return list(enum_class)
        else:
            return []
    except Exception:
        logger.error(f"Error retrieving values for enum {enum_class.__name__}")
        return []