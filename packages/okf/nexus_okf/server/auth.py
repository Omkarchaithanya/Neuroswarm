"""Optional auth hooks for OKF serve."""

from __future__ import annotations


def allow_read(visibility: str, roles: list[str]) -> bool:
    if visibility in {"public", "internal"}:
        return True
    if visibility == "private":
        return "role:human" in roles or "role:agent" in roles
    if visibility == "restricted":
        return "role:architect" in roles
    return False
