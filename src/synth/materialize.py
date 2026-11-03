"""Four weeks of prewritten v1 returns-desk history. Model-free.

Each ticket is one trace. The shape cycles through 16 archetypes so a shipping
question, a wrong amount, a missing reference, and a calculator call are not
the same tree. v2 is not in this history. Timestamps depend on the index and
``run_date`` only, so the first N traces stay byte-stable when volume grows.
"""
from __future__ import annotations

import importlib.util
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
from langfuse_synth_core.seed.otlp import trace_root_span_id

from .config import DERIVATION_HOOK
from .paths import kit_root
from .pricing import usage_and_cost

SKILL_NAME = "returns-and-refunds"
SKILL_REFS = [{"name": SKILL_NAME, "version": 1}]
MODEL = "claude-sonnet-5-5"
NON_REFUND_SLOTS = frozenset({0, 5, 8, 9, 12})
LOADED_NON_REFUND_SLOTS = frozenset({0, 8, 12})


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


@lru_cache(maxsize=1)
def _calc_refund():
    path = (
        kit_root()
        / "skill_bundles"
        / "returns-and-refunds"
        / "v2"
        / "scripts"
        / "calc_refund.py"
    )
    spec = importlib.util.spec_from_file_location("kestrel_calc_refund", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load calculator at {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.calc_refund


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


def _calc_step(index: int, payload: dict, result: dict):
    return _step(
        "calc",
        "run_refund_calculator",
        "tool",
        _ms(36, index),
        payload,
        result,
        skills=True,
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


def _steps(ticket: dict, index: int, message: str, decision_out: dict, excerpt: str, calc):
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
                {"price_seen": ticket["expected_amount"], "method": "work it out yourself"},
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
        steps.append(_load_step(index, excerpt))
        steps.append(_calc_step(index, calc["payload"], calc["result"]))
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
                {"photo": True, "within_7_days": True, "action": "approve"},
            )
        )
        steps.append(_calc_step(index, calc["payload"], calc["result"]))
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
                {"started": "about four months ago", "price": "119.88"},
                {"remaining_months": 6, "refund_amount": 59.94},
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
                {"amount": 899, "limit_eur": 500},
                {"limit_eur": 500, "amount": 899, "action": "escalate"},
            )
        )
        steps.append(_draft(index, True, decision_out))
    elif shape == "deny":
        steps.append(_load_step(index, excerpt))
        steps.append(_calc_step(index, calc["payload"], calc["result"]))
        steps.append(_draft(index, True, decision_out))
    else:
        raise ValueError(f"unknown history shape {shape}")
    return steps


def _calc_bundle(ticket: dict, run_date: datetime, order_id: str) -> dict | None:
    spec = ticket.get("calc")
    if not spec:
        return None
    today = run_date.date()
    delivery = today - timedelta(days=int(spec["days_ago"]))
    item = {
        "sku": spec["sku"],
        "category": spec["category"],
        "price": spec["price"],
        "on_sale": bool(spec["on_sale"]),
        "condition_reported": spec["condition"],
        "shipping_fee": spec["shipping_fee"],
        "return": True,
        "delivery_date": delivery.isoformat(),
        "photo": bool(spec["photo"]),
        "downloaded": bool(spec["downloaded"]),
    }
    order = {
        "order_id": order_id,
        "order_date": (delivery - timedelta(days=2)).isoformat(),
        "delivery_date": delivery.isoformat(),
        "today": today.isoformat(),
        "customer_tier": spec["tier"],
        "items": [item],
    }
    payload = {
        "order": order,
        "items": [item],
        "today": today.isoformat(),
        "customer_tier": spec["tier"],
    }
    return {"payload": payload, "result": _calc_refund()(payload)}


