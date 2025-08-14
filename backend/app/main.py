from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
from app.core.config import settings
from app.core.database import init_db, start_materialized_view_refresh, AsyncSessionLocal, initialize_engine_and_session, redis
from app.api.v1.api import api_router
from app.models.system_logs import SystemLogs
from app.core.enums import SystemAction
from ipaddress import ip_address
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

# Configure logging
logging.basicConfig(
    filename=settings.LOG_FILE,
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Action mapping: (path_suffix, method) -> SystemAction
ACTION_MAPPING = {
    ("/auth/token", "POST"): SystemAction.LOGIN,
    ("/auth/logout", "POST"): SystemAction.LOGOUT,
    ("/attendance-records/clock", "POST"): SystemAction.CLOCK_IN,
    ("/leave-requests/approve", "POST"): SystemAction.APPROVE_LEAVE,
    ("/leave-requests/reject", "POST"): SystemAction.REJECT_LEAVE,
}

METHOD_FALLBACK = {
    "POST": SystemAction.INSERT,
    "PUT": SystemAction.UPDATE,
    "DELETE": SystemAction.DELETE,
}

def determine_system_action(path: str, method: str) -> str | None:
    for (path_suffix, mapped_method), action in ACTION_MAPPING.items():
        if path.endswith(path_suffix) and method == mapped_method:
            return action
    return METHOD_FALLBACK.get(method)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🔄 Application startup: initializing database and views...")
    await initialize_engine_and_session()  # Initialize engine, session, and Redis
    await init_db()
    await start_materialized_view_refresh()
    logger.info("✅ Startup complete.")
    yield
    logger.info("🛑 Application shutdown...")
    if redis:
        redis.close()
        await redis.wait_closed()
        logger.info("Redis connection closed")

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan
)

app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_system_actions(request: Request, call_next):
    response = await call_next(request)
    user = getattr(request.state, "user", None)
    user_id = getattr(user, "user_id", None)

    path = request.url.path
    method = request.method
    action = determine_system_action(path, method)

    if action:
        try:
            async with AsyncSessionLocal() as session:
                ip_addr = None
                if request.client and request.client.host:
                    try:
                        ip_addr = str(ip_address(request.client.host))
                    except ValueError:
                        logger.warning(f"Invalid IP address: {request.client.host}")
                        ip_addr = None

                system_log = SystemLogs(
                    user_id=user_id,
                    action=action,
                    table_affected=path.strip("/").split("/")[0],
                    record_id=None,
                    old_values=None,
                    new_values=None,
                    ip_address=ip_addr,
                    user_agent=request.headers.get("user-agent"),
                    timestamp=datetime.now(timezone.utc)
                )
                session.add(system_log)
                await session.commit()
                logger.info(f"📋 Logged action: {action} by user_id={user_id}")
        except Exception as e:
            logger.error(f"⚠️ Failed to log action: {str(e)}")

    return response

app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
async def root():
    return {"message": f"Welcome to {settings.APP_NAME} API"}