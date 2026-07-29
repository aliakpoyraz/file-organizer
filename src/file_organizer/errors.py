"""Exception hierarchy for file-organizer.

The CLI catches :class:`OrganizerError` and exits with a clean, non-zero
message. Any other (unexpected) exception is allowed to propagate and, under
``--verbose``, its traceback is shown.
"""

from __future__ import annotations


class OrganizerError(Exception):
    """Base class for all expected, user-facing errors."""


class ConfigError(OrganizerError):
    """Raised when configuration is invalid or cannot be loaded."""


class RuleError(OrganizerError):
    """Raised when a rule or template cannot be evaluated."""


class MoveError(OrganizerError):
    """Raised when a filesystem move fails."""


class UndoError(OrganizerError):
    """Raised when an undo operation cannot be completed."""


class PermissionDeniedError(OrganizerError):
    """Raised when a destination directory is not writable."""
