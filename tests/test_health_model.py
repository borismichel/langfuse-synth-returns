"""The live health probe uses the kit model, not core's sonnet fallback."""
from synth.companion.app import MODEL, build_adapter
from synth.config import load_config


def test_readiness_model_is_the_kit_default(monkeypatch):
    monkeypatch.delenv("LLM_MODEL", raising=False)
    adapter = build_adapter(load_config("config/demo.yaml"))
    identity = adapter.llm()
    assert identity.model == MODEL == "claude-sonnet-5-5"
    assert identity.provider == "anthropic"


def test_pinned_llm_model_still_wins(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "claude-haiku-test")
    adapter = build_adapter(load_config("config/demo.yaml"))
    assert adapter.llm().model == "claude-haiku-test"
