import asyncio
from datetime import date, datetime, timedelta, timezone
from celery import Celery
from pydantic import BaseModel, ConfigDict
from sqlalchemy.sql import text, select
import logging
import aiofiles
import csv
import io
import os
import re
from app.core.config import settings
from app.core.database import AsyncSessionLocal, initialize_engine_and_session
from app.models.attendance_records import AttendanceRecords
from app.core.mail import send_email_notification
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from sqlalchemy.ext.asyncio import AsyncSession

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

# Ensure DB and Redis are initialized before tasks run
@app.on_after_configure.connect
def setup_task_prerequisites(**kwargs):
    async def init_async():
        await initialize_engine_and_session()
        logger.info("Database engine and session initialized for Celery tasks")
    
    # Run the async initialization in a new event loop
    try:
        asyncio.run(init_async())
    except Exception as e:
        logger.error(f"Failed to initialize database for Celery tasks: {str(e)}")
        raise

def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal and invalid characters."""
    filename = re.sub(r'[^\w\-_\.]', '_', filename)
    filename = filename.replace('..', '')
    return filename

async def fetch_attendance_records(user_id: int, start_date: str, end_date: str, session: AsyncSession) -> list:
    """Fetch attendance records for a user within a date range."""
    try:
        # Normalize YYYY-MM-DD inputs to [start, end) datetimes in UTC (or your default TZ)
        def to_dt_bounds(s: str, e: str):
            # Treat inputs as dates; include full end day by advancing one day and using < upper bound
            sd = datetime.fromisoformat(s).replace(hour=0, minute=0, second=0, microsecond=0)
            ed = (datetime.fromisoformat(e).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1))
            return sd, ed
        start_dt, end_dt = to_dt_bounds(start_date, end_date)

        # Use explicit column selection to ensure proper attribute access
        query = select(
            AttendanceRecords.attendance_id,
            AttendanceRecords.date,
            AttendanceRecords.clock_in_time,
            AttendanceRecords.clock_out_time,
            AttendanceRecords.status,
            AttendanceRecords.total_hours,
            AttendanceRecords.overtime_hours
        ).where(
            AttendanceRecords.user_id == user_id,
            AttendanceRecords.clock_in_time >= start_dt,
            AttendanceRecords.clock_in_time < end_dt,
            AttendanceRecords.is_active.is_(True)
        ).order_by(AttendanceRecords.clock_in_time.desc())

        result = await session.execute(query)
        return result.fetchall()
    except Exception as e:
        logger.error(f"Error fetching attendance records for user_id {user_id}: {str(e)}")
        raise

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
async def send_email_task(notification_type: str, context: dict):
    """Celery task to send emails asynchronously."""
    async with AsyncSessionLocal() as session:
        try:
            await send_email_notification(notification_type, context, session)
            logger.info(f"Email sent successfully for {notification_type} to user_id: {context.get('user_id')}")
            return {"status": "success", "message": f"Email sent for {notification_type}"}
        except Exception as e:
            logger.error(f"Failed to send email for {notification_type}: {str(e)}")
            raise

@app.task
async def generate_attendance_csv_task(user_id: int, start_date: str, end_date: str, filename: str):
    """Celery task to generate attendance CSV report asynchronously."""
    sanitized_filename = sanitize_filename(filename)
    output_path = os.path.join(settings.UPLOAD_FOLDER, sanitized_filename)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    async with AsyncSessionLocal() as session:
        try:
            records = await fetch_attendance_records(user_id, start_date, end_date, session)

            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow([
                "Record ID", "Date", "Clock In", "Clock Out", 
                "Status", "Total Hours", "Overtime Hours"
            ])
            
            for record in records:
                # Access Row tuple elements by index
                writer.writerow([
                    record[0],  # attendance_id
                    record[1],  # date
                    record[2],  # clock_in_time
                    record[3],  # clock_out_time
                    record[4],  # status
                    record[5],  # total_hours
                    record[6]   # overtime_hours
                ])

            async with aiofiles.open(output_path, "w", encoding='utf-8') as f:
                await f.write(output.getvalue())

            logger.info(f"Attendance CSV generated for user_id: {user_id}, file: {output_path}")
            return {"status": "success", "message": f"CSV generated: {output_path}"}
        except Exception as e:
            logger.error(f"Error generating attendance CSV for user_id {user_id}: {str(e)}")
            raise

@app.task
async def generate_attendance_pdf_task(user_id: int, start_date: str, end_date: str, filename: str):
    """Celery task to generate attendance PDF report asynchronously."""
    sanitized_filename = sanitize_filename(filename)
    output_path = os.path.join(settings.UPLOAD_FOLDER, sanitized_filename)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    async with AsyncSessionLocal() as session:
        try:
            records = await fetch_attendance_records(user_id, start_date, end_date, session)

            data = [[
                "Record ID", "Date", "Clock In", "Clock Out", 
                "Status", "Total Hours", "Overtime Hours"
            ]]
            
            for record in records:
                # Access Row tuple elements by index with safe conversion
                data.append([
                    str(record[0]) if record[0] is not None else "",  # attendance_id
                    str(record[1]) if record[1] is not None else "",  # date
                    str(record[2]) if record[2] is not None else "",  # clock_in_time
                    str(record[3]) if record[3] is not None else "",  # clock_out_time
                    str(record[4]) if record[4] is not None else "",  # status
                    str(record[5]) if record[5] is not None else "",  # total_hours
                    str(record[6]) if record[6] is not None else ""   # overtime_hours
                ])

            doc = SimpleDocTemplate(output_path, pagesize=letter)
            table = Table(data)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            doc.build([table])

            logger.info(f"Attendance PDF generated for user_id: {user_id}, file: {output_path}")
            return {"status": "success", "message": f"PDF generated: {output_path}"}
        except Exception as e:
            logger.error(f"Error generating attendance PDF for user_id {user_id}: {str(e)}")
            raise

def dispatch_csv_report(user_id: int, start_date: date, end_date: date) -> str:
    """Dispatch CSV report generation task and return job ID."""
    filename = f"attendance_{user_id}_{start_date}_to_{end_date}.csv"
    sanitized_filename = sanitize_filename(filename)
    job = app.send_task('app.core.celery.generate_attendance_csv_task', 
                       args=[user_id, str(start_date), str(end_date), sanitized_filename])
    logger.info(f"Dispatched CSV report task for user_id: {user_id}, job_id: {job.id}")
    return job.id

def dispatch_pdf_report(user_id: int, start_date: date, end_date: date) -> str:
    """Dispatch PDF report generation task and return job ID."""
    filename = f"attendance_{user_id}_{start_date}_to_{end_date}.pdf"
    sanitized_filename = sanitize_filename(filename)
    job = app.send_task('app.core.celery.generate_attendance_pdf_task',
                       args=[user_id, str(start_date), str(end_date), sanitized_filename])
    logger.info(f"Dispatched PDF report task for user_id: {user_id}, job_id: {job.id}")
    return job.id

def setup_periodic_tasks():
    """Setup periodic tasks for Celery."""
    try:
        app.conf.update(
            beat_schedule={
                'refresh-materialized-view': {
                    'task': 'app.core.celery.refresh_materialized_view',
                    'schedule': settings.MATERIALIZED_VIEW_REFRESH_INTERVAL,
                },
            }
        )
        logger.info("Periodic tasks configured for Celery")
    except AttributeError as e:
        logger.warning(f"Could not set up periodic tasks: {e}")
        # Fallback: set directly on conf object
        if hasattr(app, 'conf'):
            setattr(app.conf, 'beat_schedule', {
                'refresh-materialized-view': {
                    'task': 'app.core.celery.refresh_materialized_view',
                    'schedule': settings.MATERIALIZED_VIEW_REFRESH_INTERVAL,
                },
            })
            logger.info("Periodic tasks configured via fallback method")

# Configure periodic tasks on startup
setup_periodic_tasks()