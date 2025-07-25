import os
from pathlib import Path
from typing import List
from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

# Load .env file manually
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent.parent / ".env")

class Settings(BaseSettings):
    APP_NAME: str = os.getenv("APP_NAME", "Employee Management System")
    APP_VERSION: str = os.getenv("APP_VERSION", "0.1.0")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = os.getenv("DEBUG", "True").lower() == "true"
    API_V1_STR: str = os.getenv("API_V1_STR", "/api/v1")

    DATABASE_URL: str = Field(..., env="DATABASE_URL")
    DATABASE_HOST: str = Field(..., env="DATABASE_HOST")
    DATABASE_PORT: int = Field(..., env="DATABASE_PORT")
    DATABASE_NAME: str = Field(..., env="DATABASE_NAME")
    DATABASE_USER: str = Field(..., env="DATABASE_USER")
    DATABASE_PASSWORD: str = Field(..., env="DATABASE_PASSWORD")

    SECRET_KEY: str = Field(..., env="SECRET_KEY")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 7))
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    BCRYPT_ROUNDS: int = int(os.getenv("BCRYPT_ROUNDS", 12))

    BACKEND_CORS_ORIGINS: List[str] = Field(default_factory=list)

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def parse_origins(cls, v):
        if isinstance(v, str):
            return [i.strip() for i in v.split(",") if i.strip()]
        return v

    MAIL_USERNAME: str = Field(..., env="MAIL_USERNAME")
    MAIL_PASSWORD: str = Field(..., env="MAIL_PASSWORD")
    MAIL_FROM: str = Field(..., env="MAIL_FROM")
    MAIL_PORT: int = int(os.getenv("MAIL_PORT", 587))
    MAIL_SERVER: str = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    MAIL_STARTTLS: bool = os.getenv("MAIL_STARTTLS", "True").lower() == "true"
    MAIL_SSL_TLS: bool = os.getenv("MAIL_SSL_TLS", "False").lower() == "true"

    REDIS_URL: str = Field(..., env="REDIS_URL")
    CELERY_BROKER_URL: str = Field(..., env="CELERY_BROKER_URL")
    CELERY_RESULT_BACKEND: str = Field(..., env="CELERY_RESULT_BACKEND")

    MAX_FILE_SIZE: int = int(os.getenv("MAX_FILE_SIZE", 10485760))
    UPLOAD_FOLDER: str = os.getenv("UPLOAD_FOLDER", "./uploads")
    ALLOWED_EXTENSIONS: List[str] = Field(default_factory=lambda: [
        ext.strip() for ext in os.getenv("ALLOWED_EXTENSIONS", "pdf,doc,docx,jpg,jpeg,png").split(",")
    ])

    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = os.getenv("LOG_FILE", "./logs/app.log")

    DEFAULT_PAGE_SIZE: int = int(os.getenv("DEFAULT_PAGE_SIZE", 50))
    MAX_PAGE_SIZE: int = int(os.getenv("MAX_PAGE_SIZE", 100))
    DEFAULT_TIMEZONE: str = os.getenv("DEFAULT_TIMEZONE", "UTC")

    # Static lists
    ATTENDANCE_STATUSES: List[str] = ["present", "absent", "late", "early_departure", "on_leave", "half_day", "sick"]
    LEAVE_TYPES: List[str] = ["annual", "sick", "maternity", "paternity", "emergency", "unpaid", "casual", "compensatory", "bereavement", "leave_of_absence", "public_holiday"]
    LEAVE_REQUEST_STATUSES: List[str] = ["draft", "under_review", "approved", "rejected", "cancelled", "completed"]
    CORRECTION_STATUSES: List[str] = ["draft", "under_review", "approved", "rejected", "cancelled", "completed"]
    SYSTEM_ACTIONS: List[str] = ["INSERT", "UPDATE", "DELETE", "LOGIN", "LOGOUT", "CLOCK_IN", "CLOCK_OUT", "password_change", "profile_update", "data_export", "data_import", "assign_role", "revoke_role", "view_report", "approve_leave", "reject_leave", "create_department", "delete_department"]
    EMPLOYEE_TYPES: List[str] = ["full_time", "part_time", "contract", "intern", "temporary"]
    SHIFT_TYPES: List[str] = ["morning", "afternoon", "night", "flexible", "split"]
    PERMISSION_KEYS: List[str] = ["clock_in", "clock_out", "view_own_attendance", "request_leave", "view_leave_balance", "approve_leave", "view_team_attendance", "generate_reports", "manage_overtime", "manage_employees", "generate_compliance_reports", "view_all_attendance", "manage_leave_policies", "manage_users", "manage_roles", "system_configuration", "view_logs", "manage_departments", "all_permissions"]

    MATERIALIZED_VIEW_REFRESH_INTERVAL: int = int(os.getenv("MATERIALIZED_VIEW_REFRESH_INTERVAL", 3600))

settings = Settings()