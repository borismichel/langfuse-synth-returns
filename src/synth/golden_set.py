"""The committed 16-item golden set. No Langfuse or model imports."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .paths import kit_root

DATASET_NAME = "returns-agent-golden-set"


def golden_path() -> Path:
    return kit_root() / "data" / "returns-agent-golden-set.json"


def normalize_numbers(value):
    """Whole-number floats become ints.

    Langfuse stores ``40.0`` as ``40``. Hashing and equality both go through
    this so a publish does not mint a new item version for that difference.
    ``29.99`` stays a float. Booleans are not floats.
    """
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {key: normalize_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_numbers(item) for item in value]
    return value


def content_hash(items: list) -> str:
    """SHA-256 of the canonical item list. The hash field itself is not covered."""
    blob = json.dumps(
        normalize_numbers(items),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def load_golden(path: Path | None = None) -> dict:
    document = json.loads((path or golden_path()).read_text(encoding="utf-8"))
    items = document.get("items")
    if not isinstance(items, list) or len(items) != 16:
        raise ValueError("returns golden set must contain 16 items")
    digest = content_hash(items)
    recorded = document.get("content_hash")
    if recorded != digest:
        raise ValueError(
            f"golden content_hash {recorded} does not match the items ({digest})"
        )
    return document
