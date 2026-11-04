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


class _Record:
    def __init__(self, path, digest):
        self.path = path
        self.sha256hash = digest


class _Remote:
    def __init__(self, version, hashes):
        self.version = version
        self.files = [_Record(path, digest) for path, digest in hashes.items()]


class _Skills:
    def __init__(self, by_label):
        self.by_label = by_label

    def get(self, _name, version=None, label=None):
        assert label in self.by_label
        return self.by_label[label]


class _Client:
    def __init__(self, by_label):
        self.api = type("API", (), {})()
        self.api.skills = _Skills(by_label)


def _kit(tmp_path: Path) -> Path:
    from synth.returns_agent.skills_publish import V1, V2

    v1 = tmp_path.joinpath(*V1)
    v2 = tmp_path.joinpath(*V2)
    v1.mkdir(parents=True)
    v2.mkdir(parents=True)
    (v1 / "SKILL.md").write_text("v1 body\n", encoding="utf-8")
    (v2 / "SKILL.md").write_text("v2 body\n", encoding="utf-8")
    return tmp_path


def _publish_as(monkeypatch, versions):
    def fake_publish(_client, bundle, labels):
        version = versions[labels[0]]
        return {"name": "returns-and-refunds", "version": version, "created": True}

    monkeypatch.setattr("synth.returns_agent.skills_publish.publish_bundle", fake_publish)


def test_any_version_is_accepted_when_the_files_match(tmp_path, monkeypatch):
    from synth.returns_agent.skills_publish import V1, V2

    root = _kit(tmp_path)
    _publish_as(monkeypatch, {"production": 3, "candidate": 4})
    client = _Client({
        "production": _Remote(3, _local_hashes(root.joinpath(*V1))),
        "candidate": _Remote(4, _local_hashes(root.joinpath(*V2))),
    })
    published = publish_returns_skills(client, root=root)
    assert published["production"]["version"] == 3
    assert published["candidate"]["version"] == 4
    assert published["production"]["created"] is True


def test_mismatched_files_still_ask_for_a_fresh_project(tmp_path, monkeypatch):
    from synth.returns_agent.skills_publish import V2

    root = _kit(tmp_path)
    _publish_as(monkeypatch, {"production": 3, "candidate": 4})
    client = _Client({
        "production": _Remote(3, {"SKILL.md": "different"}),
        "candidate": _Remote(4, _local_hashes(root.joinpath(*V2))),
    })
    with pytest.raises(RuntimeError, match="fresh project") as raised:
        publish_returns_skills(client, root=root)
    message = str(raised.value)
    assert "version 3" in message
    assert "version 4" in message
    assert "no migration path" in message
    assert "any number" in message
