import logging
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError
from app.core.exceptions import BaseCustomException
from app.core.utils import get_request_id

logger = logging.getLogger(__name__)

def setup_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BaseCustomException)
    async def custom_exception_handler(request: Request, exc: BaseCustomException):
        request_id = get_request_id(request)
        logger.warning(
            f"Custom exception: {exc.detail}", 
            extra={"request_id": request_id, "error_code": exc.error_code}
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": exc.detail, 
                "error_code": exc.error_code, 
                "request_id": request_id
            },
            headers=exc.headers
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        request_id = get_request_id(request)
        logger.warning(f"Validation error: {exc.errors()}", extra={"request_id": request_id})
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "detail": "Invalid input data", 
                "errors": exc.errors(), 
                "request_id": request_id
            }
        )

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
        request_id = get_request_id(request)
        logger.error(f"Database error: {str(exc)}", extra={"request_id": request_id})
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "Internal server error. Database operation failed.", 
                "error_code": "DATABASE_ERROR",
                "request_id": request_id
            }
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        request_id = get_request_id(request)
        logger.error(f"Unhandled exception: {str(exc)}", extra={"request_id": request_id}, exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "An unexpected error occurred.", 
                "error_code": "INTERNAL_ERROR",
                "request_id": request_id
            }
        )