"""Preview renders the desk from fixtures and does not call a model."""
from fastapi.testclient import TestClient

from synth.companion.app import create_app
from synth.companion.preview import FixtureAdapter


def _client() -> TestClient:
    adapter = FixtureAdapter()
    app = create_app(adapter, preview=True)
    adapter.mount_health(app)
    return TestClient(app)


def test_pages_render_and_health_is_not_ready():
    client = _client()
    home = client.get("/")
    chat = client.get("/chat")
    health = client.get("/healthz")
    assert home.status_code == 200
    assert "Returns" in home.text
    assert "Presenter controls" in home.text
    assert chat.status_code == 200
    assert "rr-001" in chat.text
    assert health.status_code == 503
    assert health.json()["ready"] is False


def test_preview_post_uses_fixtures_for_one_label_and_for_compare():
    client = _client()
    one = client.post(
        "/chat",
        data={"item": "rr-001", "action": "run", "label": "candidate", "message": ""},
    )
    assert one.status_code == 200
    assert "Fixture · candidate" in one.text
    assert "approve_full" in one.text
    both = client.post(
        "/chat",
        data={"item": "rr-013", "action": "compare", "label": "production", "message": ""},
    )
    assert both.status_code == 200
    assert "Fixture · production" in both.text
    assert "Fixture · candidate" in both.text
    assert "loaded the returns skill" in both.text


def test_empty_submit_asks_for_a_ticket():
    client = _client()
    response = client.post(
        "/chat",
        data={"item": "", "message": "", "action": "run", "label": "production"},
    )
    assert response.status_code == 200
    assert "Pick a golden ticket or type a message." in response.text


def test_custom_message_without_a_ticket_still_renders():
    client = _client()
    response = client.post(
        "/chat",
        data={"item": "", "message": "Where is my parcel?", "action": "run", "label": "production"},
    )
    assert response.status_code == 200
    assert "Fixture · production" in response.text
    assert "not_applicable" in response.text
    assert "loaded the returns skill" in response.text
