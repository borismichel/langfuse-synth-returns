"""Bytecode never enters a skill hash or a published bundle."""
from pathlib import Path

import pytest

from synth.returns_agent.skills_publish import (
    _local_hashes,
    publish_bundle,
    publish_returns_skills,
)


def _bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "v2"
    (bundle / "scripts" / "__pycache__").mkdir(parents=True)
    (bundle / "SKILL.md").write_text(
        "---\nname: returns-and-refunds\ndescription: Helps with customer orders\n---\nbody\n",
        encoding="utf-8",
    )
    (bundle / "scripts" / "calc_refund.py").write_text("x = 1\n", encoding="utf-8")
    cached = bundle / "scripts" / "__pycache__" / "calc_refund.cpython-312.pyc"
    cached.write_bytes(b"\x00\x01not utf-8 \xff")
    (bundle / "scripts" / "extra.pyc").write_bytes(b"\xff\xfe")
    return bundle


def test_local_hashes_skip_bytecode(tmp_path):
    hashes = _local_hashes(_bundle(tmp_path))
    assert set(hashes) == {"SKILL.md", "scripts/calc_refund.py"}


def test_publish_hands_core_a_tree_without_bytecode(tmp_path, monkeypatch):
    seen: dict = {}

    def fake_publish(_client, directory, labels):
        root = Path(directory)
        seen["labels"] = list(labels)
        seen["files"] = sorted(
            path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
        )
        return {"name": "returns-and-refunds", "version": 2}

    monkeypatch.setattr("langfuse_synth_core.skills.publish_skill_bundle", fake_publish)

    class _Missing(Exception):
        status_code = 404

    class _Skills:
        def get(self, _name, version=None):
            raise _Missing("missing")

    class _Client:
        class api:
            skills = _Skills()

    result = publish_bundle(_Client(), _bundle(tmp_path), ["candidate"])
    assert result == {"name": "returns-and-refunds", "version": 2, "created": True}
    assert seen["labels"] == ["candidate"]
    assert seen["files"] == ["SKILL.md", "scripts/calc_refund.py"]


def test_existing_versions_ask_for_a_fresh_project(monkeypatch):
    def fake_publish(_client, bundle, labels):
        version = 3 if "v1" in bundle.parts else 4
        return {"name": "returns-and-refunds", "version": version, "created": True}

    monkeypatch.setattr(
        "synth.returns_agent.skills_publish.publish_bundle",
        fake_publish,
    )
    with pytest.raises(RuntimeError, match="fresh project") as raised:
        publish_returns_skills(object(), root=Path("."))
    message = str(raised.value)
    assert "got 3 and 4" in message
    assert "cannot replace" in message
    assert "no migration path" in message
