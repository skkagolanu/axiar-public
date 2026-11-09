"""Common schemas for API responses"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Standard error response"""

    detail: str
    error_code: Optional[str] = None
    field_errors: Optional[Dict[str, str]] = None


class SuccessResponse(BaseModel):
    """Standard success response"""

    message: str
    data: Optional[Any] = None


class HealthResponse(BaseModel):
    """Health check response"""

    status: str
    version: str
    database: str
    cache: str


class MessageResponse(BaseModel):
    """Simple message response"""

    message: str


class PaginatedResponse(BaseModel):
    """Paginated list response"""

    items: List[Any]
    total: int
    page: int
    page_size: int
    total_pages: int
