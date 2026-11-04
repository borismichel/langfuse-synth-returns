"""One Kestrel ticket against a fetched skill version. Tracing is the caller's emitter."""
from __future__ import annotations

import json
import os
import re
from contextlib import contextmanager
from typing import Any

from opentelemetry import context as otel_context

from ..pricing import usage_and_cost
from .tools import TOOL_SCHEMAS, FetchedSkill, dispatch

MODEL = "claude-sonnet-5-5"
_REPLY_MAX_TOKENS = 4096
_JSON = re.compile(r"\{.*\}", re.DOTALL)


def system_prompt(skill: FetchedSkill) -> str:
    """Name and description only. The body arrives through loadSkill."""
    return (
        "You are the returns desk for Kestrel & Co, a fictional EU retailer. "
        "Reply in English.\n\n"
        "Available skills (name and description only — the body is not included):\n"
        f"- {skill.name}: {skill.description()}\n\n"
        "Call loadSkill when a skill's description matches the customer's request. "
        "Read further files with skill_read. Use run_refund_calculator when the skill "
        "tells you to compute an amount.\n\n"
        "Earlier turns of this conversation, if any, are already in the messages. "
        "Answer the latest customer message.\n\n"
        "Finish with one JSON object and no other text: "
        '{"decision":"approve_full|approve_partial|store_credit|deny|escalate|not_applicable",'
        '"refund_amount": number or null, "reply":"customer-facing text"}.'
    )


def parse_decision(text: str) -> dict:
    match = _JSON.search(text or "")
    if match is None:
        return {
            "decision": "escalate",
            "refund_amount": None,
            "reply": (text or "")[:2000],
            "error": "model did not return JSON",
        }
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {
            "decision": "escalate",
            "refund_amount": None,
            "reply": (text or "")[:2000],
            "error": "model JSON did not parse",
        }
    if not isinstance(data, dict):
        data = {}
    amount = data.get("refund_amount")
    if isinstance(amount, str):
        try:
            amount = float(amount)
        except ValueError:
            amount = None
    elif isinstance(amount, bool) or amount is None:
        amount = None if amount is None else float(amount)
    elif isinstance(amount, (int, float)):
        amount = float(amount)
    else:
        amount = None
    return {
        "decision": data.get("decision") or "escalate",
        "refund_amount": amount,
        "reply": str(data.get("reply") or ""),
    }


def _ticket_text(ticket: dict) -> str:
    return json.dumps(
        {
            "customer_message": ticket.get("customer_message"),
            "order": ticket.get("order"),
            "customer_tier": ticket.get("customer_tier"),
        },
        ensure_ascii=False,
    )


def _blocks(response) -> tuple[str, list]:
    text: list[str] = []
    tools = []
    for block in response.content:
        if getattr(block, "type", None) == "text":
            text.append(block.text)
        elif getattr(block, "type", None) == "tool_use":
            tools.append(block)
    return "\n".join(text), tools


@contextmanager
def _fresh_otel_context():
    """Start a turn with no current span.

    A long-running server can leave an OpenTelemetry span current after the
    previous request: core's ``LiveEmitter.trace`` opens the root with
    ``start_as_current_observation``, which parents onto that span, and the
    parent id is not an observation in this trace. A standalone emitter in a
    fresh process does not see the leak. Attaching an empty context here makes
    the root parentless even when the previous span was not detached.
    """
    token = otel_context.attach(otel_context.Context())
    try:
        yield
    finally:
        otel_context.detach(token)


