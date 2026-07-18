"""Vista segura y acotada de un Plan para clientes Home."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence

from core.domain.home import JsonValue
from core.domain.plan import Action

_MAX_DEPTH = 4
_MAX_ITEMS = 16
_MAX_STRING = 256
_SENSITIVE_FRAGMENTS = (
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "credential",
    "oauth",
    "password",
    "private_key",
    "secret",
    "token",
)


def _is_sensitive(name: str) -> bool:
    normalized = name.casefold().replace("-", "_")
    return any(fragment in normalized for fragment in _SENSITIVE_FRAGMENTS)


def _bounded_string(value: str) -> JsonValue:
    if len(value) <= _MAX_STRING:
        return value
    return {
        "preview": value[:_MAX_STRING],
        "truncated": True,
        "characters": len(value),
        "sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
    }


def _preview_value(value: object, *, depth: int) -> JsonValue:
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return _bounded_string(value)
    if depth >= _MAX_DEPTH:
        return {"truncated": True, "reason": "max_depth"}
    if isinstance(value, Mapping):
        result: dict[str, JsonValue] = {}
        entries = sorted(
            ((str(key), item) for key, item in value.items()), key=lambda pair: pair[0]
        )
        for key, item in entries[:_MAX_ITEMS]:
            result[key] = (
                {"redacted": True} if _is_sensitive(key) else _preview_value(item, depth=depth + 1)
            )
        if len(entries) > _MAX_ITEMS:
            result["_truncated_entries"] = len(entries) - _MAX_ITEMS
        return result
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        items = [_preview_value(item, depth=depth + 1) for item in value[:_MAX_ITEMS]]
        if len(value) > _MAX_ITEMS:
            items.append({"truncated": True, "remaining_items": len(value) - _MAX_ITEMS})
        return items
    return _bounded_string(str(value))


def home_action_step(action: Action) -> dict[str, JsonValue]:
    """Expone el efecto material sin proyectar secretos ni payloads sin límite."""
    parameters: dict[str, JsonValue] = {}
    for key, value in sorted(action.parameters.items()):
        name = str(key)
        parameters[name] = (
            {"redacted": True} if _is_sensitive(name) else _preview_value(value, depth=0)
        )
    return {
        "description": action.type,
        "target": action.target,
        "parameters": parameters,
    }
