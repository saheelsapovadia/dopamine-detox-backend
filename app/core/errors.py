"""
Error Handling
==============

Standardized error codes and exception handlers.
"""

from typing import Any, Optional

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse


# =============================================================================
# Error Codes
# =============================================================================

class ErrorCodes:
    """Standardized error codes."""
    
    # Authentication (AUTH_001 - AUTH_010)
    AUTH_INVALID_CREDENTIALS = "AUTH_001"
    AUTH_TOKEN_EXPIRED = "AUTH_002"
    AUTH_ACCOUNT_LOCKED = "AUTH_003"
    AUTH_EMAIL_EXISTS = "AUTH_004"
    AUTH_INVALID_TOKEN = "AUTH_005"
    
    # Tasks (TASK_001 - TASK_010)
    TASK_NOT_FOUND = "TASK_001"
    TASK_PLAN_EXISTS = "TASK_002"
    TASK_PLAN_NOT_FOUND = "TASK_003"
    TASK_INVALID_DATA = "TASK_004"
    TASK_HIGH_PRIORITY_CONFLICT = "CONFLICT"
    
    # User Tasks (v2 HomeScreen API)
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    USER_NOT_FOUND = "USER_NOT_FOUND"
    
    # Journal (JOURNAL_001 - JOURNAL_010)
    JOURNAL_ENTRY_EXISTS = "JOURNAL_001"
    JOURNAL_TRANSCRIPTION_FAILED = "JOURNAL_002"
    JOURNAL_NOT_FOUND = "JOURNAL_003"
    JOURNAL_INVALID_DATE = "JOURNAL_004"
    JOURNAL_LIMIT_REACHED = "JOURNAL_005"
    
    # Subscription (SUB_001 - SUB_010)
    SUB_INVALID_PACKAGE = "SUB_001"
    SUB_PAYMENT_FAILED = "SUB_002"
    SUB_ALREADY_ACTIVE = "SUB_003"
    SUB_NO_ACTIVE_SUB = "SUB_004"
    SUB_ALREADY_CANCELLED = "SUB_005"
    SUB_NO_PURCHASES = "SUB_006"
    
    # Voice (VOICE_001 - VOICE_010)
    VOICE_INVALID_FORMAT = "VOICE_001"
    VOICE_TOO_SHORT = "VOICE_002"
    VOICE_SERVICE_UNAVAILABLE = "VOICE_003"
    VOICE_FILE_TOO_LARGE = "VOICE_004"
    
    # Feature (FEATURE_001 - FEATURE_010)
    FEATURE_LOCKED = "FEATURE_001"
    
    # Rate Limit
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT"
    
    # General
    INTERNAL_ERROR = "INTERNAL_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"


# =============================================================================
# Custom Exceptions
# =============================================================================

class AppException(HTTPException):
    """Base application exception with structured error response."""
    
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        field: Optional[str] = None,
        **extra,
    ):
        self.code = code
        self.field = field
        self.extra = extra
        
        detail = {
            "code": code,
            "message": message,
        }
        
        if field:
            detail["field"] = field
        
        detail.update(extra)
        
        super().__init__(status_code=status_code, detail=detail)


class AuthenticationError(AppException):
    """Authentication-related errors."""
    
    def __init__(
        self,
        code: str = ErrorCodes.AUTH_INVALID_CREDENTIALS,
        message: str = "Authentication failed",
        **extra,
    ):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code=code,
            message=message,
            **extra,
        )


class NotFoundError(AppException):
    """Resource not found errors."""
    
    def __init__(
        self,
        code: str = ErrorCodes.NOT_FOUND,
        message: str = "Resource not found",
        **extra,
    ):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            code=code,
            message=message,
            **extra,
        )


class ConflictError(AppException):
    """Resource conflict errors."""
    
    def __init__(
        self,
        code: str,
        message: str,
        **extra,
    ):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            code=code,
            message=message,
            **extra,
        )


class ForbiddenError(AppException):
    """Permission/feature access errors."""
    
    def __init__(
        self,
        code: str = ErrorCodes.FEATURE_LOCKED,
        message: str = "Access denied",
        **extra,
    ):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            code=code,
            message=message,
            **extra,
        )


class ValidationError(AppException):
    """Validation errors."""
    
    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        **extra,
    ):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=ErrorCodes.VALIDATION_ERROR,
            message=message,
            field=field,
            **extra,
        )


class ServiceUnavailableError(AppException):
    """External service unavailable errors."""
    
    def __init__(
        self,
        code: str,
        message: str = "Service temporarily unavailable",
        **extra,
    ):
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code=code,
            message=message,
            **extra,
        )


# =============================================================================
# Exception Handlers
# =============================================================================

async def app_exception_handler(
    request: Request,
    exc: AppException,
) -> JSONResponse:
    """Handler for AppException."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": exc.detail,
        },
    )


async def http_exception_handler(
    request: Request,
    exc: HTTPException,
) -> JSONResponse:
    """Handler for standard HTTPException."""
    # Check if detail is already structured
    if isinstance(exc.detail, dict) and "code" in exc.detail:
        error = exc.detail
    else:
        error = {
            "code": "HTTP_ERROR",
            "message": str(exc.detail),
        }
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": error,
        },
    )


async def validation_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Handler for Pydantic validation errors."""
    from pydantic import ValidationError as PydanticValidationError
    
    if isinstance(exc, PydanticValidationError):
        errors = exc.errors()
        if errors:
            first_error = errors[0]
            field = ".".join(str(loc) for loc in first_error.get("loc", []))
            message = first_error.get("msg", "Validation error")
        else:
            field = None
            message = "Validation error"
        
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "success": False,
                "error": {
                    "code": ErrorCodes.VALIDATION_ERROR,
                    "message": message,
                    "field": field,
                    "details": errors,
                },
            },
        )
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "error": {
                "code": ErrorCodes.VALIDATION_ERROR,
                "message": str(exc),
            },
        },
    )


async def global_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Handler for unhandled exceptions."""
    # Log the error
    print(f"Unhandled error: {type(exc).__name__}: {exc}")
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": {
                "code": ErrorCodes.INTERNAL_ERROR,
                "message": "An unexpected error occurred",
            },
        },
    )


def setup_exception_handlers(app):
    """
    Register exception handlers with FastAPI app.
    
    Usage:
        from app.core.errors import setup_exception_handlers
        setup_exception_handlers(app)
    """
    from pydantic import ValidationError as PydanticValidationError
    from fastapi.exceptions import RequestValidationError
    
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(PydanticValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, global_exception_handler)
