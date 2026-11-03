"""The committed 16-item golden set. No Langfuse or model imports."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .paths import kit_root

DATASET_NAME = "returns-agent-golden-set"


def golden_path() -> Path:
    return kit_root() / "data" / "returns-agent-golden-set.json"


def content_hash(items: list) -> str:
    """SHA-256 of the canonical item list. The hash field itself is not covered."""
    blob = json.dumps(items, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
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
