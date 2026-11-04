"""A reply that hits the token cap is retried once; an empty reply is a note."""
import json
import re
from contextlib import contextmanager

from fastapi.testclient import TestClient

from synth.companion.app import create_app
from synth.companion.preview import FixtureAdapter
from synth.returns_agent.agent import _REPLY_MAX_TOKENS, run_ticket
from synth.returns_agent.tools import FetchedSkill

_SESSION = re.compile(r"name='session_id' value='(kc-[a-f0-9]{16})'")
_HISTORY = re.compile(r"name='history' value='([^']*)'")
_REPLY = '{"decision":"approve_full","refund_amount":28.99,"reply":"EUR 28.99 back"}'


class _Block:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _Tool:
    type = "tool_use"
    name = "loadSkill"
    id = "tool-1"
    input = {"name": "returns-and-refunds"}


class _Usage:
    def __init__(self, input_tokens, output_tokens):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _Response:
    def __init__(self, content, stop_reason, usage):
        self.content = content
        self.stop_reason = stop_reason
        self.usage = usage


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


def _skill() -> FetchedSkill:
    return FetchedSkill(
        name="returns-and-refunds",
        version=1,
        files={
            "SKILL.md": (
                "---\nname: returns-and-refunds\n"
                "description: Helps with customer orders\n---\nbody\n"
            )
        },
    )


def _ticket() -> dict:
    return {
        "customer_message": "I want to return the navy t-shirt.",
        "order": {"order_id": "KC-10482", "items": []},
        "customer_tier": "standard",
    }


def _run(responses):
    client = _Anthropic(responses)
    result = run_ticket(
        _skill(),
        _ticket(),
        emitter=_Emitter(),
        anthropic_client=client,
        model="claude-sonnet-5-5",
    )
    return client.messages, result


def test_max_tokens_retries_once_then_uses_the_reply():
    messages, result = _run([
        _Response([], "max_tokens", _Usage(11, 1024)),
        _Response([_Block(_REPLY)], "end_turn", _Usage(12, 40)),
    ])
    assert len(messages.calls) == 2
    assert all(call["max_tokens"] == _REPLY_MAX_TOKENS == 4096 for call in messages.calls)
    assert result["reply"] == "EUR 28.99 back"
    assert result["decision"] == "approve_full"
    assert result["usage"]["input"] == 23
    assert result["usage"]["output"] == 1064
    assert "error" not in result


def test_capped_tool_call_is_not_dispatched():
    messages, result = _run([
        _Response([_Tool()], "max_tokens", _Usage(4, 1024)),
        _Response([_Block(_REPLY)], "end_turn", _Usage(4, 20)),
    ])
    assert len(messages.calls) == 2
    assert result["loaded_skill"] is False
    assert result["reply"] == "EUR 28.99 back"


def test_a_normal_stop_is_not_retried():
    messages, result = _run([
        _Response([_Block(_REPLY)], "end_turn", _Usage(5, 30)),
    ])
    assert len(messages.calls) == 1
    assert messages.calls[0]["max_tokens"] == 4096
    assert result["reply"] == "EUR 28.99 back"


def test_two_empty_caps_surface_an_error():
    messages, result = _run([
        _Response([], "max_tokens", _Usage(8, 4096)),
        _Response([], "max_tokens", _Usage(8, 4096)),
    ])
    assert len(messages.calls) == 2
    assert result["reply"] == ""
    assert result["decision"] == "escalate"
    assert result["error"] == "model stopped at max_tokens"


def test_empty_live_reply_is_a_note_and_not_a_bubble(monkeypatch):
    def empty(*_args, **_kwargs):
        return {
            "decision": "escalate",
            "refund_amount": None,
            "loaded": False,
            "calculated": False,
            "reference": None,
            "text": "",
        }

    monkeypatch.setattr("synth.companion.app._live_turn", empty)
    client = TestClient(create_app(FixtureAdapter(), preview=False))
    first = client.get("/chat")
    session = _SESSION.search(first.text)
    history = _HISTORY.search(first.text)
    assert session is not None and history is not None
    response = client.post(
        "/chat",
        data={
            "message": "I want to return the navy t-shirt.",
            "label": "production",
            "session_id": session.group(1),
            "history": history.group(1).replace("&quot;", '"'),
        },
    )
    assert response.status_code == 200
    assert "stopped before it wrote a reply" in response.text
    assert "I want to return the navy t-shirt." not in response.text
    kept = _HISTORY.search(response.text)
    assert kept is not None
    assert json.loads(kept.group(1).replace("&quot;", '"')) == []
