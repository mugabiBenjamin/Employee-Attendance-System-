from select import select
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
from pythonjsonlogger import jsonlogger
from app.core.config import get_settings
from app.core.database import (
    get_db,
    initialize_engine_and_session,
    init_db,
    start_background_refresh,
    shutdown
)
from app.core.middleware import setup_middleware
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.v1.api import api_router
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
from app.core.celery import app as celery_app

settings = get_settings()

# -----------------------
# Logging Configuration
# -----------------------
logger = logging.getLogger(__name__)
log_handler = logging.FileHandler(settings.LOG_FILE)
formatter = jsonlogger.JsonFormatter(
    fmt="%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s",
    json_ensure_ascii=False
)
log_handler.setFormatter(formatter)
logger.handlers = [log_handler]
try:
    logger.setLevel(getattr(logging, settings.LOG_LEVEL))
except AttributeError:
    logger.error(f"Invalid LOG_LEVEL: {settings.LOG_LEVEL}, defaulting to INFO")
    logger.setLevel(logging.INFO)

# -----------------------
# Rate Limiter Setup
# -----------------------
def get_client_ip(request: FastAPI.Request) -> str:
    """Get client IP, preferring X-Forwarded-For for proxy environments."""
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return get_remote_address(request)

limiter = Limiter(key_func=get_client_ip)

# -----------------------
# Lifespan Events
# -----------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        f"Application startup: initializing database, Redis, and views... Version: {settings.APP_VERSION}, Environment: {settings.ENVIRONMENT}",
        extra={"request_id": None}
    )
    try:
        await initialize_engine_and_session()  # Initialize DB engine, session factory, and Redis
        await init_db()                       # Create enums, tables, and materialized views
        await start_background_refresh()      # Start background refresh for materialized views
        try:
            celery_app.setup_periodic_tasks()  # Configure Celery periodic tasks
        except Exception as e:
            logger.error(f"Failed to setup Celery periodic tasks: {str(e)}", extra={"request_id": None})
            raise
        logger.info("Startup complete.", extra={"request_id": None})
        yield
    except Exception as e:
        logger.error(f"Startup failed: {str(e)}", extra={"request_id": None})
        raise
    finally:
        logger.info(
            f"Application shutdown... Version: {settings.APP_VERSION}, Environment: {settings.ENVIRONMENT}",
            extra={"request_id": None}
        )
        await shutdown()  # Close DB engine and Redis connections
        logger.info("Shutdown complete.", extra={"request_id": None})

# -----------------------
# FastAPI App Instance
# -----------------------
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan
)

# -----------------------
# Middleware Configuration
# -----------------------
# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# System action logging
setup_middleware(app)

# -----------------------
# API Routes
# -----------------------
app.include_router(api_router, prefix=settings.API_V1_STR)

# -----------------------
# Root Endpoint
# -----------------------
@app.get("/")
async def root():
    return {"message": f"Welcome to {settings.APP_NAME} API"}

# -----------------------
# Health Check Endpoint
# -----------------------
@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check(db: AsyncSession = Depends(get_db)) -> dict:
    """Check the health of the application and database connectivity."""
    try:
        await db.execute(select(1))  # Simple query to test DB connection
        return {
            "status": "healthy",
            "app_name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}", extra={"request_id": None})
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database connection failed")