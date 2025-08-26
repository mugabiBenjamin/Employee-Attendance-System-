import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, List, Dict, Any
import anyio
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException
from app.core.config import settings
from app.models.users import Users
from app.core.exceptions import DatabaseError, ResourceNotFoundError
import anyio

class EmailSchema(BaseModel):
    to_email: EmailStr
    subject: str = Field(..., max_length=255)
    body: str
    cc_emails: Optional[List[EmailStr]] = None
    bcc_emails: Optional[List[EmailStr]] = None

    model_config = ConfigDict(from_attributes=True)

async def get_user_email(user_id: int, db: AsyncSession) -> Optional[str]:
    """Retrieve user email by user_id using SQLAlchemy."""
    try:
        query = select(Users.email).where(Users.user_id == user_id, Users.is_active == True, Users.deleted_at == None)
        result = await db.execute(query)
        email = result.scalar_one_or_none()
        if not email:
            raise ResourceNotFoundError(resource="User", identifier=user_id)
        return email
    except Exception as e:
        raise DatabaseError(f"Failed to retrieve user email: {str(e)}")

async def send_email(email_data: EmailSchema) -> None:
    """Send email using SMTP configuration from settings, running blocking SMTP in a thread."""
    def _send_email_blocking():
        try:
            msg = MIMEMultipart()
            msg['From'] = settings.MAIL_FROM
            msg['To'] = email_data.to_email
            msg['Subject'] = email_data.subject
            if email_data.cc_emails:
                msg['Cc'] = ", ".join(email_data.cc_emails)
            if email_data.bcc_emails:
                msg['Bcc'] = ", ".join(email_data.bcc_emails)

            msg.attach(MIMEText(email_data.body, 'plain'))

            with smtplib.SMTP(settings.MAIL_SERVER, settings.MAIL_PORT) as server:
                if settings.MAIL_STARTTLS:
                    server.starttls()
                server.login(settings.MAIL_USERNAME, settings.MAIL_PASSWORD)
                server.send_message(msg)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")

    await anyio.to_thread.run_sync(_send_email_blocking)

async def send_email_notification(notification_type: str, context: Dict[str, Any], db: AsyncSession) -> None:
    """Unified function to construct and send email notifications based on type."""
    email = await get_user_email(context.get("user_id"), db)
    
    if notification_type == "leave_notification":
        subject = f"Leave Request {context['status'].capitalize()} (ID: {context['leave_id']})"
        body = (
            f"Dear User,\n\n"
            f"Your leave request (ID: {context['leave_id']}) has been {context['status']}.\n"
            f"Details:\n"
            f"Leave Type: {context['leave_type'].capitalize()}\n"
            f"Start Date: {context['start_date']}\n"
            f"End Date: {context['end_date']}\n\n"
            f"Please contact HR for any questions.\n\n"
            f"Best regards,\nEmployee Management System"
        )
    elif notification_type == "time_correction_notification":
        subject = f"Time Correction Request {context['status'].capitalize()} (ID: {context['correction_id']})"
        clock_in = context.get('clock_in')
        clock_out = context.get('clock_out')
        body = (
            f"Dear User,\n\n"
            f"Your time correction request (ID: {context['correction_id']}) has been {context['status']}.\n"
            f"Details:\n"
            f"Clock In: {clock_in.strftime('%Y-%m-%d %H:%M:%S') if clock_in else 'Not modified'}\n"
            f"Clock Out: {clock_out.strftime('%Y-%m-%d %H:%M:%S') if clock_out else 'Not modified'}\n\n"
            f"Please contact HR for any questions.\n\n"
            f"Best regards,\nEmployee Management System"
        )
    elif notification_type == "password_reset":
        subject = "Password Reset Request"
        body = (
            f"Dear User,\n\n"
            f"You have requested a password reset. Use the following token to reset your password:\n\n"
            f"Token: {context['reset_token']}\n\n"
            f"If you did not request this, please ignore this email or contact support.\n\n"
            f"Best regards,\nEmployee Management System"
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unknown notification type: {notification_type}")

    email_data = EmailSchema(
        to_email=email,
        subject=subject,
        body=body,
        cc_emails=context.get("cc_emails"),
        bcc_emails=context.get("bcc_emails")
    )
    await send_email(email_data)