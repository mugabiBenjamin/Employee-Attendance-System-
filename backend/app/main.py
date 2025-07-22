from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.database import init_db, start_materialized_view_refresh
from app.api.v1.api import router as api_router
from app.models import SystemLog
from app.core.enums import SystemAction
import asyncio
import logging
from contextlib import asynccontextmanager

# Configure logging
logging.basicConfig(
    filename=settings.LOG_FILE,
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware to log system actions
@app.middleware("http")
async def log_system_actions(request: Request, call_next):
    response = await call_next(request)
    user_id = None
    action = None
    
    # Determine the action based on request method and path
    path = request.url.path
    method = request.method
    
    if path.endswith("/auth/token") and method == "POST":
        action = SystemAction.LOGIN
    elif path.endswith("/auth/logout") and method == "POST":
        action = SystemAction.LOGOUT
    elif path.endswith("/attendance/clock_in") and method == "POST":
        action = SystemAction.CLOCK_IN
    elif path.endswith("/attendance/clock_out") and method == "POST":
        action = SystemAction.CLOCK_OUT
    elif path.endswith("/users/password") and method == "PUT":
        action = SystemAction.password_change
    elif path.endswith("/users/me") and method == "PUT":
        action = SystemAction.profile_update
    elif path.endswith("/users/export") and method == "GET":
        action = SystemAction.data_export
    elif path.endswith("/users/import") and method == "POST":
        action = SystemAction.data_import
    elif path.endswith("/users/roles") and method == "POST":
        action = SystemAction.assign_role
    elif path.endswith("/users/roles") and method == "DELETE":
        action = SystemAction.revoke_role
    elif path.endswith("/reports") and method == "GET":
        action = SystemAction.view_report
    elif path.endswith("/leave/approve") and method == "POST":
        action = SystemAction.approve_leave
    elif path.endswith("/leave/reject") and method == "POST":
        action = SystemAction.reject_leave
    elif path.endswith("/departments") and method == "POST":
        action = SystemAction.create_department
    elif path.endswith("/departments") and method == "DELETE":
        action = SystemAction.delete_department
    elif method in ["POST", "PUT", "DELETE"]:
        action = SystemAction[method]  # Maps POST->INSERT, PUT->UPDATE, DELETE->DELETE

    if action:
        # Get user_id from request state if available
        user = getattr(request.state, "user", None)
        user_id = user.user_id if user else None
        
        # Log to system_logs table
        async with AsyncSessionLocal() as session:
            try:
                system_log = SystemLog(
                    user_id=user_id,
                    action=action,
                    table_affected=path.split("/")[-2] if len(path.split("/")) > 2 else None,
                    record_id=None,  # Could be extracted from path for specific endpoints
                    old_values=None,
                    new_values=None,
                    ip_address=str(request.client.host),
                    user_agent=request.headers.get("user-agent")
                )
                session.add(system_log)
                await session.commit()
                logger.info(f"Logged system action: {action} for user_id: {user_id}")
            except Exception as e:
                logger.error(f"Failed to log system action: {str(e)}")
                await session.rollback()

    return response

# Include API routes
app.include_router(api_router, prefix=settings.API_V1_STR)

@app.on_event("startup")
async def startup_event():
    logger.info("Starting up the application")
    await init_db()  # Initialize enums, tables, and materialized view
    await start_materialized_view_refresh()  # Start periodic materialized view refresh
    logger.info("Database and materialized view refresh initialized")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down the application")

@app.get("/")
async def root():
    return {"message": f"Welcome to {settings.APP_NAME} API"}

# Ensure AsyncSessionLocal is imported for middleware
from app.core.database import AsyncSessionLocal