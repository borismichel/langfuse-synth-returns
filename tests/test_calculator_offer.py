"""The calculator is offered only with the script, and only a real run counts."""
from contextlib import contextmanager
from pathlib import Path

from synth.returns_agent.agent import run_ticket, system_prompt
from synth.returns_agent.tools import FetchedSkill, tool_schemas

ROOT = Path(__file__).resolve().parents[1] / "skill_bundles" / "returns-and-refunds"
_REPLY = '{"decision":"approve_full","refund_amount":29.99,"reply":"EUR 29.99 back"}'


class _Text:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _Tool:
    def __init__(self, name, arguments):
        self.type = "tool_use"
        self.name = name
        self.id = "tool-1"
        self.input = arguments


class _Usage:
    input_tokens = 4
    output_tokens = 8


class _Response:
    def __init__(self, content):
        self.content = content
        self.stop_reason = "end_turn"
        self.usage = _Usage()


class _Messages:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


class _Anthropic:
    def __init__(self, responses):
        self.messages = _Messages(responses)


class _Node:
    def update(self, **_kwargs):
        return self

    @contextmanager
    def _child(self):
        yield self

    def observation(self, *_args, **_kwargs):
        return self._child()

    def span(self, *_args, **_kwargs):
        return self._child()

    def generation(self, *_args, **_kwargs):
        return self._child()

    def tool(self, *_args, **_kwargs):
        return self._child()


class _Emitter:
    @contextmanager
    def trace(self, *_args, **_kwargs):
        yield _Node()


def _skill(version: int) -> FetchedSkill:
    folder = ROOT / f"v{version}"
    files = {
        path.relative_to(folder).as_posix(): path.read_text(encoding="utf-8")
        for path in folder.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    }
    return FetchedSkill(name="returns-and-refunds", version=version, files=files)


def _names(skill: FetchedSkill) -> set[str]:
    return {schema["name"] for schema in tool_schemas(skill)}


def _run(skill: FetchedSkill, responses):
    client = _Anthropic(responses)
    result = run_ticket(
        skill,
        {
            "customer_message": "I want to return the navy t-shirt.",
            "order": {"order_id": "KC-10482", "items": []},
            "customer_tier": "standard",
        },
        emitter=_Emitter(),
        anthropic_client=client,
        model="claude-sonnet-5-5",
    )
    return client.messages, result


def test_v1_does_not_offer_the_calculator_and_a_failed_call_is_not_calculated():
    skill = _skill(1)
    assert "run_refund_calculator" not in _names(skill)
    assert "run_refund_calculator" not in system_prompt(skill)
    messages, result = _run(skill, [
        _Response([_Tool("run_refund_calculator", {"today": "2026-10-20", "items": []})]),
        _Response([_Text(_REPLY)]),
    ])
    offered = {schema["name"] for schema in messages.calls[0]["tools"]}
    assert offered == {"loadSkill", "skill_read"}
    assert result["calculated"] is False


def test_v2_offers_the_calculator_and_a_successful_call_is_calculated():
    skill = _skill(2)
    assert "run_refund_calculator" in _names(skill)
    assert "run_refund_calculator" in system_prompt(skill)
    payload = {
        "today": "2026-10-20",
        "customer_tier": "standard",
        "items": [{
            "sku": "TEE",
            "category": "apparel",
            "price": "29.99",
            "delivery_date": "2026-10-10",
            "condition_reported": "unused",
            "return": True,
        }],
    }
    messages, result = _run(skill, [
        _Response([_Tool("run_refund_calculator", payload)]),
        _Response([_Text(_REPLY)]),
    ])
    offered = {schema["name"] for schema in messages.calls[0]["tools"]}
    assert "run_refund_calculator" in offered
    assert result["calculated"] is True
    assert result["refund_amount"] == 29.99
