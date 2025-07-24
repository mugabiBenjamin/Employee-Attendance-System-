from celery import Celery
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text
from app.core.config import settings
from app.core.database import AsyncSessionLocal
import logging
import asyncio

logger = logging.getLogger(__name__)

# Initialize Celery
app = Celery(
    'ems_tasks',
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=['app.core.celery']
)

# Celery configuration
app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone=settings.DEFAULT_TIMEZONE,
    enable_utc=True,
)

class TaskConfig(BaseModel):
    task_name: str
    description: str

    model_config = ConfigDict(from_attributes=True)

@app.task
async def refresh_materialized_view():
    """Celery task to refresh the attendance_summary materialized view."""
    async with AsyncSessionLocal() as session:
        try:
            await session.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY attendance_summary"))
            await session.commit()
            logger.info("Materialized view 'attendance_summary' refreshed successfully")
            return {"status": "success", "message": "Materialized view refreshed"}
        except Exception as e:
            logger.error(f"Error refreshing materialized view: {str(e)}")
            await session.rollback()
            raise

@app.task
async def send_email_task(to_email: str, subject: str, body: str, cc_emails: list = None, bcc_emails: list = None):
    """Celery task to send emails asynchronously."""
    from app.core.mail import send_email, EmailSchema
    try:
        email_data = EmailSchema(
            to_email=to_email,
            subject=subject,
            body=body,
            cc_emails=cc_emails,
            bcc_emails=bcc_emails
        )
        await send_email(email_data)
        logger.info(f"Email sent successfully to {to_email}")
        return {"status": "success", "message": f"Email sent to {to_email}"}
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {str(e)}")
        raise

def setup_periodic_tasks():
    """Setup periodic tasks for Celery."""
    app.conf.beat_schedule = {
        'refresh-materialized-view': {
            'task': 'app.core.celery.refresh_materialized_view',
            'schedule': settings.MATERIALIZED_VIEW_REFRESH_INTERVAL,
        },
    }
    logger.info("Periodic tasks configured for Celery")

# Configure periodic tasks on startup
setup_periodic_tasks()