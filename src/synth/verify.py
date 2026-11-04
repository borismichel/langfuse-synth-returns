"""`synth verify` — read the seeded beats back and confirm both skill labels exist."""
from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass, field

import requests
from langfuse_synth_core.read import ReadError, parse_ts
from langfuse_synth_core.target import TargetProfile
from langfuse_synth_core.timegen import iso

from .config import Config
from .receipt import SAMPLE_LIMIT, RunReceipt
from .story import check_story

SKILL_NAME = "returns-and-refunds"


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


@dataclass
class VerifyReport:
    checks: list[Check] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str) -> None:
        self.checks.append(Check(name, ok, detail))

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)


def _version_of(payload: dict) -> int | None:
    raw = payload.get("version", payload.get("skillVersion"))
    if raw is None and isinstance(payload.get("skill"), dict):
        raw = payload["skill"].get("version")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _check_skill_labels(base_url: str) -> tuple[bool, str]:
    from langfuse_synth_core.lfread import get_json

    path = f"/api/public/skills/{SKILL_NAME}"
    production = get_json(base_url, path, {"label": "production"}, attempts=1)
    candidate = get_json(base_url, path, {"label": "candidate"}, attempts=1)
    prod_version = _version_of(production)
    cand_version = _version_of(candidate)
    if prod_version is None or cand_version is None:
        return False, "production and candidate labels did not return a version"
    if prod_version == cand_version:
        return False, f"production and candidate are both version {prod_version}"
    return True, (
        f"production is version {prod_version} and candidate is version {cand_version}"
    )


def _read_examples(reader, examples: list[dict], base_url: str) -> VerifyReport:
    report = VerifyReport()
    for example in examples:
        trace_id, score_id = example["trace_id"], example["score_id"]
        trace = reader.trace(trace_id, with_scores=False)
        trace_ok = (
            trace is not None
            and trace.id == trace_id
            and trace.timestamp is not None
            and iso(trace.timestamp) == example["trace_timestamp"]
        )
        report.add(
            f"trace:{trace_id}",
            trace_ok,
            "expected trace and run timestamp visible"
            if trace_ok
            else f"missing trace {trace_id} or mismatched run timestamp",
        )
        scores = reader.scores(trace_id=trace_id, name=example["name"], limit_pages=1)
        score = next((item for item in scores if item.id == score_id), None)
        score_ok = (
            score is not None
            and score.trace_id == trace_id
            and score.name == example["name"]
            and score.value == example["value"]
            and score.data_type == example["data_type"]
        )
        report.add(
            f"score:{score_id}",
            score_ok,
            "expected score, value and trace relationship visible"
            if score_ok
            else f"missing or mismatched score {score_id} on trace {trace_id}",
        )
    report.add("returns_story", *check_story(reader, examples))
    try:
        report.add("skill_labels", *_check_skill_labels(base_url))
    except (OSError, ValueError, requests.RequestException) as exc:
        report.add("skill_labels", False, f"cannot read skill labels: {exc}")
    return report


def run_verify(
    cfg: Config,
    *,
    timeout_seconds: float = 60,
    poll_interval: float = 2,
    clock=time.monotonic,
    sleep=time.sleep,
    log=print,
) -> VerifyReport:
    """Read the last successful seed, polling visibility for at most 60 seconds."""
    if (
        not math.isfinite(timeout_seconds)
        or timeout_seconds < 0
        or not math.isfinite(poll_interval)
        or poll_interval <= 0
    ):
        raise ValueError("timeout_seconds must be finite and nonnegative; poll_interval positive")
    report = VerifyReport()
    try:
        receipt = RunReceipt.load()
        if not isinstance(receipt.examples, list) or not 1 <= len(receipt.examples) <= SAMPLE_LIMIT:
            raise ValueError("receipt needs 1–5 representative score/trace pairs")
        for example in receipt.examples:
            if not isinstance(example, dict) or "value" not in example:
                raise ValueError("receipt example needs a score value")
            for key in ("trace_id", "score_id", "name", "data_type", "trace_timestamp"):
                if not isinstance(example.get(key), str) or not example[key]:
                    raise ValueError(f"receipt example needs a nonempty {key}")
            parse_ts(example["trace_timestamp"])
        if (
            receipt.base_url != cfg.target.base_url
            or receipt.public_key != os.environ.get("LANGFUSE_PUBLIC_KEY", "")
            or receipt.seed != cfg.generation.seed
            or receipt.target_traces != cfg.generation.target_traces
            or receipt.as_of_date != str(cfg.generation.as_of_date or "")
        ):
            raise ValueError("receipt target or generation configuration differs from invocation")
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        report.add("run_receipt", False, f"Missing or invalid receipt; run synth seed: {exc}")
    else:
        profile = TargetProfile.detect(cfg.target.base_url)
        reader = profile.reader(attempts=1)
        log(f"· verifying against {profile.label} ({profile.base_url})")
        deadline = clock() + timeout_seconds
        while True:
            try:
                report = _read_examples(reader, receipt.examples, cfg.target.base_url)
            except (ReadError, requests.RequestException) as exc:
                report = VerifyReport()
                report.add("target_read", False, f"Cannot read expected records: {exc}")
            if report.ok:
                break
            remaining = deadline - clock()
            if remaining <= 0:
                for check in report.checks:
                    if not check.ok:
                        check.detail += f" (visibility timeout after {timeout_seconds:g}s)"
                break
            sleep(min(poll_interval, remaining))
    for check in report.checks:
        log(f"{'✓' if check.ok else '✗'} {check.name}: {check.detail}")
    return report
