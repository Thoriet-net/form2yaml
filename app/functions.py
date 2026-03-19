from typing import Any


def to_upper(value: Any) -> str:
    """Convert value to uppercase string."""
    if value is None:
        return ""
    return str(value).upper()


def to_lower(value: Any) -> str:
    """Convert value to lowercase string."""
    if value is None:
        return ""
    return str(value).lower()


def default_if_empty(value: Any, default: Any = "") -> Any:
    """Return default if value is empty or None."""
    if value in (None, "", []):
        return default
    return value


def trim(value: Any) -> str:
    """Strip whitespace from string."""
    if value is None:
        return ""
    return str(value).strip()