def _emit_trace(ticket: dict, index: int, seed: int, run_date: datetime) -> tuple[list, dict, list]:
    order_id = f"KC-{index:04d}"
    message = _fill(ticket["customer_message"], order_id)
    reply = _fill(ticket["reply"], order_id)
    decision_out = {
        "decision": ticket["decision"],
        "refund_amount": ticket["refund_amount"],
        "reply": reply,
    }
    rng = Rng(seed).sub("returns", index)
    trace_id = rng.trace_id("ticket")
    root_id = trace_root_span_id(trace_id)
    agent_id = rng.obs_id("agent")
    owner = index - 1 if index % 9 == 8 else index
    session_id = f"kc-sess-{seed}-{owner:04d}"
    user_id = f"kc-{index:04d}"
    start = run_date - timedelta(
        days=(index % 28),
        hours=9 + (index % 8),
        minutes=(index * 3) % 60,
        seconds=index % 50,
    )
    calc = _calc_bundle(ticket, run_date, order_id) if ticket["did_calc"] else None
    steps = _steps(ticket, index, message, decision_out, _skill_excerpt(), calc)
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
        meta = {"archetype": ticket["key"], "evidence": "prewritten"}
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
    metadata = {
        "archetype": ticket["key"],
        "beat": ticket["key"],
        "channel": ticket["channel"],
        "tier": ticket["tier"],
        "skill": SKILL_NAME,
        "skill_version": "1",
        "evidence": "prewritten",
    }
    observations = [
        trace_event(
            trace_id=trace_id,
            timestamp=start,
            name=ticket["trace_name"],
            user_id=user_id,
            session_id=session_id,
            tags=["returns", "kestrel", "skill-v1", ticket["tier"], ticket["channel"]],
            metadata=metadata,
            input=message,
            output=decision_out,
        ),
        observation_event(
            obs_id=agent_id,
            trace_id=trace_id,
            name="returns-desk",
            obs_type="agent",
            start=start,
            end=agent_end,
            parent_id=root_id,
            input={"message": message},
            output=decision_out,
            metadata=metadata,
        ),
        *built,
    ]
    comment = f"{ticket['key']}: prewritten v1 label"
    decision = score_event(
        score_id=rng.score_id("decision_correct"),
        trace_id=trace_id,
        name="decision_correct",
        value=1 if ticket["decision"] == ticket["expected_decision"] else 0,
        data_type="BOOLEAN",
        timestamp=start,
        comment=comment,
    )
    others = [
        score_event(
            score_id=rng.score_id("amount_correct"),
            trace_id=trace_id,
            name="amount_correct",
            value=1 if _amounts_match(ticket["refund_amount"], ticket["expected_amount"]) else 0,
            data_type="BOOLEAN",
            timestamp=start,
            comment=comment,
        ),
        score_event(
            score_id=rng.score_id("skill_load_correct"),
            trace_id=trace_id,
            name="skill_load_correct",
            value=1 if _skill_load_ok(ticket) else 0,
            data_type="BOOLEAN",
            timestamp=start,
            comment=comment,
        ),
        score_event(
            score_id=rng.score_id("policy_faithful"),
            trace_id=trace_id,
            name="policy_faithful",
            value=ticket["policy_faithful"],
            data_type="NUMERIC",
            timestamp=start,
            comment=comment,
        ),
    ]
    return observations, decision, others


def build_events(
    target_traces: int, params: Mapping[str, Any], *, run_date: datetime,
) -> list[dict]:
    """Return the Spool lines for ``target_traces`` tickets.

    Counts below three cannot show the three presenter beats. Higher counts
    repeat the 16-archetype cycle. The first trace's ids do not depend on the
    total.
    """
    count = int(DERIVATION_HOOK(target_traces, params)["target_traces"])
    if count < 3:
        raise ValueError("returns history needs at least 3 traces for all story beats")
    seed = int(params.get("seed", 42))
    tickets = _tickets()
    observations: list[dict] = []
    decisions: list[dict] = []
    others: list[dict] = []
    for index in range(count):
        obs, decision, rest = _emit_trace(tickets[index % 16], index, seed, run_date)
        observations.extend(obs)
        decisions.append(decision)
        others.extend(rest)
    return observations + decisions + others
