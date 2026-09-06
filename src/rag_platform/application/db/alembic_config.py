from __future__ import annotations


def escape_config_value(value: str) -> str:
    """Escape percent signs before storing a value in Alembic's ConfigParser."""
    return value.replace("%", "%%")
