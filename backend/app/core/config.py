from typing import List, ClassVar, Set, Dict, Tuple
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

    REQUIRE_ATTENDANCE_LOCATION: bool = Field(default=False, env="REQUIRE_ATTENDANCE_LOCATION")
    REQUIRE_ATTENDANCE_IP: bool = Field(default=False, env="REQUIRE_ATTENDANCE_IP")  # Added setting
    CHECK_HOLIDAYS_ON_ATTENDANCE: bool = Field(default=True, env="CHECK_HOLIDAYS_ON_ATTENDANCE")
    NOTIFY_ON_ATTENDANCE: bool = Field(default=True, env="NOTIFY_ON_ATTENDANCE")
    MINIMUM_SHIFT_DURATION: float = Field(default=4.0, env="MINIMUM_SHIFT_DURATION")
    MAX_EMERGENCY_CONTACTS: int = Field(default=3, env="MAX_EMERGENCY_CONTACTS")
    MAX_WORKFLOW_LEVELS: int = Field(default=5, env="MAX_WORKFLOW_LEVELS")
    PREVENT_DELETE_APPROVED_WORKFLOW: bool = Field(default=True, env="PREVENT_DELETE_APPROVED_WORKFLOW")
    MAX_BALANCE_CHANGE: float = Field(default=30.0, env="MAX_BALANCE_CHANGE")
    PREVENT_NEGATIVE_ALLOCATION: bool = Field(default=True, env="PREVENT_NEGATIVE_ALLOCATION")
    CHECK_HOLIDAYS_ON_LEAVE: bool = Field(default=True, env="CHECK_HOLIDAYS_ON_LEAVE")
    PREVENT_DELETE_APPROVED_LEAVE: bool = Field(default=True, env="PREVENT_DELETE_APPROVED_LEAVE")
    PREVENT_DELETE_APPROVED_OVERTIME: bool = Field(default=True, env="PREVENT_DELETE_APPROVED_OVERTIME")
    CHECK_HOLIDAYS_ON_OVERTIME: bool = Field(default=True, env="CHECK_HOLIDAYS_ON_OVERTIME")
    DEFAULT_OVERTIME_RATE: float = Field(default=1.5, env="DEFAULT_OVERTIME_RATE")
    REQUIRE_ACTIVE_SHIFT_ASSIGNMENT: bool = Field(default=True, env="REQUIRE_ACTIVE_SHIFT_ASSIGNMENT")
    MAX_TIME_CORRECTION_HOURS: float = Field(default=12.0, env="MAX_TIME_CORRECTION_HOURS")
    PREVENT_INVALID_TIME_CORRECTIONS: bool = Field(default=True, env="PREVENT_INVALID_TIME_CORRECTIONS")

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

    # System action and route table mappings for middleware
    ACTION_MAPPING: Dict[Tuple[str, str], str] = Field(
        default_factory=lambda: {
            ("/auth/token", "POST"): SystemAction.LOGIN.value,
            ("/auth/logout", "POST"): SystemAction.LOGOUT.value,
            ("/attendance/clock_in", "POST"): SystemAction.CLOCK_IN.value,
            ("/attendance/clock_out", "POST"): SystemAction.CLOCK_OUT.value,
            ("/users/password", "PUT"): SystemAction.PASSWORD_CHANGE.value,
            ("/users/me", "PUT"): SystemAction.PROFILE_UPDATE.value,
            ("/users/export", "GET"): SystemAction.DATA_EXPORT.value,
            ("/users/import", "POST"): SystemAction.DATA_IMPORT.value,
            ("/users/roles", "POST"): SystemAction.ASSIGN_ROLE.value,
            ("/users/roles", "DELETE"): SystemAction.REVOKE_ROLE.value,
            ("/reports", "GET"): SystemAction.VIEW_REPORT.value,
            ("/leave/approve", "POST"): SystemAction.APPROVE_LEAVE.value,
            ("/leave/reject", "POST"): SystemAction.REJECT_LEAVE.value,
            ("/departments", "POST"): SystemAction.CREATE_DEPARTMENT.value,
            ("/departments", "DELETE"): SystemAction.DELETE_DEPARTMENT.value,
            ("/holidays", "DELETE"): SystemAction.DELETE_HOLIDAY.value,
            ("/overtime", "POST"): SystemAction.CREATE_OVERTIME_RECORD.value,
            ("/roles", "PUT"): SystemAction.UPDATE_ROLE.value,
            ("/roles", "DELETE"): SystemAction.DELETE_ROLE.value,
            ("/departments", "PUT"): SystemAction.UPDATE_DEPARTMENT.value,
            ("/emergency-contacts", "DELETE"): SystemAction.DELETE_EMERGENCY_CONTACT.value,
            ("/emergency-contacts", "PUT"): SystemAction.UPDATE_EMERGENCY_CONTACT.value,
            ("/emergency-contacts", "POST"): SystemAction.CREATE_EMERGENCY_CONTACT.value,
            ("/hierarchy", "DELETE"): SystemAction.DELETE_HIERARCHY.value,
            ("/hierarchy", "PUT"): SystemAction.UPDATE_HIERARCHY.value,
            ("/hierarchy", "POST"): SystemAction.CREATE_HIERARCHY.value,
            ("/holidays", "PUT"): SystemAction.UPDATE_HOLIDAY.value,
            ("/holidays", "POST"): SystemAction.CREATE_HOLIDAY.value,
            ("/workflows", "POST"): SystemAction.DEFINE_WORKFLOW.value,
            ("/leave_balances", "PUT"): SystemAction.UPDATE_LEAVE_BALANCE.value,
            ("/leave_policies", "DELETE"): SystemAction.DELETE_LEAVE_POLICY.value,
            ("/leave_policies", "PUT"): SystemAction.UPDATE_LEAVE_POLICY.value,
            ("/leave_policies", "POST"): SystemAction.CREATE_LEAVE_POLICY.value,
            ("/leave_requests", "POST"): SystemAction.CREATE_LEAVE_REQUEST.value,
            ("/leave_requests/approve", "POST"): SystemAction.APPROVE_LEAVE_REQUEST.value,
            ("/overtime/approve", "POST"): SystemAction.APPROVE_OVERTIME_RECORD.value,
        }
    )
    ROUTE_TABLE_MAPPING: Dict[str, str] = Field(
        default_factory=lambda: {
            "/auth/token": "users",
            "/auth/logout": "users",
            "/attendance/clock_in": "attendance_records",
            "/attendance/clock_out": "attendance_records",
            "/users/password": "users",
            "/users/me": "users",
            "/users/export": "users",
            "/users/import": "users",
            "/users/roles": "user_roles",
            "/reports": "attendance_records",
            "/leave/approve": "leave_requests",
            "/leave/reject": "leave_requests",
            "/departments": "departments",
            "/holidays": "holiday_calendar",
            "/overtime": "overtime_records",
            "/roles": "roles",
            "/emergency_contacts": "employee_emergency_contacts",
            "/hierarchy": "employee_hierarchy",
            "/workflows": "leave_approval_workflow",
            "/leave_balances": "leave_balances",
            "/leave_policies": "leave_policies",
            "/leave_requests": "leave_requests",
            "/leave_requests/approve": "leave_requests",
            "/overtime/approve": "overtime_records",
        }
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True
    )

# Singleton instance
_settings_instance = None

def get_settings() -> Settings:
    """Return a singleton instance of Settings."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance

# Export the singleton instance for direct import
settings = get_settings()