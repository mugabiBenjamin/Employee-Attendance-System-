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
    
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://username:password@localhost:5432/employee_attendance_db")
    DATABASE_HOST: str = os.getenv("DATABASE_HOST", "localhost")
    DATABASE_PORT: int = int(os.getenv("DATABASE_PORT", 5432))
    DATABASE_NAME: str = os.getenv("DATABASE_NAME", "employee_attendance_db")
    DATABASE_USER: str = os.getenv("DATABASE_USER", "username")
    DATABASE_PASSWORD: str = os.getenv("DATABASE_PASSWORD", "password")
    
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-this-to-a-random-secret-key")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 7))
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    BCRYPT_ROUNDS: int = int(os.getenv("BCRYPT_ROUNDS", 12))
    
    BACKEND_CORS_ORIGINS: List[str] = [
        x.strip() for x in os.getenv("BACKEND_CORS_ORIGINS", "http://localhost:3000,http://localhost:8000").split(",")
    ]
    
    MAIL_USERNAME: str = os.getenv("MAIL_USERNAME", "your-email@example.com")
    MAIL_PASSWORD: str = os.getenv("MAIL_PASSWORD", "your-app-password")
    MAIL_FROM: str = os.getenv("MAIL_FROM", "your-email@example.com")
    MAIL_PORT: int = int(os.getenv("MAIL_PORT", 587))
    MAIL_SERVER: str = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    MAIL_STARTTLS: bool = os.getenv("MAIL_STARTTLS", "True").lower() == "true"
    MAIL_SSL_TLS: bool = os.getenv("MAIL_SSL_TLS", "False").lower() == "true"
    
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
    
    MAX_FILE_SIZE: int = int(os.getenv("MAX_FILE_SIZE", 10485760))
    UPLOAD_FOLDER: str = os.getenv("UPLOAD_FOLDER", "./uploads")
    ALLOWED_EXTENSIONS: List[str] = [
        x.strip() for x in os.getenv("ALLOWED_EXTENSIONS", "pdf,doc,docx,jpg,jpeg,png").split(",")
    ]
    
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = os.getenv("LOG_FILE", "./logs/app.log")
    
    DEFAULT_PAGE_SIZE: int = int(os.getenv("DEFAULT_PAGE_SIZE", 50))
    MAX_PAGE_SIZE: int = int(os.getenv("MAX_PAGE_SIZE", 100))
    
    DEFAULT_TIMEZONE: str = os.getenv("DEFAULT_TIMEZONE", "UTC")
    
    class Config:
        case_sensitive = True
        env_file = Path(__file__).parent.parent.parent.parent / ".env"
        env_file_encoding = "utf-8"

settings = Settings()