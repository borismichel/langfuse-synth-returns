"""Run the golden set against a skill label and print scores, tokens, and cost."""
from __future__ import annotations

from datetime import datetime, timezone

from ..config import Config
from ..golden_set import DATASET_NAME, content_hash, load_golden
from .agent import resolved_model, run_ticket
from .dataset_publish import publish_golden_dataset
from .evaluators import evaluators
from .skills_publish import langfuse_client
from .tools import fetch_skill, load_installed


def _pinned_dataset(client):
    """Refetch at the latest item version and refuse a dataset that drifted."""
    document = load_golden()
    publish_golden_dataset(client)
    dataset = client.get_dataset(DATASET_NAME)
    pin = max(item.version for item in dataset.items)
    if getattr(pin, "tzinfo", None) is None:
        pin = pin.replace(tzinfo=timezone.utc)
    pinned = client.get_dataset(DATASET_NAME, version=pin)
    rows = sorted(
        (
            {
                "id": item.id,
                "input": item.input,
                "expected": item.expected_output,
                "metadata": item.metadata,
            }
            for item in pinned.items
        ),
        key=lambda row: row["id"],
    )
    digest = content_hash(sorted(document["items"], key=lambda row: row["id"]))
    if content_hash(rows) != digest:
        raise RuntimeError(
            f"dataset {DATASET_NAME} at {pin.isoformat()} does not match committed hash {digest}"
        )
    return pinned, pin, digest


def default_skill_label(run_name: str | None) -> str:
    """Candidate when the run name says so. Every other run is production."""
    name = (run_name or "").lower().replace("_", "-")
    tokens = set(name.split("-"))
    if "candidate" in name or "v2" in tokens:
        return "candidate"
    return "production"


def resolve_experiment_skill(
    client,
    *,
    skill_label: str | None,
    skill_version: int | None,
    run_name: str | None,
    install_dir: str | None,
    lockfile: str | None,
):
    """The installed checkout, or the version wearing ``skill_label``.

    An install directory is accepted at whatever version the lock records.
    A label is accepted at whatever version currently wears it. ``--skill-version``
    pins a number only when no label was passed.
    """
    from pathlib import Path

    if install_dir:
        return load_installed(
            Path(install_dir),
            Path(lockfile) if lockfile else None,
        )
    if skill_label is None and skill_version is None:
        skill_label = default_skill_label(run_name)
    if skill_label is not None:
        if skill_label not in {"production", "candidate"}:
            raise ValueError("skill label must be production or candidate")
        return fetch_skill(client, label=skill_label)
    if isinstance(skill_version, bool) or not isinstance(skill_version, int) or skill_version < 1:
        raise ValueError("skill version must be a positive integer")
    return fetch_skill(client, version=skill_version)


def run_skill_experiment(
    cfg: Config,
    skill_version: int | None = None,
    *,
    skill_label: str | None = None,
    run_name: str | None = None,
    install_dir: str | None = None,
    lockfile: str | None = None,
) -> dict:
    from langfuse_synth_core.live.emit import LiveEmitter

    from .agent import anthropic_client_from_env

    client = langfuse_client(cfg.target.base_url)
    skill = resolve_experiment_skill(
        client,
        skill_label=skill_label,
        skill_version=skill_version,
        run_name=run_name,
        install_dir=install_dir,
        lockfile=lockfile,
    )
    dataset, pin, digest = _pinned_dataset(client)
    model = resolved_model()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = run_name or f"returns-v{skill.version}-{model}-{stamp}"
    anthropic = anthropic_client_from_env()
    judge_and_item = evaluators(anthropic, model)

    def task(*, item, **_kwargs):
        ticket = item.input if not isinstance(item, dict) else item["input"]
        item_id = getattr(item, "id", None) or "item"
        emitter = LiveEmitter(
            cfg.target.base_url,
            client=client,
            flush_on_exit=False,
        )
        return run_ticket(
            skill,
            ticket,
            emitter=emitter,
            anthropic_client=anthropic,
            model=model,
            user_id=f"kc-{item_id}",
            session_id=f"{name}-{item_id}",
            metadata={
                "item_id": str(item_id),
                "label": skill.label or "",
                "model": model,
                "source": "experiment",
            },
        )

    result = client.run_experiment(
        name="returns-desk",
        run_name=name,
        data=dataset.items,
        task=task,
        evaluators=judge_and_item,
        max_concurrency=2,
        metadata={
            "skill": skill.name,
            "skill_version": str(skill.version),
            "model": model,
            "dataset": DATASET_NAME,
            "dataset_content_hash": digest,
            "dataset_version": pin.isoformat(),
        },
    )
    client.flush()
    print(result.format(include_item_results=True))
    input_tokens = 0
    output_tokens = 0
    cost = 0.0
    for item_result in result.item_results:
        produced = item_result.output or {}
        usage = produced.get("usage") or {}
        input_tokens += int(usage.get("input") or 0)
        output_tokens += int(usage.get("output") or 0)
        cost += float(usage.get("cost") or 0)
        item_id = getattr(item_result.item, "id", None) or "?"
        scores = ", ".join(
            f"{evaluation.name}={evaluation.value}" for evaluation in item_result.evaluations
        )
        print(
            f"{item_id} decision={produced.get('decision')} "
            f"amount={produced.get('refund_amount')} tokens="
            f"{usage.get('input', 0)}+{usage.get('output', 0)} {scores}"
        )
    print(
        f"total input_tokens={input_tokens} output_tokens={output_tokens} "
        f"cost_usd={cost:.6f} run={name} skill_version={skill.version} model={model}"
    )
    return {
        "run_name": name,
        "skill_version": skill.version,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost": cost,
        "dataset_version": pin.isoformat(),
        "dataset_content_hash": digest,
    }
