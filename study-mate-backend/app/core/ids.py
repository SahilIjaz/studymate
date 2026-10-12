"""Opaque identifiers."""

from __future__ import annotations

import re
import secrets
import uuid

WORKSPACE_ID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(12)}"


def new_workspace_id() -> str:
    return str(uuid.uuid4())


def is_workspace_id(value: str) -> bool:
    return bool(WORKSPACE_ID_RE.match(value))
