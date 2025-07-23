import os
from typing import List
from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):
    APP_NAME: str = os.getenv("APP_NAME", "Employee Management System")
    APP_VERSION: str = os.getenv("APP_VERSION", "0.1.0")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = os.getenv("DEBUG", "True").lower() == "true"
    API_V1_STR: str = os.getenv("API_V1_STR", "/api/v1")
    
    DATABASE_URL: str
    DATABASE_HOST: str
    DATABASE_PORT: int
    DATABASE_NAME: str
    DATABASE_USER: str
    DATABASE_PASSWORD: str
    
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 7))
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    BCRYPT_ROUNDS: int = int(os.getenv("BCRYPT_ROUNDS", 12))
    
    BACKEND_CORS_ORIGINS: List[str]
    
    MAIL_USERNAME: str
    MAIL_PASSWORD: str
    MAIL_FROM: str
    MAIL_PORT: int = int(os.getenv("MAIL_PORT", 587))
    MAIL_SERVER: str = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    MAIL_STARTTLS: bool = os.getenv("MAIL_STARTTLS", "True").lower() == "true"
    MAIL_SSL_TLS: bool = os.getenv("MAIL_SSL_TLS", "False").lower() == "true"
    
    REDIS_URL: str
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str
    
    MAX_FILE_SIZE: int = int(os.getenv("MAX_FILE_SIZE", 10485760))
    UPLOAD_FOLDER: str = os.getenv("UPLOAD_FOLDER", "./uploads")
    ALLOWED_EXTENSIONS: List[str] = [
        x.strip() for x in os.getenv("ALLOWED_EXTENSIONS", "pdf,doc,docx,jpg,jpeg,png,txt").split(",")
    ]
    
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = os.getenv("LOG_FILE", "./logs/app.log")
    
    DEFAULT_PAGE_SIZE: int = int(os.getenv("DEFAULT_PAGE_SIZE", 50))
    MAX_PAGE_SIZE: int = int(os.getenv("MAX_PAGE_SIZE", 100))
    
    DEFAULT_TIMEZONE: str = os.getenv("DEFAULT_TIMEZONE", "UTC")
    
    # Enum settings from DDL
    ATTENDANCE_STATUSES: List[str] = [
        "present", "absent", "late", "early_departure", "on_leave", "half_day", "sick"
    ]
    LEAVE_TYPES: List[str] = [
        "annual", "sick", "maternity", "paternity", "emergency", "unpaid",
        "casual", "compensatory", "bereavement", "leave_of_absence", "public_holiday"
    ]
    LEAVE_REQUEST_STATUSES: List[str] = [
        "draft", "under_review", "approved", "rejected", "cancelled", "completed"
    ]
    CORRECTION_STATUSES: List[str] = [
        "draft", "under_review", "approved", "rejected", "cancelled", "completed"
    ]
    SYSTEM_ACTIONS: List[str] = [
        "INSERT", "UPDATE", "DELETE", "LOGIN", "LOGOUT", "CLOCK_IN", "CLOCK_OUT",
        "password_change", "profile_update", "data_export", "data_import",
        "assign_role", "revoke_role", "view_report", "approve_leave",
        "reject_leave", "create_department", "delete_department"
    ]
    EMPLOYEE_TYPES: List[str] = [
        "full_time", "part_time", "contract", "intern", "temporary"
    ]
    SHIFT_TYPES: List[str] = [
        "morning", "afternoon", "night", "flexible", "split"
    ]
    
    # Permission keys aligned with DDL roles table
    PERMISSION_KEYS: List[str] = [
        "clock_in", "clock_out", "view_own_attendance", "request_leave", "view_leave_balance",
        "approve_leave", "view_team_attendance", "generate_reports", "manage_overtime",
        "manage_employees", "generate_compliance_reports", "view_all_attendance", "manage_leave_policies",
        "manage_users", "manage_roles", "system_configuration", "view_logs", "manage_departments",
        "all_permissions"
    ]
    
    # Materialized view refresh interval (in seconds)
    MATERIALIZED_VIEW_REFRESH_INTERVAL: int = int(os.getenv("MATERIALIZED_VIEW_REFRESH_INTERVAL", 3600))  # Default: 1 hour
    
    class Config:
        case_sensitive = True
        env_file = Path(__file__).parent.parent.parent / ".env"
        env_file_encoding = "utf-8"
        validate_assignment = True

settings = Settings()