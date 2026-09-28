"""
Custom exceptions used across the user/team/project-board APIs.

Keeping a small, explicit hierarchy makes it easy for the Django view
layer to translate application errors into sensible HTTP status codes
without inspecting error strings.
"""


class ApplicationError(Exception):
    """Base class for all handled application errors."""
    status_code = 400


class ValidationError(ApplicationError):
    """Raised when input data fails a documented constraint."""
    status_code = 400


class NotFoundError(ApplicationError):
    """Raised when a referenced entity (user/team/board/task) does not exist."""
    status_code = 404


class ConflictError(ApplicationError):
    """Raised when a uniqueness constraint is violated (duplicate name, etc.)."""
    status_code = 409
