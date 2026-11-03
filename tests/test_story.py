"""Seeded history keeps its beats when the volume changes."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from langfuse_synth_core.seed.otlp import trace_root_span_id

from synth.materialize import (
    LOADED_NON_REFUND_SLOTS,
    NON_REFUND_SLOTS,
    build_events,
)
from synth.story import check_story

RUN = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)


def _attrs(span: dict) -> dict:
    found = {}
    for attr in span.get("attributes", []):
        value = attr["value"]
        if "stringValue" in value:
            found[attr["key"]] = value["stringValue"]
    return found


def _roots(events: list[dict]) -> list[dict]:
    return [
        event for event in events
        if "spanId" in event and event["spanId"] == trace_root_span_id(event["traceId"])
    ]


def _children(events: list[dict], trace_id: str) -> list[dict]:
    return [
        event for event in events
        if event.get("traceId") == trace_id and "spanId" in event
        and event["spanId"] != trace_root_span_id(trace_id)
    ]


class _Obs:
    def __init__(self, span: dict):
        attrs = _attrs(span)
        self.id = span["spanId"]
        self.parent_id = span.get("parentSpanId")
        self.name = span["name"]
        self.output = attrs.get("langfuse.observation.output")


class _Trace:
    def __init__(self, spans: list[dict]):
        self.observations = [_Obs(span) for span in spans]
        root = next(
            span for span in spans
            if span["spanId"] == trace_root_span_id(span["traceId"])
        )
        attrs = _attrs(root)
        self.name = attrs.get("langfuse.trace.name")
        self.output = attrs.get("langfuse.observation.output")
        self.id = root["traceId"]


class _Reader:
    def __init__(self, events: list[dict]):
        grouped: dict[str, list] = {}
        for event in events:
            if "spanId" in event:
                grouped.setdefault(event["traceId"], []).append(event)
        self._traces = {trace_id: _Trace(spans) for trace_id, spans in grouped.items()}

    def trace(self, trace_id: str, with_scores: bool = False):
        return self._traces.get(trace_id)


def _examples(events: list[dict], limit: int = 3) -> list[dict]:
    found = []
    for event in events:
        if event.get("type") == "score-create":
            found.append({"trace_id": event["body"]["traceId"], "name": event["body"]["name"]})
            if len(found) == limit:
                break
    return found


@pytest.mark.parametrize("count", [3, 4, 24, 101])
def test_first_beats_survive_volume_changes(count):
    events = build_events(count, {"seed": 42}, run_date=RUN)
    roots = _roots(events)
    assert len(roots) == count
    assert [root["name"] for root in roots[:3]] == [
        "returns-other", "returns-refund", "returns-refund",
    ]
    first = _attrs(roots[0])
    assert first["langfuse.trace.metadata.archetype"] == "shipping-loads-skill"
    tiny = build_events(3, {"seed": 42}, run_date=RUN)
    assert _roots(tiny)[0]["traceId"] == roots[0]["traceId"]


def test_too_small_volume_cannot_drop_a_beat():
    with pytest.raises(ValueError, match="at least 3"):
        build_events(2, {"seed": 42}, run_date=RUN)


def test_check_story_reads_the_first_three_decision_scores():
    events = build_events(8, {"seed": 42}, run_date=RUN)
    ok, detail = check_story(_Reader(events), _examples(events))
    assert ok, detail


def test_skill_refs_are_version_1_on_generations_and_skill_tools():
    events = build_events(16, {"seed": 42}, run_date=RUN)
    seen = set()
    for event in events:
        if "spanId" not in event:
            continue
        raw = _attrs(event).get("langfuse.observation.skills_available")
        if raw is None:
            continue
        parsed = json.loads(raw)
        assert parsed == [{"name": "returns-and-refunds", "version": 1}]
        seen.add(event["name"])
    assert {"draft-customer-reply", "loadSkill", "skill_read", "run_refund_calculator"} <= seen


def test_non_refund_load_rate_is_three_of_five():
    events = build_events(16, {"seed": 42}, run_date=RUN)
    roots = _roots(events)
    loaded = 0
    for index in NON_REFUND_SLOTS:
        children = _children(events, roots[index]["traceId"])
        did = any(child["name"] == "loadSkill" for child in children)
        assert did == (index in LOADED_NON_REFUND_SLOTS)
        loaded += int(did)
    assert loaded == 3


def test_shapes_are_not_one_flat_tree():
    events = build_events(16, {"seed": 42}, run_date=RUN)
    roots = _roots(events)

    def names(index: int) -> set[str]:
        return {child["name"] for child in _children(events, roots[index]["traceId"])}

    assert names(0) != names(5)
    assert names(5) != names(10)
    assert "estimate-remaining-months" in names(10)
    assert "approval-limit" in names(11)
    assert "run_refund_calculator" in names(3)
    shipping = _children(events, roots[0]["traceId"])
    agent = next(child for child in shipping if child["name"] == "returns-desk")
    load = next(child for child in shipping if child["name"] == "loadSkill")
    assert agent["parentSpanId"] == roots[0]["spanId"]
    assert load["parentSpanId"] == agent["spanId"]
    nested = next(child for child in _children(events, roots[10]["traceId"])
                  if child["name"] == "estimate-remaining-months")
    parent = next(child for child in _children(events, roots[10]["traceId"])
                  if child["name"] == "work-out-refund")
    assert nested["parentSpanId"] == parent["spanId"]
    assert int(nested["endTimeUnixNano"]) <= int(parent["endTimeUnixNano"])


def test_loaded_generations_are_expensive_and_some_amounts_are_wrong():
    events = build_events(24, {"seed": 42}, run_date=RUN)
    drafts = [
        event for event in events
        if event.get("name") == "draft-customer-reply"
    ]
    loaded = []
    quiet = []
    for event in drafts:
        usage = json.loads(_attrs(event)["langfuse.observation.usage_details"])
        cost = json.loads(_attrs(event)["langfuse.observation.cost_details"])
        assert cost["total"] > 0
        assert event["endTimeUnixNano"] > event["startTimeUnixNano"]
        (loaded if usage["input"] >= 3800 else quiet).append(usage["input"])
    assert loaded and quiet
    assert max(quiet) < 900
    scores = [event["body"] for event in events if event.get("type") == "score-create"]
    assert [score["name"] for score in scores[:5]] == ["decision_correct"] * 5
    assert len({score["traceId"] for score in scores[:5]}) == 5
    assert any(score["name"] == "amount_correct" and score["value"] == 0 for score in scores)
    assert all(score["value"] in (0, 1) for score in scores if score["dataType"] == "BOOLEAN")


def test_history_spans_about_four_weeks_and_stays_on_v1():
    events = build_events(84, {"seed": 42}, run_date=RUN)
    starts = [int(event["startTimeUnixNano"]) for event in _roots(events)]
    oldest = datetime.fromtimestamp(min(starts) / 1e9, tz=timezone.utc)
    assert (RUN - oldest).days >= 27
    blob = json.dumps(events)
    assert '"version":2' not in blob
    assert "skill-v1" in blob
