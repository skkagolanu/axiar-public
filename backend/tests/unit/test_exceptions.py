"""
Unit tests for centralized exception handling

"""

import pytest
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.exceptions import (
    AppException,
    BookingConflictError,
    ForbiddenException,
    NotFoundException,
    PaymentFailedError,
    UnauthorizedException,
    ValidationException,
    app_exception_handler,
    database_exception_handler,
    generic_exception_handler,
    validation_exception_handler,
)


@pytest.mark.asyncio
async def test_app_exception_handler():
    """Test custom app exception handler"""
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "url": "http://test/api/test",
            "path": "/api/test",
            "headers": [],
            "query_string": b"",
        }
    )
    exc = AppException("Test error", status.HTTP_400_BAD_REQUEST, "TEST_ERROR")

    response = await app_exception_handler(request, exc)

    assert response.status_code == 400
    body = response.body.decode()
    assert "TEST_ERROR" in body
    assert "Test error" in body
    assert "error_id" in body


@pytest.mark.asyncio
async def test_validation_exception():
    """Test validation exception"""
    exc = ValidationException("Invalid input")

    assert exc.status_code == 400
    assert exc.error_code == "VALIDATION_ERROR"
    assert exc.message == "Invalid input"


@pytest.mark.asyncio
async def test_not_found_exception():
    """Test not found exception"""
    exc = NotFoundException("User")

    assert exc.status_code == 404
    assert exc.error_code == "NOT_FOUND"
    assert "User not found" in exc.message


@pytest.mark.asyncio
async def test_unauthorized_exception():
    """Test unauthorized exception"""
    exc = UnauthorizedException("Invalid token")

    assert exc.status_code == 401
    assert exc.error_code == "UNAUTHORIZED"
    assert exc.message == "Invalid token"


@pytest.mark.asyncio
async def test_forbidden_exception():
    """Test forbidden exception"""
    exc = ForbiddenException("Insufficient permissions")

    assert exc.status_code == 403
    assert exc.error_code == "FORBIDDEN"
    assert exc.message == "Insufficient permissions"


@pytest.mark.asyncio
async def test_booking_conflict_error():
    """Test booking conflict error"""
    exc = BookingConflictError("Time slot unavailable")

    assert exc.status_code == 409
    assert exc.error_code == "BOOKING_CONFLICT"
    assert exc.message == "Time slot unavailable"


@pytest.mark.asyncio
async def test_payment_failed_error():
    """Test payment failed error"""
    exc = PaymentFailedError("Card declined")

    assert exc.status_code == 402
    assert exc.error_code == "PAYMENT_FAILED"
    assert exc.message == "Card declined"


@pytest.mark.asyncio
async def test_database_exception_handler():
    """Test database exception handler - no schema details exposed"""
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "url": "http://test/api/test",
            "path": "/api/test",
            "headers": [],
            "query_string": b"",
        }
    )
    exc = IntegrityError("statement", "params", "orig")

    response = await database_exception_handler(request, exc)

    assert response.status_code == 409  # IntegrityError is a client/constraint conflict, not a server fault
    body = response.body.decode()
    assert "INTEGRITY_ERROR" in body
    assert "error_id" in body
    # Should NOT contain internal details
    assert "statement" not in body
    assert "params" not in body


@pytest.mark.asyncio
async def test_generic_exception_handler():
    """Test generic exception handler - no stack traces exposed"""
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "url": "http://test/api/test",
            "path": "/api/test",
            "headers": [],
            "query_string": b"",
        }
    )
    exc = Exception("Internal error")

    response = await generic_exception_handler(request, exc)

    assert response.status_code == 500
    body = response.body.decode()
    assert "INTERNAL_ERROR" in body
    assert "error_id" in body
    # Should NOT contain stack trace
    assert "Traceback" not in body
    assert "Internal error" not in body  # Generic message only


@pytest.mark.asyncio
async def test_error_id_uniqueness():
    """Test that error IDs are unique"""
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "url": "http://test/api/test",
            "path": "/api/test",
            "headers": [],
            "query_string": b"",
        }
    )
    exc1 = AppException("Error 1")
    exc2 = AppException("Error 2")

    response1 = await app_exception_handler(request, exc1)
    response2 = await app_exception_handler(request, exc2)

    body1 = response1.body.decode()
    body2 = response2.body.decode()

    # Extract error IDs (they should be different)
    assert body1 != body2
