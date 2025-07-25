from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncSession
from contextlib import asynccontextmanager
import logging

from app.core.config import settings
from app.core.database import init_db, start_materialized_view_refresh, AsyncSessionLocal
from app.api.v1.api import api_router
from app.models.system_logs import SystemLog
from app.core.enums import SystemAction

# Configure logging
logging.basicConfig(
    filename=settings.LOG_FILE,
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Define lifespan context
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🔄 Application startup: initializing database and views...")
    await init_db()
    await start_materialized_view_refresh()
    logger.info("✅ Startup complete.")
    yield
    logger.info("🛑 Application shutdown...")

# Initialize FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware: Log system actions
@app.middleware("http")
async def log_system_actions(request: Request, call_next):
    response = await call_next(request)
    user = getattr(request.state, "user", None)
    user_id = getattr(user, "user_id", None)

    path = request.url.path
    method = request.method
    action = None

    # Match common tracked paths
    if path.endswith("/auth/token") and method == "POST":
        action = SystemAction.LOGIN
    elif path.endswith("/auth/logout") and method == "POST":
        action = SystemAction.LOGOUT
    elif path.endswith("/attendance-records/clock") and method == "POST":
        action = SystemAction.CLOCK_IN  # Could distinguish more deeply
    elif path.endswith("/leave-requests/approve") and method == "POST":
        action = SystemAction.APPROVE_LEAVE
    elif path.endswith("/leave-requests/reject") and method == "POST":
        action = SystemAction.REJECT_LEAVE
    elif method in ["POST", "PUT", "DELETE"]:
        try:
            action = SystemAction[method]
        except KeyError:
            action = None

    if action:
        try:
            async with AsyncSessionLocal() as session:
                system_log = SystemLog(
                    user_id=user_id,
                    action=action,
                    table_affected=path.strip("/").split("/")[0],
                    record_id=None,
                    old_values=None,
                    new_values=None,
                    ip_address=str(request.client.host),
                    user_agent=request.headers.get("user-agent"),
                )
                session.add(system_log)
                await session.commit()
                logger.info(f"📋 Logged action: {action} by user_id={user_id}")
        except Exception as e:
            logger.error(f"⚠️ Failed to log action: {e}")

    return response

# Include API routes
app.include_router(api_router, prefix=settings.API_V1_STR)

# Root endpoint
@app.get("/")
async def root():
    return {"message": f"Welcome to {settings.APP_NAME} API"}
