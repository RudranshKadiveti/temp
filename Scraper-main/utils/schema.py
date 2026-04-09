from __future__ import annotations

from typing import Any


def infer_schema(records: list[dict[str, Any]]) -> dict[str, str]:
    schema: dict[str, str] = {}
    for record in records:
        for key, value in record.items():
            if value is None:
                continue
            dtype = type(value).__name__
            prev = schema.get(key)
            if prev is None:
                schema[key] = dtype
            elif prev != dtype:
                schema[key] = "mixed"
    return schema


def align_records(records: list[dict[str, Any]], known_fields: set[str]) -> list[dict[str, Any]]:
    aligned = []
    for record in records:
        for key in list(record.keys()):
            known_fields.add(key)
        aligned.append(record)

    result = []
    ordered = sorted(known_fields)
    for record in aligned:
        result.append({key: record.get(key) for key in ordered})
    return result