def run_ticket(
    skill: FetchedSkill,
    ticket: dict,
    *,
    emitter,
    anthropic_client,
    model: str = MODEL,
    user_id: str = "kc-live",
    session_id: str = "kc-live-session",
    tags: list[str] | None = None,
    metadata: dict | None = None,
    history: list[dict] | None = None,
) -> dict:
    """Run one turn. Tools are siblings under the agent, not children of a generation.

    ``history`` is the prior turns of this chat, ``{"role", "content"}`` pairs.
    They stay on this turn's agent input and on the model messages. The
    ``session_id`` is the caller's, stable across turns.
    """
    message = _ticket_text(ticket)
    prior = [
        {"role": turn["role"], "content": turn["content"]}
        for turn in (history or [])
        if turn.get("role") in {"user", "assistant"} and turn.get("content")
    ]
    refs = skill.refs
    tier = str(ticket.get("customer_tier") or "standard")
    trace_tags = list(tags or ["returns", "kestrel", f"skill-v{skill.version}", tier, "live"])
    totals = {"input": 0, "output": 0}
    loaded = False
    calculated = False
    files_read: list[str] = []
    final_text = ""
    capped_without_text = False
    messages: list[dict] = [*prior, {"role": "user", "content": message}]
    agent_input = {
        "customer_message": ticket.get("customer_message"),
        "order": ticket.get("order"),
        "prior_turns": prior,
    }

    with _fresh_otel_context(), emitter.trace(
        "returns-ticket",
        user_id=user_id,
        session_id=session_id,
        tags=trace_tags,
        input=ticket.get("customer_message"),
        metadata={"skill": skill.name, "skill_version": str(skill.version), **(metadata or {})},
        skills_available=refs,
    ) as trace:
        with trace.observation("returns-desk", as_type="agent", input=agent_input) as agent:
            with agent.span(
                "classify-intent", input={"message": ticket.get("customer_message")}
            ) as classify:
                classify.update(output={"handed_to": model, "skill": skill.name})
            for step in range(8):
                gen_name = "classify-and-route" if step == 0 else "draft-customer-reply"
                with agent.generation(
                    gen_name,
                    model=model,
                    input={"step": step},
                    skills_available=refs,
                ) as generation:
                    response = None
                    stopped_at_cap = False
                    inp = out = 0
                    for _attempt in range(2):
                        response = anthropic_client.messages.create(
                            model=model,
                            max_tokens=_REPLY_MAX_TOKENS,
                            system=system_prompt(skill),
                            tools=TOOL_SCHEMAS,
                            messages=messages,
                        )
                        usage = getattr(response, "usage", None)
                        inp += int(getattr(usage, "input_tokens", 0) or 0)
                        out += int(getattr(usage, "output_tokens", 0) or 0)
                        stopped_at_cap = getattr(response, "stop_reason", None) == "max_tokens"
                        if not stopped_at_cap:
                            break
                    text, tool_uses = _blocks(response)
                    totals["input"] += inp
                    totals["output"] += out
                    details, cost = usage_and_cost(inp, out)
                    if not tool_uses and step == 0:
                        generation.update(name="draft-customer-reply")
                    generation.update(
                        output={"text": text, "tools": [block.name for block in tool_uses]},
                        usage_details=details,
                        cost_details=cost,
                    )
                if not tool_uses:
                    final_text = text
                    capped_without_text = stopped_at_cap and not text.strip()
                    break
                messages.append({"role": "assistant", "content": response.content})
                results = []
                for block in tool_uses:
                    arguments = block.input if isinstance(block.input, dict) else {}
                    with agent.tool(block.name, input=arguments, skills_available=refs) as tool:
                        result = dispatch(skill, block.name, arguments)
                        tool.update(output=result)
                    if block.name == "loadSkill":
                        loaded = True
                    if block.name == "run_refund_calculator":
                        calculated = True
                    if block.name == "skill_read":
                        files_read.append(str(arguments.get("path") or ""))
                    content = result if isinstance(result, str) else json.dumps(result)
                    results.append(
                        {"type": "tool_result", "tool_use_id": block.id, "content": content}
                    )
                messages.append({"role": "user", "content": results})
            else:
                final_text = final_text or "stopped before a reply"
            parsed = parse_decision(final_text)
            if capped_without_text:
                parsed["error"] = "model stopped at max_tokens"
                parsed["reply"] = ""
            route = "route-returns" if loaded else "route-general"
            with agent.span(route, input={"loaded_skill": loaded}) as routed:
                routed.update(output={"decision": parsed["decision"], "files_read": files_read})
            agent.update(output=parsed)
        trace.update(output=parsed)

    _usage, cost = usage_and_cost(totals["input"], totals["output"])
    return {
        **parsed,
        "loaded_skill": loaded,
        "calculated": calculated,
        "files_read": files_read,
        "usage": {**_usage, "cost": cost["total"]},
    }


def anthropic_client_from_env():
    """The experiment command's client. The portal injects ANTHROPIC_API_KEY."""
    key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("LLM_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    from anthropic import Anthropic

    return Anthropic(api_key=key)


def resolved_model() -> str:
    return os.environ.get("LLM_MODEL") or MODEL


def as_mapping(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if value is None:
        return {}
    return dict(value)
