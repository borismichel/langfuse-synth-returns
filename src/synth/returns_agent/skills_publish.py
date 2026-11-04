"""Publish v1 (production) then v2 (candidate) without minting a duplicate version.

``publish_skill_bundle`` only compares the latest version. A second publish of v1
after v2 exists would create version 3 and move the production label. This wrapper
matches file hashes on any existing version first.
"""
from __future__ import annotations

import base64
import hashlib
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

from ..paths import kit_root

SKILL_NAME = "returns-and-refunds"
V1 = ("skill_bundles", "returns-and-refunds", "v1")
V2 = ("skill_bundles", "returns-and-refunds", "v2")


def _content_hash(content: str) -> str:
    digest = hashlib.sha256(content.encode("utf-8")).digest()
    return base64.b64encode(digest).decode("ascii")


def _skipped_bundle_file(rel: Path) -> bool:
    """Bytecode is not skill content. Hashing it raises UnicodeDecodeError."""
    return "__pycache__" in rel.parts or rel.suffix == ".pyc"


def _bundle_files(bundle: Path):
    for path in sorted(bundle.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(bundle)
        if _skipped_bundle_file(rel):
            continue
        yield path, rel.as_posix()


def _local_hashes(bundle: Path) -> dict[str, str]:
    return {
        rel: _content_hash(path.read_text(encoding="utf-8"))
        for path, rel in _bundle_files(bundle)
    }


@contextmanager
def _publish_tree(bundle: Path):
    """Copy the bundle without bytecode so the core publisher cannot upload it.

    Core walks every file under the directory and would otherwise read ``.pyc``
    as skill text.
    """
    with tempfile.TemporaryDirectory() as tmp:
        staged = Path(tmp) / bundle.name
        for path, rel in _bundle_files(bundle):
            target = staged / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        yield staged


def _remote_hashes(version) -> dict[str, str]:
    found: dict[str, str] = {}
    for record in getattr(version, "files", None) or []:
        digest = getattr(record, "sha256hash", None)
        if digest is None:
            digest = getattr(record, "sha256Hash", None)
        found[str(getattr(record, "path", ""))] = "" if digest is None else str(digest)
    return found


def _missing(exc: Exception) -> bool:
    return getattr(exc, "status_code", None) == 404


def _managed(version) -> set[str]:
    return {str(label) for label in (getattr(version, "labels", None) or []) if label != "latest"}


def publish_bundle(client, bundle: Path, labels: list[str]) -> dict:
    from langfuse_synth_core.skills import publish_skill_bundle

    local = _local_hashes(bundle)
    skills = client.api.skills
    match = None
    for number in range(1, 21):
        try:
            remote = skills.get(SKILL_NAME, version=number)
        except Exception as exc:
            if _missing(exc):
                break
            raise
        if _remote_hashes(remote) == local:
            match = remote
            break
    if match is not None:
        if _managed(match) != set(labels):
            match = skills.set_labels(SKILL_NAME, int(match.version), labels=list(labels))
        return {"name": SKILL_NAME, "version": int(match.version), "created": False}
    with _publish_tree(bundle) as staged:
        created = publish_skill_bundle(client, staged, labels)
    return {"name": created["name"], "version": int(created["version"]), "created": True}


def _labeled_version(client, label: str):
    return client.api.skills.get(SKILL_NAME, label=label)


def publish_returns_skills(client, *, root: Path | None = None) -> dict:
    """Label local v1 ``production`` and local v2 ``candidate``.

    A fresh project gets version 1 and version 2. A project that already has
    the skill may wear those labels on later versions. Any version number is
    accepted when its files match the local bundle. A labelled body that does
    not match is a genuine mismatch: there is no migration path.
    """
    root = root or kit_root()
    v1_dir = root.joinpath(*V1)
    v2_dir = root.joinpath(*V2)
    published_prod = publish_bundle(client, v1_dir, ["production"])
    published_cand = publish_bundle(client, v2_dir, ["candidate"])
    production = _labeled_version(client, "production")
    candidate = _labeled_version(client, "candidate")
    prod_version = int(production.version)
    cand_version = int(candidate.version)
    prod_ok = _remote_hashes(production) == _local_hashes(v1_dir)
    cand_ok = _remote_hashes(candidate) == _local_hashes(v2_dir)
    if prod_version == cand_version or not prod_ok or not cand_ok:
        raise RuntimeError(
            "production version "
            f"{prod_version} does not match the local v1 bundle, or candidate version "
            f"{cand_version} does not match the local v2 bundle. "
            "A labelled version is accepted at any number when its files match. "
            "These files differ, and there is no migration path. Use a fresh project."
        )
    return {
        "production": {
            "name": SKILL_NAME,
            "version": prod_version,
            "created": bool(published_prod.get("created")) and prod_version == int(
                published_prod["version"]
            ),
        },
        "candidate": {
            "name": SKILL_NAME,
            "version": cand_version,
            "created": bool(published_cand.get("created")) and cand_version == int(
                published_cand["version"]
            ),
        },
    }


def langfuse_client(base_url: str):
    import os

    from langfuse import Langfuse
    from langfuse_synth_core.ingestion import INGESTION_VERSION, INGESTION_VERSION_HEADER

    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
    if not public_key or not secret_key:
        raise RuntimeError("LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are required")
    return Langfuse(
        host=base_url,
        public_key=public_key,
        secret_key=secret_key,
        additional_headers={INGESTION_VERSION_HEADER: INGESTION_VERSION},
    )
