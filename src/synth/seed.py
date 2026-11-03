"""`synth seed` — materialize the Spool, then ingest it through the library.

Generation is model-free. The Spool is OTLP spans plus `score-create` envelopes.
OTLP appends, so a re-seed into a project that already holds the demo duplicates
observations. Import a cleared project.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from langfuse_synth_core.seed.ingest import Ingestor, assert_demo_project
from langfuse_synth_core.timegen import resolve_run_date

from .config import Config
from .golden_set import DATASET_NAME, load_golden
from .materialize import MODEL, SKILL_NAME, build_events, representative_trace_id
from .receipt import SAMPLE_LIMIT, RunReceipt

DEFAULT_SPOOL = Path(".synth_spool") / "events.ndjson"


def _write_report(artifact_dir: Path, cfg: Config, run_date, log) -> None:
    golden = load_golden()
    report = {
        "kit": "returns",
        "skill": SKILL_NAME,
        "history_skill_version": 1,
        "model": MODEL,
        "target_traces": cfg.generation.target_traces,
        "seed": cfg.generation.seed,
        "run_date": run_date.isoformat(),
        "dataset": DATASET_NAME,
        "dataset_content_hash": golden["content_hash"],
        "dataset_version": golden.get("dataset_version"),
        "representative_trace_id": representative_trace_id(cfg.generation.seed),
        "note": (
            "History is returns-and-refunds version 1 in production only. "
            "Version 2 is the candidate label and is not in the seeded traces."
        ),
    }
    path = artifact_dir / "generation-report.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    log(f"· generation report -> {path}")


def run_seed(
    cfg: Config,
    *,
    dry_run: bool = False,
    do_import: bool = True,
    spool_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    runbook_source: str | Path = "DEMO_SCRIPT.md",
    log=print,
) -> Path:
    """Deliver the runbook, generate the Spool, and ingest unless `dry_run`."""
    Path(RunReceipt.state_path()).unlink(missing_ok=True)
    source = Path(runbook_source)
    artifact_dir = Path(output_dir) if output_dir is not None else Path(
        os.environ.get("SYNTH_OUT_DIR", "/app/out")
    )
    runbook = artifact_dir / "DEMO_SCRIPT.md"
    try:
        content = source.read_bytes()
    except OSError as exc:
        raise RuntimeError(
            f"Cannot read Presenter Runbook source {source.resolve()}: {exc}. "
            "Restore DEMO_SCRIPT.md and run seed from the kit root."
        ) from exc
    try:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        runbook.write_bytes(content)
    except OSError as exc:
        raise RuntimeError(
            f"Cannot write Presenter Runbook {runbook}: {exc}. "
            "Set SYNTH_OUT_DIR to a directory writable by the runtime user "
            "(/app/out in the depot container)."
        ) from exc
    log(f"· Presenter Runbook -> {runbook}")
    run_date = resolve_run_date(cfg.generation.as_of_date)
    log(
        f"· run anchor {run_date.isoformat()}"
        + (" (as-of date)" if cfg.generation.as_of_date else " (now)")
    )
    _write_report(artifact_dir, cfg, run_date, log)
    events = build_events(
        cfg.generation.target_traces, {"seed": cfg.generation.seed}, run_date=run_date
    )
    spool_path = Path(spool_path) if spool_path else DEFAULT_SPOOL

    if not dry_run:
        _project_id, project_name = assert_demo_project(
            cfg.target.base_url, cfg.target.project_hint
        )
        log(
            f"✓ guardrail passed: project {project_name!r} "
            f"matches hint {cfg.target.project_hint!r}"
        )

    ingestor = Ingestor.from_env(cfg.target.base_url, dry_run=dry_run, spool_path=spool_path)
    ingestor.open_spool()
    ingestor.extend(events)
    ingestor.close_spool()
    log(f"· spooled {ingestor.spooled} events -> {spool_path}")

    if do_import and not dry_run:
        sent = ingestor.import_spool(path=spool_path, log=log)
        log(f"✓ imported {sent} events")
        examples = []
        for event in events:
            if event.get("type") == "score-create" and event["body"].get("traceId"):
                body = event["body"]
                examples.append({
                    "trace_id": body["traceId"],
                    "score_id": body["id"],
                    "name": body["name"],
                    "value": body["value"],
                    "data_type": body["dataType"],
                    "trace_timestamp": event["timestamp"],
                })
                if len(examples) == SAMPLE_LIMIT:
                    break
        receipt = RunReceipt(
            base_url=cfg.target.base_url,
            public_key=os.environ.get("LANGFUSE_PUBLIC_KEY", ""),
            seed=cfg.generation.seed,
            target_traces=cfg.generation.target_traces,
            as_of_date=str(cfg.generation.as_of_date or ""),
            examples=examples,
        )
        receipt.save()
        log(f"· verification receipt -> {RunReceipt.state_path()}")
    return spool_path
