"""Publish the golden set. Existing items with the same content are left alone."""
from __future__ import annotations

import json
from datetime import timezone

from ..golden_set import DATASET_NAME, content_hash, load_golden


def _canon(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _same(remote, row: dict) -> bool:
    return (
        _canon(getattr(remote, "input", None)) == _canon(row["input"])
        and _canon(getattr(remote, "expected_output", None)) == _canon(row["expected"])
        and _canon(getattr(remote, "metadata", None)) == _canon(row["metadata"])
    )


def _missing(exc: Exception) -> bool:
    return getattr(exc, "status_code", None) == 404


def publish_golden_dataset(client) -> dict:
    document = load_golden()
    name = document.get("name") or DATASET_NAME
    try:
        existing = client.get_dataset(name)
    except Exception as exc:
        if not _missing(exc):
            raise
        existing = None
    if existing is None:
        client.create_dataset(name=name, description=document.get("description"))
        remote_items = []
    else:
        remote_items = list(existing.items)
    by_id = {item.id: item for item in remote_items}
    written = 0
    for row in document["items"]:
        current = by_id.get(row["id"])
        if current is not None and _same(current, row):
            continue
        client.create_dataset_item(
            dataset_name=name,
            id=row["id"],
            input=row["input"],
            expected_output=row["expected"],
            metadata=row["metadata"],
        )
        written += 1
    refreshed = client.get_dataset(name)
    if len(list(refreshed.items)) != 16:
        raise RuntimeError(f"{name} does not have 16 items after publish")
    pin = max(item.version for item in refreshed.items)
    if getattr(pin, "tzinfo", None) is None:
        pin = pin.replace(tzinfo=timezone.utc)
    pinned = client.get_dataset(name, version=pin)
    remote_rows = [
        {
            "id": item.id,
            "input": item.input,
            "expected": item.expected_output,
            "metadata": item.metadata,
        }
        for item in pinned.items
    ]
    remote_rows.sort(key=lambda row: row["id"])
    committed = sorted(document["items"], key=lambda row: row["id"])
    digest = content_hash(committed)
    if content_hash(remote_rows) != digest:
        raise RuntimeError(
            f"published {name} does not match the committed content hash {digest}. "
            "The dataset was not pinned."
        )
    return {
        "name": name,
        "written": written,
        "content_hash": digest,
        "dataset_version": pin.isoformat(),
    }
