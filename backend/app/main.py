from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
from pythonjsonlogger import jsonlogger
from app.core.config import settings
from app.core.database import init_db, start_background_refresh, shutdown
from app.core.middleware import setup_middleware
from app.api.v1.api import api_router
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import _rate_limit_exceeded_handler

# Configure JSON logging
logger = logging.getLogger(__name__)
log_handler = logging.FileHandler(settings.LOG_FILE)
formatter = jsonlogger.JsonFormatter(
    fmt="%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s",
    json_ensure_ascii=False
)
log_handler.setFormatter(formatter)
logger.handlers = [log_handler]
logger.setLevel(getattr(logging, settings.LOG_LEVEL))

# Configure rate limiter
limiter = Limiter(key_func=get_remote_address)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application startup: initializing database and views...", extra={"request_id": None})
    await init_db()
    await start_background_refresh()
    logger.info("Startup complete.", extra={"request_id": None})
    yield
    logger.info("Application shutdown...", extra={"request_id": None})
    await shutdown()
    logger.info("Shutdown complete.", extra={"request_id": None})

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan
)

# Add rate-limiting middleware and exception handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup system action logging middleware
setup_middleware(app)

app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
async def root():
    return {"message": f"Welcome to {settings.APP_NAME} API"}