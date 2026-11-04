"""Four weeks of prewritten v1 returns-desk history. Model-free.

Traces are turns in a session: one to four messages, one shared session id and
user id, a few seconds to minutes apart. The shape of the decision turn cycles
through 16 archetypes. v1 never calls ``run_refund_calculator`` (that tool is
v2). Timestamps depend on the session, the turn, and ``run_date`` only, so the
first N traces stay byte-stable when volume grows.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from langfuse_synth_core.rng import Rng
from langfuse_synth_core.seed.events import (
    generation_event,
    observation_event,
    score_event,
    trace_event,
)
from langfuse_synth_core.seed.otlp import string_attr, trace_root_span_id

from .config import DERIVATION_HOOK
from .paths import kit_root
from .pricing import usage_and_cost

SKILL_NAME = "returns-and-refunds"
SKILL_REFS = [{"name": SKILL_NAME, "version": 1}]
MODEL = "claude-sonnet-5-5"
NON_REFUND_SLOTS = frozenset({0, 5, 8, 9, 12})
LOADED_NON_REFUND_SLOTS = frozenset({0, 8, 12})
# Turns per session, then it repeats. The first five traces are: shipping
# decision, shipping follow-up, t-shirt decision, t-shirt follow-up, sale
# decision. Those three decision turns are the presenter beats inside a
# five-score receipt.
TURN_CYCLE = (2, 2, 3, 1, 4, 2, 3, 1)
# Seconds after the session's first message. A clarification, then a follow-up.
TURN_GAP_SECONDS = (0, 45, 180, 540)
_OBS_META = "langfuse.observation.metadata."


def representative_trace_id(seed: int) -> str:
    """Trace id of archetype 0, the shipping question that loads the skill."""
    return Rng(seed).sub("returns", 0).trace_id("ticket")


def _history_path() -> Path:
    return Path(__file__).resolve().parent / "history_assets" / "tickets.json"


@lru_cache(maxsize=1)
def _tickets() -> tuple[dict, ...]:
    document = json.loads(_history_path().read_text(encoding="utf-8"))
    tickets = document["tickets"]
    if len(tickets) != 16:
        raise ValueError("history needs 16 archetypes")
    for index, ticket in enumerate(tickets):
        non_refund = index in NON_REFUND_SLOTS
        if non_refund != (ticket["case_type"] == "non_refund"):
            raise ValueError(f"archetype {index} breaks the non-refund cycle")
        loaded = bool(ticket["loaded"])
        if non_refund and loaded != (index in LOADED_NON_REFUND_SLOTS):
            raise ValueError(f"archetype {index} breaks the 60% load rate")
    return tuple(tickets)


@lru_cache(maxsize=1)
def _skill_excerpt() -> str:
    path = kit_root() / "skill_bundles" / "returns-and-refunds" / "v1" / "SKILL.md"
    text = path.read_text(encoding="utf-8")
    body = text.split("---", 2)[-1].strip()
    return body[:420].rstrip() + "\n… [SKILL.md continues; v1 is one file]"


def _fill(text: str, order_id: str) -> str:
    return text.replace("{order}", order_id)


def _amounts_match(quoted, expected) -> bool:
    if quoted is None and expected is None:
        return True
    if quoted is None or expected is None:
        return False
    return abs(float(quoted) - float(expected)) < 0.01


def _skill_load_ok(ticket: dict) -> bool:
    ok = bool(ticket["loaded"]) == bool(ticket["should_load_skill"])
    needed = ticket.get("needs_reference")
    if needed:
        ok = ok and needed in (ticket.get("reads") or [])
    return ok


def _tokens(index: int, loaded: bool, kind: str) -> tuple[int, int]:
    if not loaded:
        return 680 + (index % 5) * 24, 88 + (index % 4) * 5
    if kind == "nested":
        return 3880 + (index % 4) * 20, 42
    if kind == "math":
        return 4020 + (index % 5) * 30, 55
    return 4180 + (index % 9) * 60, 128 + (index % 6) * 7


def _ms(base: int, index: int) -> int:
    return base + (index % 5) * 17


def _step(
    key, name, obs_type, base_ms, data_in, data_out, *, skills=False, usage=None, parent="agent"
):
    return {
        "key": key,
        "name": name,
        "type": obs_type,
        "ms": base_ms,
        "input": data_in,
        "output": data_out,
        "skills": skills,
        "usage": usage,
        "parent": parent,
    }


def _load_step(index: int, excerpt: str):
    return _step(
        "load",
        "loadSkill",
        "tool",
        _ms(64, index),
        {"name": SKILL_NAME},
        excerpt,
        skills=True,
    )


def _read_step(index: int, path: str, excerpt: str):
    if path == "SKILL.md":
        output: Any = excerpt
    else:
        output = {
            "status": "not_in_this_version",
            "path": path,
            "skill": SKILL_NAME,
            "version": 1,
            "message": (
                f"{path} is not in returns-and-refunds version 1. "
                "The policy is pasted into SKILL.md."
            ),
        }
    return _step(
        "read",
        "skill_read",
        "tool",
        _ms(88, index),
        {"skillName": SKILL_NAME, "path": path},
        output,
        skills=True,
    )


def _price_step(index: int, amount):
    return _step(
        "price",
        "read-price-from-order",
        "span",
        _ms(55, index),
        {"source": "order line"},
        {
            "refund_amount": amount,
            "method": "shelf price minus the EUR 1.00 returns label",
        },
    )


def _draft(index: int, loaded: bool, decision_out: dict, kind: str = "draft"):
    return _step(
        "draft",
        "draft-customer-reply",
        "generation",
        _ms(980 if loaded else 720, index),
        {"task": "write the customer reply", "decision": decision_out["decision"]},
        decision_out,
        skills=True,
        usage=_tokens(index, loaded, kind),
    )


def _steps(ticket: dict, index: int, message: str, decision_out: dict, excerpt: str):
    loaded = bool(ticket["loaded"])
    shape = ticket["shape"]
    classify_out = {
        "case_type": ticket["case_type"],
        "route": "returns" if loaded or ticket["case_type"] == "refund" else "general",
    }
    steps = [
        _step(
            "classify",
            "classify-intent",
            "span",
            _ms(190, index),
            {"message": message},
            classify_out,
        )
    ]
    if shape == "misroute":
        steps = [
            _step(
                "context",
                "assemble-context",
                "chain",
                _ms(160, index),
                {"message": message},
                {"carrier": "in transit", "opened_returns_note": True},
            ),
            _step(
                "classify",
                "classify-intent",
                "span",
                _ms(140, index),
                {"message": message},
                {"case_type": "non_refund", "route": "returns"},
            ),
            _step(
                "route",
                "route-returns",
                "span",
                _ms(80, index),
                {"route": "returns"},
                {"chosen": SKILL_NAME, "reason": "customer order"},
            ),
            _load_step(index, excerpt),
            _draft(index, True, decision_out),
        ]
    elif shape == "no_skill":
        steps.append(
            _step(
                "route",
                "route-general",
                "span",
                _ms(70, index),
                {"route": "general"},
                {"chosen": "general-desk"},
            )
        )
        steps.append(_draft(index, False, decision_out))
    elif shape == "wrong_amount":
        steps.append(_load_step(index, excerpt))
        steps.append(
            _step(
                "math",
                "estimate-refund",
                "generation",
                _ms(860, index),
                {
                    "price_seen": ticket["expected_amount"],
                    "method": "shelf price minus the EUR 1.00 returns label",
                },
                {"refund_amount": ticket["refund_amount"], "method": "worked out in the reply"},
                skills=True,
                usage=_tokens(index, True, "math"),
            )
        )
        steps.append(_draft(index, True, decision_out))
    elif shape == "reference":
        steps.append(_load_step(index, excerpt))
        steps.append(_read_step(index, ticket["reads"][0], excerpt))
        steps.append(_draft(index, True, decision_out))
    elif shape == "calc":
        # v1 has no calculator. The desk subtracts the returns label itself.
        # The book reply states that figure; the shoes turn records the same
        # subtraction on a span. Both stay consistent with the scores.
        steps.append(_load_step(index, excerpt))
        if ticket["key"] != "book-with-calc":
            steps.append(_price_step(index, ticket["refund_amount"]))
        steps.append(_draft(index, True, decision_out))
    elif shape == "damaged":
        steps.append(_load_step(index, excerpt))
        steps.append(_read_step(index, ticket["reads"][0], excerpt))
        steps.append(
            _step(
                "photo",
                "photo-check",
                "guardrail",
                _ms(40, index),
                {"photo": True},
                {
                    "photo": True,
                    "within_7_days": True,
                    "action": "approve",
                    "refund_amount": ticket["refund_amount"],
                    "policy_rule": ticket["policy_rule"],
                },
            )
        )
        steps.append(_draft(index, True, decision_out))
    elif shape == "gold":
        steps.append(_load_step(index, excerpt))
        steps.append(_read_step(index, "SKILL.md", excerpt))
        steps.append(
            _step(
                "window",
                "apply-window",
                "generation",
                _ms(740, index),
                {"tier": "gold", "days": 51},
                {"window_days": 30, "decision": "deny"},
                skills=True,
                usage=_tokens(index, True, "math"),
            )
        )
        steps.append(_draft(index, True, decision_out))
    elif shape == "digital":
        steps.append(_load_step(index, excerpt))
        steps.append(_read_step(index, ticket["reads"][0], excerpt))
        steps.append(_draft(index, True, decision_out))
    elif shape == "subscription":
        steps.append(_load_step(index, excerpt))
        steps.append(_read_step(index, ticket["reads"][0], excerpt))
        steps.append(
            _step(
                "workout",
                "work-out-refund",
                "span",
                _ms(40, index),
                {"price": "119.88"},
                {"method": "half the price"},
            )
        )
        steps.append(
            _step(
                "months",
                "estimate-remaining-months",
                "generation",
                _ms(640, index),
                {
                    "started": "about four months ago",
                    "price": "119.88",
                    "rule": "half the price in the first six months",
                },
                {"refund_amount": 59.94, "method": "half the price"},
                skills=True,
                usage=_tokens(index, True, "nested"),
                parent="workout",
            )
        )
        steps.append(_draft(index, True, decision_out))
    elif shape == "over_limit":
        steps.append(_load_step(index, excerpt))
        steps.append(
            _step(
                "limit",
                "approval-limit",
                "guardrail",
                _ms(48, index),
                {"shelf_price": 899, "limit_eur": 1000},
                {
                    "limit_eur": 1000,
                    "refund_amount": ticket["refund_amount"],
                    "action": "approve",
                },
            )
        )
        steps.append(_draft(index, True, decision_out))
    elif shape == "deny":
        steps.append(_load_step(index, excerpt))
        steps.append(
            _step(
                "window",
                "apply-window",
                "generation",
                _ms(520, index),
                {"tier": ticket["tier"], "method": "count the days yourself"},
                {"decision": "deny", "policy_rule": ticket["policy_rule"]},
                skills=True,
                usage=_tokens(index, True, "math"),
            )
        )
        steps.append(_draft(index, True, decision_out))
    else:
        raise ValueError(f"unknown history shape {shape}")
    return steps


_REFUND_FOLLOWUPS = (
    {
        "customer_message": "What about postage on {order}?",
        "reply": (
            "I opened the returns note again for {order}. I am not adding postage "
            "on top of the amount I already gave you."
        ),
        "shape": "reload",
        "decision": "not_applicable",
        "expected_decision": "not_applicable",
        "refund_amount": None,
        "expected_amount": None,
        "loaded": True,
        "should_load_skill": False,
        "policy_faithful": 0.75,
        "trace_name": "returns-other",
    },
    {
        "customer_message": "Ok, how do I send it back?",
        "reply": (
            "Use the returns form in your Kestrel account for {order}, print the label, "
            "and drop the parcel at any post office within fourteen days."
        ),
        "shape": "brief",
        "decision": "not_applicable",
        "expected_decision": "not_applicable",
        "refund_amount": None,
        "expected_amount": None,
        "loaded": False,
        "should_load_skill": False,
        "policy_faithful": 1.0,
        "trace_name": "returns-other",
    },
    {
        "customer_message": "When does the refund land?",
        "reply": (
            "Once we scan the return for {order}, the refund goes back to the original "
            "card in three to five business days."
        ),
        "shape": "brief",
        "decision": "not_applicable",
        "expected_decision": "not_applicable",
        "refund_amount": None,
        "expected_amount": None,
        "loaded": False,
        "should_load_skill": False,
        "policy_faithful": 1.0,
        "trace_name": "returns-other",
    },
)
_OTHER_FOLLOWUPS = (
    {
        "customer_message": "Thanks. When should {order} scan again?",
        "reply": (
            "The next scan for {order} should show up by tomorrow morning. "
            "I will not open a return for a parcel that is still moving."
        ),
        "shape": "brief",
        "decision": "not_applicable",
        "expected_decision": "not_applicable",
        "refund_amount": None,
        "expected_amount": None,
        "loaded": False,
        "should_load_skill": False,
        "policy_faithful": 1.0,
        "trace_name": "returns-other",
    },
    {
        "customer_message": "Can you text me when it arrives?",
        "reply": (
            "Tracking texts for {order} come from the carrier, not from this desk. "
            "The link in your shipping email is the one that updates."
        ),
        "shape": "brief",
        "decision": "not_applicable",
        "expected_decision": "not_applicable",
        "refund_amount": None,
        "expected_amount": None,
        "loaded": False,
        "should_load_skill": False,
        "policy_faithful": 1.0,
        "trace_name": "returns-other",
    },
    {
        "customer_message": "It still has not moved. Should I just return it?",
        "reply": (
            "I checked the returns note while looking at {order}. It is still in transit, "
            "so there is nothing to refund yet. Give it one more business day."
        ),
        "shape": "reload",
        "decision": "not_applicable",
        "expected_decision": "not_applicable",
        "refund_amount": None,
        "expected_amount": None,
        "loaded": True,
        "should_load_skill": False,
        "policy_faithful": 0.75,
        "trace_name": "returns-other",
    },
)


def iter_turns(count: int):
    """Yield ``(trace_index, session, turn, turns, archetype)`` for ``count`` traces.

    The plan is a prefix of the same schedule at every volume, so trace ids do
    not move when ``target_traces`` grows.
    """
    produced = 0
    session = 0
    while produced < count:
        turns = TURN_CYCLE[session % len(TURN_CYCLE)]
        archetype = session % 16
        for turn in range(turns):
            if produced >= count:
                return
            yield produced, session, turn, turns, archetype
            produced += 1
        session += 1


def _followup(ticket: dict, turn: int, archetype: int) -> dict:
    bank = _REFUND_FOLLOWUPS if ticket["case_type"] == "refund" else _OTHER_FOLLOWUPS
    return bank[(turn - 1 + archetype) % len(bank)]


def _follow_steps(spec: dict, index: int, message: str, decision_out: dict, excerpt: str):
    classify_out = {"case_type": "follow_up", "route": "returns" if spec["loaded"] else "general"}
    steps = [
        _step(
            "classify",
            "classify-intent",
            "span",
            _ms(120, index),
            {"message": message},
            classify_out,
        )
    ]
    if spec["shape"] == "reload":
        steps.append(
            _step(
                "route",
                "route-returns",
                "span",
                _ms(60, index),
                {"route": "returns"},
                {"chosen": SKILL_NAME, "reason": "follow-up on an order"},
            )
        )
        steps.append(_load_step(index, excerpt))
        steps.append(_draft(index, True, decision_out))
    else:
        steps.append(
            _step(
                "route",
                "route-general",
                "span",
                _ms(50, index),
                {"route": "general"},
                {"chosen": "general-desk"},
            )
        )
        steps.append(_draft(index, False, decision_out))
    return steps


def _step_metadata(name: str) -> dict:
    """Observation metadata for one child. Trace fields stay on the root."""
    if name == "loadSkill":
        return {"tool": "loadSkill"}
    if name == "skill_read":
        return {"tool": "skill_read"}
    if name == "classify-intent":
        return {"step": "classify"}
    if name == "photo-check":
        return {"step": "photo"}
    generations = {
        "draft-customer-reply",
        "estimate-refund",
        "apply-window",
        "estimate-remaining-months",
    }
    if name in generations:
        return {"step": "generation"}
    return {"step": name}


def _stamp_root_notes(span: dict, notes: dict) -> None:
    """Observation metadata that finalisation does not copy onto children."""
    span["attributes"].extend(
        string_attr(_OBS_META + key, value) for key, value in notes.items()
    )


def _emit_turn(
    ticket: dict,
    *,
    trace_index: int,
    session: int,
    turn: int,
    turns: int,
    seed: int,
    run_date: datetime,
    follow: dict | None,
) -> tuple[list, dict, list]:
    order_id = f"KC-{session:04d}"
    if follow is None:
        message = _fill(ticket["customer_message"], order_id)
        reply = _fill(ticket["reply"], order_id)
        decision = ticket["decision"]
        expected_decision = ticket["expected_decision"]
        refund_amount = ticket["refund_amount"]
        expected_amount = ticket["expected_amount"]
        loaded_ok = _skill_load_ok(ticket)
        policy = ticket["policy_faithful"]
        trace_name = ticket["trace_name"]
        decision_out = {"decision": decision, "refund_amount": refund_amount, "reply": reply}
        steps = _steps(ticket, trace_index, message, decision_out, _skill_excerpt())
    else:
        message = _fill(follow["customer_message"], order_id)
        reply = _fill(follow["reply"], order_id)
        decision = follow["decision"]
        expected_decision = follow["expected_decision"]
        refund_amount = follow["refund_amount"]
        expected_amount = follow["expected_amount"]
        loaded_ok = bool(follow["loaded"]) == bool(follow["should_load_skill"])
        policy = follow["policy_faithful"]
        trace_name = follow["trace_name"]
        decision_out = {"decision": decision, "refund_amount": refund_amount, "reply": reply}
        steps = _follow_steps(follow, trace_index, message, decision_out, _skill_excerpt())
    rng = Rng(seed).sub("returns", trace_index)
    trace_id = rng.trace_id("ticket")
    root_id = trace_root_span_id(trace_id)
    agent_id = rng.obs_id("agent")
    session_id = f"kc-sess-{seed}-{session:04d}"
    user_id = f"kc-{session:04d}"
    session_start = run_date - timedelta(
        days=(session % 28),
        hours=9 + (session % 8),
        minutes=(session * 3) % 60,
        seconds=session % 50,
    )
    start = session_start + timedelta(seconds=TURN_GAP_SECONDS[turn])
    cursor = start + timedelta(milliseconds=30)
    ids = {"agent": agent_id}
    built = []
    built_by_key: dict[str, dict] = {}
    for item in steps:
        obs_id = rng.obs_id(item["key"])
        ids[item["key"]] = obs_id
        begin = cursor
        end = begin + timedelta(milliseconds=item["ms"])
        cursor = end + timedelta(milliseconds=15)
        parent = agent_id if item["parent"] == "agent" else ids[item["parent"]]
        skills = SKILL_REFS if item["skills"] else None
        meta = _step_metadata(item["name"])
        if item["type"] == "generation":
            usage, cost = usage_and_cost(*item["usage"])
            built.append(
                generation_event(
                    obs_id=obs_id,
                    trace_id=trace_id,
                    name=item["name"],
                    start=begin,
                    end=end,
                    model=MODEL,
                    usage_details=usage,
                    cost_details=cost,
                    parent_id=parent,
                    input=item["input"],
                    output=item["output"],
                    metadata=meta,
                    model_parameters={"temperature": 0},
                    skills_available=skills,
                )
            )
            built_by_key[item["key"]] = built[-1]
        else:
            built.append(
                observation_event(
                    obs_id=obs_id,
                    trace_id=trace_id,
                    name=item["name"],
                    obs_type=item["type"],
                    start=begin,
                    end=end,
                    parent_id=parent,
                    input=item["input"],
                    output=item["output"],
                    metadata=meta,
                    skills_available=skills,
                )
            )
            built_by_key[item["key"]] = built[-1]
    for item in steps:
        if item["parent"] == "agent":
            continue
        parent_event = built_by_key[item["parent"]]
        child_event = built_by_key[item["key"]]
        if int(child_event["endTimeUnixNano"]) > int(parent_event["endTimeUnixNano"]):
            parent_event["endTimeUnixNano"] = child_event["endTimeUnixNano"]
    agent_end = cursor + timedelta(milliseconds=20)
    # Only the filterable key rides as trace metadata. Core copies that onto
    # every span; the rest of the story stays on the root observation.
    trace_meta = {"archetype": ticket["key"]}
    root = trace_event(
        trace_id=trace_id,
        timestamp=start,
        name=trace_name,
        user_id=user_id,
        session_id=session_id,
        tags=["returns", "kestrel", "skill-v1", ticket["tier"], ticket["channel"]],
        metadata=trace_meta,
        input=message,
        output=decision_out,
    )
    _stamp_root_notes(
        root,
        {
            "turn": str(turn + 1),
            "turns": str(turns),
            "channel": ticket["channel"],
            "tier": ticket["tier"],
            "skill_version": "1",
            "evidence": "prewritten",
        },
    )
    observations = [
        root,
        observation_event(
            obs_id=agent_id,
            trace_id=trace_id,
            name="returns-desk",
            obs_type="agent",
            start=start,
            end=agent_end,
            parent_id=root_id,
            input={"message": message, "turn": turn + 1},
            output=decision_out,
            metadata={"role": "agent"},
        ),
        *built,
    ]
    comment = f"{ticket['key']} turn {turn + 1}: prewritten v1 label"
    decision_score = score_event(
        score_id=rng.score_id("decision_correct"),
        trace_id=trace_id,
        name="decision_correct",
        value=1 if decision == expected_decision else 0,
        data_type="BOOLEAN",
        timestamp=start,
        comment=comment,
    )
    others = [
        score_event(
            score_id=rng.score_id("amount_correct"),
            trace_id=trace_id,
            name="amount_correct",
            value=1 if _amounts_match(refund_amount, expected_amount) else 0,
            data_type="BOOLEAN",
            timestamp=start,
            comment=comment,
        ),
        score_event(
            score_id=rng.score_id("skill_load_correct"),
            trace_id=trace_id,
            name="skill_load_correct",
            value=1 if loaded_ok else 0,
            data_type="BOOLEAN",
            timestamp=start,
            comment=comment,
        ),
        score_event(
            score_id=rng.score_id("policy_faithful"),
            trace_id=trace_id,
            name="policy_faithful",
            value=policy,
            data_type="NUMERIC",
            timestamp=start,
            comment=comment,
        ),
    ]
    return observations, decision_score, others


def build_events(
    target_traces: int, params: Mapping[str, Any], *, run_date: datetime,
) -> list[dict]:
    """Return the Spool lines for ``target_traces`` turns.

    Counts below three cannot show the opening beats. Higher counts continue
    the same session schedule. The first trace's ids do not depend on the total.
    """
    count = int(DERIVATION_HOOK(target_traces, params)["target_traces"])
    if count < 3:
        raise ValueError("returns history needs at least 3 traces for all story beats")
    seed = int(params.get("seed", 42))
    tickets = _tickets()
    observations: list[dict] = []
    decisions: list[dict] = []
    others: list[dict] = []
    for trace_index, session, turn, turns, archetype in iter_turns(count):
        ticket = tickets[archetype]
        follow = None if turn == 0 else _followup(ticket, turn, archetype)
        obs, decision, rest = _emit_turn(
            ticket,
            trace_index=trace_index,
            session=session,
            turn=turn,
            turns=turns,
            seed=seed,
            run_date=run_date,
            follow=follow,
        )
        observations.extend(obs)
        decisions.append(decision)
        others.extend(rest)
    return observations + decisions + others
