"""Small dependency-free JSON Schema subset for MCP boundary validation."""

from __future__ import annotations

from typing import Any

_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "null": type(None),
}


def validate_schema(value: Any, schema: dict[str, Any], *, path: str = "$") -> None:
    expected = schema.get("type")
    if expected:
        expected_type = _TYPES.get(expected)
        if expected_type is None:
            raise ValueError(f"{path}: unsupported schema type {expected}")
        if expected == "integer" and isinstance(value, bool):
            raise ValueError(f"{path}: expected integer")
        if not isinstance(value, expected_type):
            raise ValueError(f"{path}: expected {expected}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path}: value is not in enum")
    if isinstance(value, dict):
        required = schema.get("required", ())
        missing = [name for name in required if name not in value]
        if missing:
            raise ValueError(f"{path}: required fields missing: {missing}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            unknown = set(value) - set(properties)
            if unknown:
                raise ValueError(f"{path}: unknown fields: {sorted(unknown)}")
        for name, item in value.items():
            if name in properties:
                validate_schema(item, properties[name], path=f"{path}.{name}")
    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            validate_schema(item, schema["items"], path=f"{path}[{index}]")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            raise ValueError(f"{path}: string is too short")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            raise ValueError(f"{path}: string is too long")
