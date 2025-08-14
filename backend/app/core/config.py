from typing import List, ClassVar, Set
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from app.core.enums import AttendanceStatus, LeaveType, LeaveRequestStatus, CorrectionStatus, SystemAction, EmployeeType, ShiftType, Permission

class Settings(BaseSettings):
    APP_NAME: str = Field(default="Employee Management System", env="APP_NAME")
    APP_VERSION: str = Field(default="0.1.0", env="APP_VERSION")
    ENVIRONMENT: str = Field(default="development", env="ENVIRONMENT")
    DEBUG: bool = Field(default=True, env="DEBUG")
    API_V1_STR: str = Field(default="/api/v1", env="API_V1_STR")

    DATABASE_URL: str = Field(..., env="DATABASE_URL")
    DATABASE_HOST: str = Field(..., env="DATABASE_HOST")
    DATABASE_PORT: int = Field(..., env="DATABASE_PORT")
    DATABASE_NAME: str = Field(..., env="DATABASE_NAME")
    DATABASE_USER: str = Field(..., env="DATABASE_USER")
    DATABASE_PASSWORD: str = Field(..., env="DATABASE_PASSWORD")

    SECRET_KEY: str = Field(..., env="SECRET_KEY")
    JWT_SECRET_KEY: str = Field(..., env="JWT_SECRET_KEY")
    JWT_ALGORITHM: str = Field(default="HS256", env="JWT_ALGORITHM")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, env="ACCESS_TOKEN_EXPIRE_MINUTES")
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, env="REFRESH_TOKEN_EXPIRE_DAYS")
    BCRYPT_ROUNDS: int = Field(default=12, env="BCRYPT_ROUNDS")

    BACKEND_CORS_ORIGINS: List[str] = Field(default_factory=list, env="BACKEND_CORS_ORIGINS")

    @field_validator("SECRET_KEY", "JWT_SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("SECRET_KEY and JWT_SECRET_KEY cannot be empty")
        if len(v) < 32:
            raise ValueError("SECRET_KEY and JWT_SECRET_KEY must be at least 32 characters long")
        return v

    @field_validator("JWT_ALGORITHM")
    @classmethod
    def validate_jwt_algorithm(cls, v):
        supported_algorithms = ["HS256", "HS384", "HS512"]
        if v not in supported_algorithms:
            raise ValueError(f"JWT_ALGORITHM must be one of {supported_algorithms}")
        return v

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def parse_origins(cls, v):
        if isinstance(v, str):
            return [i.strip() for i in v.split(",") if i.strip()]
        return v

    MAIL_USERNAME: str = Field(..., env="MAIL_USERNAME")
    MAIL_PASSWORD: str = Field(..., env="MAIL_PASSWORD")
    MAIL_FROM: str = Field(..., env="MAIL_FROM")
    MAIL_PORT: int = Field(default=587, env="MAIL_PORT")
    MAIL_SERVER: str = Field(default="smtp.gmail.com", env="MAIL_SERVER")
    MAIL_STARTTLS: bool = Field(default=True, env="MAIL_STARTTLS")
    MAIL_SSL_TLS: bool = Field(default=False, env="MAIL_SSL_TLS")

    REDIS_URL: str = Field(..., env="REDIS_URL")
    CELERY_BROKER_URL: str = Field(..., env="CELERY_BROKER_URL")
    CELERY_RESULT_BACKEND: str = Field(..., env="CELERY_RESULT_BACKEND")

    MAX_FILE_SIZE: int = Field(default=10485760, env="MAX_FILE_SIZE")
    UPLOAD_FOLDER: str = Field(default="./Uploads", env="UPLOAD_FOLDER")
    ALLOWED_EXTENSIONS: List[str] = Field(default_factory=lambda: ["pdf", "doc", "docx", "jpg", "jpeg", "png"], env="ALLOWED_EXTENSIONS")

    # Safe file extensions whitelist
    SAFE_EXTENSIONS: ClassVar[Set[str]] = {
        "pdf", "doc", "docx", "txt", "rtf", "odt",
        "jpg", "jpeg", "png", "gif", "bmp", "tiff", "webp",
        "xls", "xlsx", "csv", "ods",
        "ppt", "pptx", "odp"
    }

    @field_validator("ALLOWED_EXTENSIONS", mode="before")
    @classmethod
    def validate_extensions(cls, v):
        if isinstance(v, str):
            extensions = [ext.strip().lower() for ext in v.split(",") if ext.strip()]
        else:
            extensions = [ext.lower() for ext in v if ext]
        
        # Filter against safe extensions
        safe_extensions = cls.SAFE_EXTENSIONS
        filtered = [ext for ext in extensions if ext in safe_extensions]
        
        if not filtered:
            return ["pdf", "doc", "docx", "jpg", "jpeg", "png"]  # Default safe list
        
        return filtered

    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")
    LOG_FILE: str = Field(default="./logs/app.log", env="LOG_FILE")

    DEFAULT_PAGE_SIZE: int = Field(default=50, env="DEFAULT_PAGE_SIZE")
    MAX_PAGE_SIZE: int = Field(default=100, env="MAX_PAGE_SIZE")
    DEFAULT_TIMEZONE: str = Field(default="UTC", env="DEFAULT_TIMEZONE")
    OVERTIME_THRESHOLD: float = Field(default=8.0, env="OVERTIME_THRESHOLD")

    MATERIALIZED_VIEW_REFRESH_INTERVAL: int = Field(default=3600, env="MATERIALIZED_VIEW_REFRESH_INTERVAL")

    # Static lists for validation
    ATTENDANCE_STATUSES: List[str] = Field(default_factory=lambda: [e.value for e in AttendanceStatus])
    LEAVE_TYPES: List[str] = Field(default_factory=lambda: [e.value for e in LeaveType])
    LEAVE_REQUEST_STATUSES: List[str] = Field(default_factory=lambda: [e.value for e in LeaveRequestStatus])
    CORRECTION_STATUSES: List[str] = Field(default_factory=lambda: [e.value for e in CorrectionStatus])
    SYSTEM_ACTIONS: List[str] = Field(default_factory=lambda: [e.value for e in SystemAction])
    EMPLOYEE_TYPES: List[str] = Field(default_factory=lambda: [e.value for e in EmployeeType])
    SHIFT_TYPES: List[str] = Field(default_factory=lambda: [e.value for e in ShiftType])
    VALID_SHIFT_TYPES: List[str] = Field(default_factory=lambda: [e.value for e in ShiftType])
    PERMISSION_KEYS: List[str] = Field(default_factory=lambda: [e.value for e in Permission])

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True
    )

def get_settings() -> Settings:
    """Dependency to provide Settings instance."""
    return Settings()