"""Experiments follow a skill label, or whatever version an install dir recorded."""
import json

import pytest

from synth.cli import build_parser
from synth.returns_agent.experiment import default_skill_label, resolve_experiment_skill


class _File:
    def __init__(self, path, content):
        self.path = path
        self.content = content


class _Remote:
    def __init__(self, version):
        self.name = "returns-and-refunds"
        self.version = version
        self.files = [
            _File(
                "SKILL.md",
                "---\nname: returns-and-refunds\n"
                "description: Helps with customer orders\n---\nbody\n",
            )
        ]


class _Skills:
    def __init__(self):
        self.seen = []

    def get(self, _name, version=None, label=None, include_content=False):
        self.seen.append({"version": version, "label": label})
        if label == "production":
            return _Remote(3)
        if label == "candidate":
            return _Remote(4)
        return _Remote(version)


class _Client:
    def __init__(self):
        self.api = type("API", (), {})()
        self.api.skills = _Skills()


def test_run_name_picks_the_default_label():
    assert default_skill_label("returns-v1") == "production"
    assert default_skill_label("returns-v2") == "candidate"
    assert default_skill_label("returns-candidate") == "candidate"
    assert default_skill_label(None) == "production"


def test_a_label_resolves_whatever_version_wears_it():
    client = _Client()
    skill = resolve_experiment_skill(
        client,
        skill_label="production",
        skill_version=1,
        run_name="returns-v1",
        install_dir=None,
        lockfile=None,
    )
    assert skill.version == 3
    assert client.api.skills.seen == [{"version": None, "label": "production"}]


def test_omitted_label_follows_the_run_name():
    client = _Client()
    skill = resolve_experiment_skill(
        client,
        skill_label=None,
        skill_version=None,
        run_name="returns-v2",
        install_dir=None,
        lockfile=None,
    )
    assert skill.version == 4
    assert client.api.skills.seen == [{"version": None, "label": "candidate"}]


def test_an_explicit_version_can_be_any_positive_integer():
    client = _Client()
    skill = resolve_experiment_skill(
        client,
        skill_label=None,
        skill_version=3,
        run_name="returns-v1",
        install_dir=None,
        lockfile=None,
    )
    assert skill.version == 3
    with pytest.raises(ValueError, match="positive integer"):
        resolve_experiment_skill(
            client,
            skill_label=None,
            skill_version=0,
            run_name="returns-v1",
            install_dir=None,
            lockfile=None,
        )


def test_install_dir_accepts_version_3(tmp_path):
    folder = tmp_path / "returns-and-refunds"
    folder.mkdir()
    (folder / "SKILL.md").write_text(
        "---\nname: returns-and-refunds\n"
        "description: Helps with customer orders\n---\nbody\n",
        encoding="utf-8",
    )
    lock = {
        "lockVersion": 1,
        "skills": [{
            "path": "returns-and-refunds",
            "name": "returns-and-refunds",
            "selector": {"label": "production"},
            "version": 3,
        }],
    }
    (tmp_path / "langfuse-skills.lock").write_text(json.dumps(lock), encoding="utf-8")
    skill = resolve_experiment_skill(
        None,
        skill_label="production",
        skill_version=1,
        run_name="returns-v1",
        install_dir=str(tmp_path),
        lockfile=None,
    )
    assert skill.version == 3
    assert skill.label == "production"


def test_parser_accepts_a_label_or_any_version():
    parser = build_parser()
    labelled = parser.parse_args(
        ["experiment", "--skill-label", "candidate", "--run-name", "returns-v2"]
    )
    assert labelled.skill_label == "candidate"
    assert labelled.skill_version is None
    pinned = parser.parse_args(["experiment", "--skill-version", "3"])
    assert pinned.skill_version == 3
    with pytest.raises(SystemExit):
        parser.parse_args(["experiment", "--skill-label", "latest"])
    with pytest.raises(SystemExit):
        parser.parse_args(["experiment", "--skill-version", "0"])
