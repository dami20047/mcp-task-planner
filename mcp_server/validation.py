"""
Input sanitization for everything the add_task tool accepts.

This is Best Practice #1 (Input Sanitization). The goal is to reject
anything that looks like an injection attempt -- SQL metacharacters,
shell metacharacters, path traversal, etc. -- *before* it ever leaves the
MCP server and reaches the task service or its database. We use an
allow-list (only characters a real task title/date/priority would ever
need) rather than a deny-list of "bad" characters, because deny-lists are
easy to bypass by encoding or by a character nobody thought to block.

exploits/test_input_sanitization.py sends several classic payloads
through `validate_title` / `validate_due_date` / `validate_priority` and
confirms every one of them is rejected.
"""

import re
from datetime import date, datetime

TITLE_MAX_LEN = 200

# Letters, numbers, spaces, and a small set of punctuation that ordinary
# task titles need. Notably excluded: quotes, backticks, semicolons,
# pipes, angle brackets, dollar signs, backslashes -- the characters that
# do the work in SQL injection (' ; --) and shell/command injection
# ($() `` | ; &&) payloads.
_TITLE_PATTERN = re.compile(r"^[A-Za-z0-9 .,!?():/_-]+$")

ALLOWED_PRIORITIES = {"low", "medium", "high"}


class ValidationError(ValueError):
    """Raised when user-supplied input fails sanitization.

    The message on this exception is always safe to show back to the
    caller (it never echoes the rejected input verbatim, so a payload
    can't use the error message itself as a reflection channel).
    """


def validate_title(title: str) -> str:
    title = title.strip()
    if not title:
        raise ValidationError("Task title cannot be empty.")
    if len(title) > TITLE_MAX_LEN:
        raise ValidationError(f"Task title cannot exceed {TITLE_MAX_LEN} characters.")
    if not _TITLE_PATTERN.match(title):
        raise ValidationError(
            "Task title contains characters that are not allowed "
            "(only letters, numbers, spaces, and basic punctuation "
            ".,!?():/_- are permitted)."
        )
    return title


def validate_due_date(due_date: str) -> str:
    due_date = due_date.strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", due_date):
        raise ValidationError("Due date must be in YYYY-MM-DD format.")
    try:
        parsed = datetime.strptime(due_date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValidationError("Due date is not a real calendar date.") from exc
    if parsed < date.today():
        raise ValidationError("Due date cannot be in the past.")
    return due_date


def validate_priority(priority: str) -> str:
    priority = priority.strip().lower()
    if priority not in ALLOWED_PRIORITIES:
        raise ValidationError(
            f"Priority must be one of: {', '.join(sorted(ALLOWED_PRIORITIES))}."
        )
    return priority
