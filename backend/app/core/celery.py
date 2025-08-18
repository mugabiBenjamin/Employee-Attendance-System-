from datetime import date
from celery import Celery
from pydantic import BaseModel, ConfigDict
from sqlalchemy.sql import text, select
import asyncio
import logging
import aiofiles
import csv
import io
import os
import re
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal, initialize_engine_and_session
from app.models.attendance_records import AttendanceRecords
from app.core.mail import send_email, EmailSchema
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

logger = logging.getLogger(__name__)

# Initialize Celery
settings = get_settings()
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
    asyncio.run(initialize_engine_and_session())

def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal and invalid characters."""
    filename = re.sub(r'[^\w\-_\.]', '_', filename)
    filename = filename.replace('..', '')
    return filename

@app.task
def refresh_materialized_view():
    """Celery task to refresh the attendance_summary materialized view."""
    async def _refresh():
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
    return asyncio.run(_refresh())

@app.task
def send_email_task(to_email: str, subject: str, body: str, cc_emails: list = None, bcc_emails: list = None):
    """Celery task to send emails asynchronously."""
    async def _send_email():
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
    return asyncio.run(_send_email())

@app.task
def generate_attendance_csv_task(user_id: int, start_date: str, end_date: str, filename: str):
    """Celery task to generate attendance CSV report asynchronously."""
    async def _generate_csv():
        sanitized_filename = sanitize_filename(filename)
        output_path = os.path.join(settings.UPLOAD_FOLDER, sanitized_filename)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        async with AsyncSessionLocal() as session:
            try:
                query = select(AttendanceRecords).where(
                    AttendanceRecords.user_id == user_id,
                    AttendanceRecords.clock_in_time >= start_date,
                    AttendanceRecords.clock_in_time <= end_date,
                    AttendanceRecords.is_active == True
                ).order_by(AttendanceRecords.clock_in_time.desc())
                
                result = await session.execute(query)
                records = result.scalars().all()

                output = io.StringIO()
                writer = csv.writer(output)
                writer.writerow([
                    "Record ID", "Date", "Clock In", "Clock Out", 
                    "Status", "Total Hours", "Overtime Hours"
                ])
                
                for record in records:
                    writer.writerow([
                        record.attendance_id,
                        record.date,
                        record.clock_in_time,
                        record.clock_out_time,
                        record.status,
                        record.total_hours,
                        record.overtime_hours
                    ])

                async with aiofiles.open(output_path, "w", encoding='utf-8') as f:
                    await f.write(output.getvalue())

                logger.info(f"Attendance CSV generated for user_id: {user_id}, file: {output_path}")
                return {"status": "success", "message": f"CSV generated: {output_path}"}
            except Exception as e:
                logger.error(f"Error generating attendance CSV for user_id {user_id}: {str(e)}")
                raise
    return asyncio.run(_generate_csv())

@app.task
def generate_attendance_pdf_task(user_id: int, start_date: str, end_date: str, filename: str):
    """Celery task to generate attendance PDF report asynchronously."""
    async def _generate_pdf():
        sanitized_filename = sanitize_filename(filename)
        output_path = os.path.join(settings.UPLOAD_FOLDER, sanitized_filename)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        async with AsyncSessionLocal() as session:
            try:
                query = select(AttendanceRecords).where(
                    AttendanceRecords.user_id == user_id,
                    AttendanceRecords.clock_in_time >= start_date,
                    AttendanceRecords.clock_in_time <= end_date,
                    AttendanceRecords.is_active == True
                ).order_by(AttendanceRecords.clock_in_time.desc())
                
                result = await session.execute(query)
                records = result.scalars().all()

                data = [[
                    "Record ID", "Date", "Clock In", "Clock Out", 
                    "Status", "Total Hours", "Overtime Hours"
                ]]
                
                for record in records:
                    data.append([
                        str(record.attendance_id),
                        str(record.date) if record.date else "",
                        str(record.clock_in_time),
                        str(record.clock_out_time) if record.clock_out_time else "",
                        str(record.status) if record.status else "",
                        str(record.total_hours) if record.total_hours else "",
                        str(record.overtime_hours) if record.overtime_hours else ""
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
    return asyncio.run(_generate_pdf())

def dispatch_csv_report(user_id: int, start_date: date, end_date: date) -> str:
    """Dispatch CSV report generation task and return job ID."""
    filename = f"attendance_{user_id}_{start_date}_to_{end_date}.csv"
    sanitized_filename = sanitize_filename(filename)
    job = generate_attendance_csv_task.delay(user_id, str(start_date), str(end_date), sanitized_filename)
    logger.info(f"Dispatched CSV report task for user_id: {user_id}, job_id: {job.id}")
    return job.id

def dispatch_pdf_report(user_id: int, start_date: date, end_date: date) -> str:
    """Dispatch PDF report generation task and return job ID."""
    filename = f"attendance_{user_id}_{start_date}_to_{end_date}.pdf"
    sanitized_filename = sanitize_filename(filename)
    job = generate_attendance_pdf_task.delay(user_id, str(start_date), str(end_date), sanitized_filename)
    logger.info(f"Dispatched PDF report task for user_id: {user_id}, job_id: {job.id}")
    return job.id

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