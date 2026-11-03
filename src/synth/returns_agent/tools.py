"""Skill files and the three desk tools. The calculator runs the fetched script."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml

SKILL_NAME = "returns-and-refunds"


@dataclass
class FetchedSkill:
    name: str
    version: int
    files: dict[str, str]
    label: str | None = None

    @property
    def refs(self) -> list[dict]:
        return [{"name": self.name, "version": int(self.version)}]

    def description(self) -> str:
        meta, _body = split_frontmatter(self.files.get("SKILL.md", ""))
        text = meta.get("description") if isinstance(meta, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise ValueError("SKILL.md is missing a description")
        return text.strip()


def split_frontmatter(text: str) -> tuple[dict, str]:
    body = text.lstrip("\ufeff")
    if not body.startswith("---"):
        return {}, text
    rest = body[3:]
    if rest.startswith("\n"):
        rest = rest[1:]
    end = rest.find("\n---")
    if end < 0:
        return {}, text
    meta = yaml.safe_load(rest[:end]) or {}
    content = rest[end + 4 :]
    if content.startswith("\n"):
        content = content[1:]
    return (meta if isinstance(meta, dict) else {}), content


def load_skill(skill: FetchedSkill, arguments: dict) -> str:
    name = arguments.get("name") or arguments.get("skill") or ""
    if name != skill.name:
        return f"No skill named {name!r} is available. Available: {skill.name}."
    text = skill.files.get("SKILL.md")
    if text is None:
        return "SKILL.md is missing from this skill version."
    return text


def skill_read(skill: FetchedSkill, arguments: dict) -> str:
    path = str(arguments.get("path") or arguments.get("file_path") or "")
    text = skill.files.get(path)
    if text is None:
        return json.dumps(
            {
                "status": "not_in_this_version",
                "path": path,
                "skill": skill.name,
                "version": skill.version,
                "message": f"{path} is not in {skill.name} version {skill.version}.",
            }
        )
    return text


def run_refund_calculator(skill: FetchedSkill, arguments: dict, *, timeout: float = 5) -> dict:
    """Run ``scripts/calc_refund.py`` from the fetched version. No shell."""
    script = skill.files.get("scripts/calc_refund.py")
    if not script:
        return {
            "error": (
                f"{skill.name} version {skill.version} has no scripts/calc_refund.py. "
                "Work the amount out from the policy text."
            ),
            "decision": None,
            "refund_amount": None,
            "policy_rule": None,
        }
    payload = json.dumps(arguments)
    with tempfile.TemporaryDirectory(prefix="kestrel-calc-") as directory:
        path = Path(directory) / "calc_refund.py"
        path.write_text(script, encoding="utf-8")
        try:
            completed = subprocess.run(
                [sys.executable, str(path)],
                input=payload,
                text=True,
                capture_output=True,
                timeout=timeout,
                shell=False,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {
                "error": "calculator timed out",
                "decision": None,
                "refund_amount": None,
                "policy_rule": None,
            }
    if completed.returncode != 0:
        return {
            "error": (completed.stderr or completed.stdout or "calculator failed").strip(),
            "decision": None,
            "refund_amount": None,
            "policy_rule": None,
        }
    try:
        parsed = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {
            "error": "calculator did not return JSON",
            "decision": None,
            "refund_amount": None,
            "policy_rule": None,
        }
    return parsed if isinstance(parsed, dict) else {"result": parsed}


def dispatch(skill: FetchedSkill, name: str, arguments: dict):
    if name == "loadSkill":
        return load_skill(skill, arguments)
    if name == "skill_read":
        return skill_read(skill, arguments)
    if name == "run_refund_calculator":
        return run_refund_calculator(skill, arguments)
    return {"error": f"unknown tool {name}"}


TOOL_SCHEMAS = [
    {
        "name": "loadSkill",
        "description": "Load the SKILL.md body for a skill by name.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "skill_read",
        "description": "Read one file from a fetched skill version.",
        "input_schema": {
            "type": "object",
            "properties": {
                "skillName": {"type": "string"},
                "path": {"type": "string"},
            },
            "required": ["skillName", "path"],
        },
    },
    {
        "name": "run_refund_calculator",
        "description": (
            "Run the skill's refund calculator. Pass order, items, today, and customer_tier."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "order": {"type": "object"},
                "items": {"type": "array"},
                "today": {"type": "string"},
                "customer_tier": {"type": "string"},
                "rule": {"type": "string"},
            },
        },
    },
]


def load_installed(directory: Path, lockfile: Path | None = None) -> FetchedSkill:
    """Read a `langfuse skills install --directory` checkout. Not `.agents/skills`."""
    directory = directory.resolve()
    candidates = []
    if lockfile is not None:
        candidates.append(lockfile)
    candidates.append(directory / "langfuse-skills.lock")
    candidates.append(Path.cwd() / "langfuse-skills.lock")
    lock_path = next((path for path in candidates if path.is_file()), None)
    if lock_path is None:
        raise FileNotFoundError(f"no langfuse-skills.lock under {directory}")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    entry = next(
        (row for row in lock.get("skills") or [] if row.get("name") == SKILL_NAME),
        None,
    )
    if entry is None:
        raise FileNotFoundError(f"{SKILL_NAME} is not in {lock_path}")
    version = entry.get("version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise ValueError("lock entry version must be an int")
    folder = directory / str(entry.get("path") or SKILL_NAME)
    files: dict[str, str] = {}
    for path in sorted(folder.rglob("*")):
        if path.is_file():
            files[path.relative_to(folder).as_posix()] = path.read_text(encoding="utf-8")
    if "SKILL.md" not in files:
        raise FileNotFoundError(f"{folder} has no SKILL.md")
    selector = entry.get("selector") or {}
    label = selector.get("label") if isinstance(selector, dict) else None
    return FetchedSkill(name=SKILL_NAME, version=version, files=files, label=label)


def fetch_skill(client, *, label: str | None = None, version: int | None = None) -> FetchedSkill:
    """Fetch one skill version with file content. Label and version together are rejected."""
    if label is not None and version is not None:
        raise ValueError("pass label or version, not both")
    kwargs: dict = {"include_content": True}
    if version is not None:
        kwargs["version"] = int(version)
    elif label:
        kwargs["label"] = label
    remote = client.api.skills.get(SKILL_NAME, **kwargs)
    files: dict[str, str] = {}
    for record in getattr(remote, "files", None) or []:
        path = getattr(record, "path", None)
        content = getattr(record, "content", None)
        if path:
            files[str(path)] = "" if content is None else str(content)
    if "SKILL.md" not in files:
        raise RuntimeError(f"{SKILL_NAME} came back without SKILL.md content")
    return FetchedSkill(
        name=str(getattr(remote, "name", SKILL_NAME)),
        version=int(remote.version),
        files=files,
        label=label,
    )
