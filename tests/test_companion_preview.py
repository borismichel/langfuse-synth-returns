"""Preview chat renders from fixtures and does not call a model."""
import json
import re

from fastapi.testclient import TestClient

from synth.companion.app import create_app
from synth.companion.preview import FixtureAdapter

_SESSION = re.compile(r"name='session_id' value='(kc-[a-f0-9]{16})'")
_HISTORY = re.compile(r"name='history' value='([^']*)'")


def _client() -> TestClient:
    adapter = FixtureAdapter()
    app = create_app(adapter, preview=True)
    adapter.mount_health(app)
    return TestClient(app)


def _hidden(html: str) -> tuple[str, str]:
    session = _SESSION.search(html)
    history = _HISTORY.search(html)
    assert session is not None
    assert history is not None
    return session.group(1), history.group(1).replace("&quot;", '"')


def test_pages_render_and_health_is_not_ready():
    client = _client()
    home = client.get("/")
    chat = client.get("/chat")
    health = client.get("/healthz")
    assert home.status_code == 200
    assert "Returns" in home.text
    assert "Open the desk" in home.text
    assert "Presenter controls" in home.text
    assert chat.status_code == 200
    assert "New chat" in chat.text
    assert "production (v1)" in chat.text
    assert "candidate (v2)" in chat.text
    assert "Where is my parcel?" in chat.text
    assert health.status_code == 503
    assert health.json()["ready"] is False


def test_empty_submit_asks_for_a_message():
    client = _client()
    first = client.get("/chat")
    session, history = _hidden(first.text)
    response = client.post(
        "/chat",
        data={"message": "   ", "label": "production", "session_id": session, "history": history},
    )
    assert response.status_code == 200
    assert "Type a message." in response.text


def test_a_chat_keeps_one_session_across_turns():
    client = _client()
    first = client.get("/chat")
    session, history = _hidden(first.text)
    opened = client.post(
        "/chat",
        data={
            "starter": "parcel",
            "label": "production",
            "session_id": session,
            "history": history,
            "message": "",
        },
    )
    assert opened.status_code == 200
    assert "Where is my parcel?" in opened.text
    assert "loaded the returns skill" in opened.text
    assert "loadSkill" in opened.text
    again, kept = _hidden(opened.text)
    assert again == session
    turns = json.loads(kept)
    assert [turn["role"] for turn in turns] == ["user", "assistant"]
    follow = client.post(
        "/chat",
        data={
            "message": "what about postage?",
            "label": "production",
            "session_id": again,
            "history": kept,
        },
    )
    assert follow.status_code == 200
    assert "what about postage?" in follow.text
    assert "worked the postage out itself" in follow.text
    same, transcript = _hidden(follow.text)
    assert same == session
    roles = [turn["role"] for turn in json.loads(transcript)]
    assert roles == ["user", "assistant", "user", "assistant"]


def test_new_chat_mints_another_session():
    client = _client()
    first = _hidden(client.get("/chat").text)[0]
    second = _hidden(client.get("/chat").text)[0]
    assert first != second


def test_production_shirt_quotes_the_wrong_amount_without_a_calculator():
    client = _client()
    session, history = _hidden(client.get("/chat").text)
    response = client.post(
        "/chat",
        data={
            "starter": "shirt",
            "label": "production",
            "session_id": session,
            "history": history,
        },
    )
    assert response.status_code == 200
    assert "28.99" in response.text
    assert "run_refund_calculator" not in response.text
    assert "Returns Desk · production" in response.text


def test_candidate_shirt_uses_the_calculator_and_the_right_amount():
    client = _client()
    session, history = _hidden(client.get("/chat").text)
    response = client.post(
        "/chat",
        data={
            "starter": "shirt",
            "label": "candidate",
            "session_id": session,
            "history": history,
        },
    )
    assert response.status_code == 200
    assert "29.99" in response.text
    assert "run_refund_calculator" in response.text
    assert "loaded the returns skill" not in response.text
    assert "Returns Desk · candidate" in response.text


def test_candidate_parcel_leaves_the_skill_closed():
    client = _client()
    session, history = _hidden(client.get("/chat").text)
    response = client.post(
        "/chat",
        data={
            "message": "Where is my parcel? The tracking has not moved since Monday.",
            "label": "candidate",
            "session_id": session,
            "history": history,
        },
    )
    assert response.status_code == 200
    assert "skill stays closed" in response.text
    assert "not_applicable" in response.text
    assert "loadSkill" not in response.text
