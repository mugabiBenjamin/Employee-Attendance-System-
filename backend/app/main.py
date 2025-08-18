from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
from pythonjsonlogger import jsonlogger
from app.core.config import get_settings
from app.core.database import (
    initialize_engine_and_session,
    init_db,
    start_background_refresh,
    shutdown
)
from app.core.middleware import setup_middleware
from app.api.v1.api import api_router
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware

# -----------------------
# Logging Configuration
# -----------------------
settings = get_settings()
logger = logging.getLogger(__name__)
log_handler = logging.FileHandler(settings.LOG_FILE)
formatter = jsonlogger.JsonFormatter(
    fmt="%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s",
    json_ensure_ascii=False
)
log_handler.setFormatter(formatter)
logger.handlers = [log_handler]
logger.setLevel(getattr(logging, settings.LOG_LEVEL))

# -----------------------
# Rate Limiter Setup
# -----------------------
limiter = Limiter(key_func=get_remote_address)

# -----------------------
# Lifespan Events
# -----------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application startup: initializing database, Redis, and views...", extra={"request_id": None})
    await initialize_engine_and_session()   # Create DB engine, session factory, Redis
    await init_db()                         # Create enums, tables, views
    await start_background_refresh()        # Start background refresh for materialized views
    logger.info("Startup complete.", extra={"request_id": None})
    yield
    logger.info("Application shutdown...", extra={"request_id": None})
    await shutdown()
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