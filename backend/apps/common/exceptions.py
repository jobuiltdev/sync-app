"""The API's standard error envelope.

Every error response has the same shape:

    {"error": {"code": "SOME_MACHINE_CODE", "message": "...", "details": {}}}

`code` is stable and is what clients branch on. `message` is for humans and may be
reworded at any time. `details` carries structured, code-specific context, and is
an object rather than being omitted so clients never have to test for its absence.
"""

from typing import Any

from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

GENERIC_ERROR_CODE = "ERROR"
VALIDATION_ERROR_CODE = "VALIDATION_ERROR"
VALIDATION_ERROR_MESSAGE = "The submitted data was invalid."


class APIError(exceptions.APIException):
    """An error that carries an explicit machine-readable code.

    Domain code raises subclasses of this so that the code travelling to the
    client is chosen deliberately rather than derived from a DRF internal.
    """

    status_code: int = status.HTTP_400_BAD_REQUEST
    default_code = GENERIC_ERROR_CODE
    default_detail = "The request could not be processed."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
        status_code: int | None = None,
    ) -> None:
        self.details: dict[str, Any] = details or {}
        if status_code is not None:
            self.status_code = status_code
        super().__init__(detail=message or self.default_detail, code=code or self.default_code)


def _error_code(exc: Exception) -> str:
    if isinstance(exc, Http404):
        return "NOT_FOUND"
    if isinstance(exc, exceptions.ValidationError):
        return VALIDATION_ERROR_CODE

    code = getattr(exc, "default_code", None)
    detail = getattr(exc, "detail", None)
    if isinstance(detail, exceptions.ErrorDetail) and detail.code:
        code = detail.code
    return str(code or GENERIC_ERROR_CODE).upper()


def _error_message(exc: Exception) -> str:
    if isinstance(exc, exceptions.ValidationError):
        return VALIDATION_ERROR_MESSAGE

    detail = getattr(exc, "detail", None)
    if isinstance(detail, str):
        return str(detail)
    return str(exc) or "The request could not be processed."


def _error_details(exc: Exception, response: Response) -> dict[str, Any]:
    if isinstance(exc, APIError):
        return exc.details
    if isinstance(exc, exceptions.ValidationError):
        # DRF renders field errors as a dict, or as a list when the error was
        # raised against the serializer as a whole.
        return (
            {"fields": response.data}
            if isinstance(response.data, dict)
            else {"errors": response.data}
        )
    return {}


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """Rewrite DRF's default error payloads into the standard envelope.

    Returning None hands the exception back to Django, which is what should happen
    for anything DRF does not recognise: an unexpected error is a 500 and a logged
    traceback, not a tidy envelope that hides a bug.
    """
    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    response.data = {
        "error": {
            "code": _error_code(exc),
            "message": _error_message(exc),
            "details": _error_details(exc, response),
        }
    }
    return response
