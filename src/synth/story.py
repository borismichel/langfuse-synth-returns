"""Read-back for the three presenter beats in the seeded history."""
from __future__ import annotations

import json


def _io(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def check_story(reader, examples: list[dict]) -> tuple[bool, str]:
    """Shipping loads the skill, a ticket quotes EUR 28.99, and one opens a reference.

    The receipt's first scores cover the opening turns of the seeded sessions.
    This checks those trees, not only the score value. Later turns in a session
    are follow-ups and are not these three beats.
    """
    if len(examples) < 3:
        return False, "current receipt needs the shipping, amount, and reference traces"
    traces = []
    for example in examples:
        trace = reader.trace(example["trace_id"], with_scores=False)
        if trace is None:
            return False, f"story trace {example['trace_id']} is not visible"
        traces.append(trace)

    def _loaded_shipping(trace) -> bool:
        if trace.name != "returns-other":
            return False
        decision = _io(trace.output)
        if not isinstance(decision, dict) or decision.get("decision") != "not_applicable":
            return False
        agent = next((obs for obs in trace.observations if obs.name == "returns-desk"), None)
        load = next((obs for obs in trace.observations if obs.name == "loadSkill"), None)
        return agent is not None and load is not None and load.parent_id == agent.id

    def _wrong_tee(trace) -> bool:
        draft = next(
            (obs for obs in trace.observations if obs.name == "draft-customer-reply"), None
        )
        if draft is None:
            return False
        body = _io(draft.output)
        quoted = body.get("refund_amount") if isinstance(body, dict) else None
        return quoted is not None and abs(float(quoted) - 28.99) < 0.001

    if not any(_loaded_shipping(trace) for trace in traces):
        return False, "shipping trace should show loadSkill under the returns desk"
    if not any(_wrong_tee(trace) for trace in traces):
        return False, "a story trace should quote the wrong t-shirt amount"
    if not any(any(obs.name == "skill_read" for obs in trace.observations) for trace in traces):
        return False, "a story trace should open a reference with skill_read"
    return True, "shipping load, wrong amount, and a reference read are visible"
