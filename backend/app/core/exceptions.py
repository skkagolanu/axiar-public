"""Centralized API exceptions and response handlers with sanitized client messages."""

import logging
import uuid

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

logger = logging.getLogger(__name__)


class AppException(Exception):
    """Base application exception"""

    def __init__(self, message: str, status_code: int = 500, error_code: str = "INTERNAL_ERROR"):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(self.message)


class ValidationException(AppException):
    """Validation error"""

    def __init__(self, message: str):
        super().__init__(message, status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR")


class NotFoundException(AppException):
    """Resource not found"""

    def __init__(self, resource: str):
        super().__init__(f"{resource} not found", status.HTTP_404_NOT_FOUND, "NOT_FOUND")


class UnauthorizedException(AppException):
    """Unauthorized access"""

    def __init__(self, message: str = "Unauthorized"):
        super().__init__(message, status.HTTP_401_UNAUTHORIZED, "UNAUTHORIZED")


class ForbiddenException(AppException):
    """Forbidden access"""

    def __init__(self, message: str = "Access denied"):
        super().__init__(message, status.HTTP_403_FORBIDDEN, "FORBIDDEN")


# Aliases for backward compatibility
class AuthenticationError(UnauthorizedException):
    """Alias for UnauthorizedException"""

    pass


class AuthorizationError(ForbiddenException):
    """Alias for ForbiddenException"""

    pass


class BookingConflictError(AppException):
    """Booking conflict error"""

    def __init__(self, message: str = "Booking conflict detected"):
        super().__init__(message, status.HTTP_409_CONFLICT, "BOOKING_CONFLICT")


class PaymentFailedError(AppException):
    """Payment failed error"""

    def __init__(self, message: str = "Payment processing failed"):
        super().__init__(message, status.HTTP_402_PAYMENT_REQUIRED, "PAYMENT_FAILED")


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handle application exceptions"""
    error_id = str(uuid.uuid4())

    # Log with error ID for tracking
    logger.error(f"Error {error_id}: {exc.error_code} - {exc.message}", extra={"error_id": error_id, "path": request.url.path})

    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.error_code, "message": exc.message, "error_id": error_id},
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle validation errors - sanitize field names"""
    error_id = str(uuid.uuid4())

    # Sanitize validation errors - don't expose internal field names
    errors = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"] if loc != "body")
        errors.append({"field": field, "message": error["msg"]})

    logger.warning(
        f"Validation error {error_id}: {len(errors)} fields", extra={"error_id": error_id, "path": request.url.path}
    )

    return JSONResponse(
        # 422 literal: the named constant was renamed in newer Starlette and accessing
        # the old name raises a DeprecationWarning.
        status_code=422,
        content={"error": "VALIDATION_ERROR", "message": "Invalid input data", "details": errors, "error_id": error_id},
    )


async def database_exception_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    """Handle database errors - never expose schema details"""
    error_id = str(uuid.uuid4())

    # Log full error internally
    logger.error(
        f"Database error {error_id}: {type(exc).__name__}",
        exc_info=True,
        extra={"error_id": error_id, "path": request.url.path},
    )

    # A constraint / FK / unique violation is caused by the request data (referencing
    # non-existent or conflicting entities) — a client error (409), not a server fault (500).
    if isinstance(exc, IntegrityError):
        status_code = status.HTTP_409_CONFLICT
        message = "Data integrity constraint violated"
        error_code = "INTEGRITY_ERROR"
    else:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        message = "Database operation failed"
        error_code = "DATABASE_ERROR"

    return JSONResponse(
        status_code=status_code,
        content={"error": error_code, "message": message, "error_id": error_id},
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected errors - never expose stack traces"""
    error_id = str(uuid.uuid4())

    # Log full error internally
    logger.error(
        f"Unexpected error {error_id}: {type(exc).__name__}",
        exc_info=True,
        extra={"error_id": error_id, "path": request.url.path},
    )

    # Generic message for user
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "INTERNAL_ERROR",
            "message": "An unexpected error occurred. Please contact support with error ID.",
            "error_id": error_id,
        },
    )
