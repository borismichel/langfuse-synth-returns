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
    """Shipping loads the skill, the next ticket quotes a wrong amount, then a reference read.

    The receipt's first scores are ``decision_correct`` on three different traces.
    This checks the tree, not only the score value.
    """
    if len(examples) < 3:
        return False, "current receipt needs the shipping, amount, and reference traces"
    traces = []
    for example in examples[:3]:
        trace = reader.trace(example["trace_id"], with_scores=False)
        if trace is None:
            return False, f"story trace {example['trace_id']} is not visible"
        traces.append(trace)
    shipping, amount, reference = traces
    if shipping.name != "returns-other":
        return False, "first story trace should be the shipping question"
    decision = _io(shipping.output)
    if not isinstance(decision, dict) or decision.get("decision") != "not_applicable":
        return False, "shipping trace output is not not_applicable"
    agent = next((obs for obs in shipping.observations if obs.name == "returns-desk"), None)
    load = next((obs for obs in shipping.observations if obs.name == "loadSkill"), None)
    if agent is None or load is None or load.parent_id != agent.id:
        return False, "shipping trace should show loadSkill under the returns desk"
    draft = next((obs for obs in amount.observations if obs.name == "draft-customer-reply"), None)
    quoted = _io(draft.output).get("refund_amount") if draft is not None else None
    if quoted is None or abs(float(quoted) - 29.99) < 0.001:
        return False, "second story trace should quote a wrong t-shirt amount"
    if not any(obs.name == "skill_read" for obs in reference.observations):
        return False, "third story trace should open a reference with skill_read"
    return True, "shipping load, wrong amount, and a reference read are visible"
