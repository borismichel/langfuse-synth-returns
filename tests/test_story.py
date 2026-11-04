"""Seeded history keeps its beats when the volume changes."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from langfuse_synth_core.seed.otlp import finalize, trace_root_span_id

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
    assert roots[0]["name"] == "returns-other"
    first = _attrs(roots[0])
    assert first["langfuse.trace.metadata.archetype"] == "shipping-loads-skill"
    tiny = build_events(3, {"seed": 42}, run_date=RUN)
    assert [root["traceId"] for root in _roots(tiny)] == [
        root["traceId"] for root in roots[:3]
    ]


def test_too_small_volume_cannot_drop_a_beat():
    with pytest.raises(ValueError, match="at least 3"):
        build_events(2, {"seed": 42}, run_date=RUN)


def test_check_story_reads_the_opening_decision_scores():
    events = build_events(8, {"seed": 42}, run_date=RUN)
    ok, detail = check_story(_Reader(events), _examples(events, limit=5))
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
    assert {"draft-customer-reply", "loadSkill", "skill_read"} <= seen
    assert "run_refund_calculator" not in seen


def _decision_roots(events: list[dict]) -> list[dict]:
    found = []
    for root in _roots(events):
        if _attrs(root).get("langfuse.observation.metadata.turn") == "1":
            found.append(root)
    return found


def test_non_refund_load_rate_is_three_of_five():
    events = build_events(40, {"seed": 42}, run_date=RUN)
    roots = _decision_roots(events)[:16]
    assert len(roots) == 16
    loaded = 0
    for index in NON_REFUND_SLOTS:
        children = _children(events, roots[index]["traceId"])
        did = any(child["name"] == "loadSkill" for child in children)
        assert did == (index in LOADED_NON_REFUND_SLOTS)
        loaded += int(did)
    assert loaded == 3


def test_shapes_are_not_one_flat_tree():
    events = build_events(40, {"seed": 42}, run_date=RUN)
    by_name = {
        _attrs(root)["langfuse.trace.metadata.archetype"]: root
        for root in _decision_roots(events)
    }

    def names(key: str) -> set[str]:
        return {child["name"] for child in _children(events, by_name[key]["traceId"])}

    assert names("shipping-loads-skill") != names("address-no-skill")
    assert names("address-no-skill") != names("subscription-math")
    assert "estimate-remaining-months" in names("subscription-math")
    assert "approval-limit" in names("laptop-over-limit")
    assert "run_refund_calculator" not in names("clean-shoes")
    assert "run_refund_calculator" not in names("damaged-reference")
    shipping_root = by_name["shipping-loads-skill"]
    shipping = _children(events, shipping_root["traceId"])
    agent = next(child for child in shipping if child["name"] == "returns-desk")
    load = next(child for child in shipping if child["name"] == "loadSkill")
    assert agent["parentSpanId"] == shipping_root["spanId"]
    assert load["parentSpanId"] == agent["spanId"]
    nested_root = by_name["subscription-math"]["traceId"]
    nested = next(
        child for child in _children(events, nested_root)
        if child["name"] == "estimate-remaining-months"
    )
    parent = next(
        child for child in _children(events, nested_root) if child["name"] == "work-out-refund"
    )
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
    assert "run_refund_calculator" not in blob
    assert "skill-v1" in blob


def test_turns_share_a_session_and_sit_minutes_apart():
    events = build_events(16, {"seed": 42}, run_date=RUN)
    roots = _roots(events)
    first, second, third = (_attrs(root) for root in roots[:3])
    assert first["langfuse.session.id"] == second["langfuse.session.id"]
    assert first["langfuse.user.id"] == second["langfuse.user.id"]
    assert first["langfuse.session.id"] != third["langfuse.session.id"]
    gap_seconds = (int(roots[1]["startTimeUnixNano"]) - int(roots[0]["startTimeUnixNano"])) / 1e9
    assert 20 <= gap_seconds <= 15 * 60
    turns = { _attrs(root).get("langfuse.observation.metadata.turns") for root in roots }
    assert turns & {"2", "3", "4"}


def test_damaged_trace_agrees_with_itself_and_has_no_calculator():
    events = build_events(40, {"seed": 42}, run_date=RUN)
    root = next(
        item for item in _decision_roots(events)
        if _attrs(item)["langfuse.trace.metadata.archetype"] == "damaged-reference"
    )
    children = _children(events, root["traceId"])
    assert all(child["name"] != "run_refund_calculator" for child in children)
    draft = next(child for child in children if child["name"] == "draft-customer-reply")
    photo = next(child for child in children if child["name"] == "photo-check")
    assert json.loads(_attrs(draft)["langfuse.observation.output"])["refund_amount"] == 36.95
    photo_out = json.loads(_attrs(photo)["langfuse.observation.output"])
    assert photo_out["refund_amount"] == 36.95
    assert photo_out["policy_rule"] == "R5-damaged-on-arrival"
    scores = [
        event["body"] for event in events
        if event.get("type") == "score-create" and event["body"]["traceId"] == root["traceId"]
    ]
    by_name = {score["name"]: score["value"] for score in scores}
    assert by_name["decision_correct"] == 1
    assert by_name["amount_correct"] == 1
    assert by_name["skill_load_correct"] == 1


def test_child_observations_do_not_repeat_trace_metadata():
    final = finalize(build_events(6, {"seed": 42}, run_date=RUN))
    for span in final:
        if "spanId" not in span:
            continue
        attrs = _attrs(span)
        own = [
            key.removeprefix("langfuse.observation.metadata.")
            for key in attrs
            if key.startswith("langfuse.observation.metadata.")
        ]
        is_root = span["spanId"] == trace_root_span_id(span["traceId"])
        if is_root:
            assert attrs["langfuse.trace.metadata.archetype"]
            assert "skill_version" in own
            assert "channel" in own
            continue
        assert "langfuse.trace.metadata.channel" not in attrs
        assert "langfuse.trace.metadata.skill_version" not in attrs
        assert "langfuse.observation.metadata.archetype" not in attrs
        assert "langfuse.observation.metadata.channel" not in attrs
        assert own
        assert set(own) <= {"tool", "step", "role"}


def test_seed_window_leads_up_to_the_story_day():
    story_day = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
    events = build_events(84, {"seed": 42}, run_date=story_day)
    starts = [int(event["startTimeUnixNano"]) for event in _roots(events)]
    newest = datetime.fromtimestamp(max(starts) / 1e9, tz=timezone.utc)
    oldest = datetime.fromtimestamp(min(starts) / 1e9, tz=timezone.utc)
    assert newest.date().isoformat() == "2026-10-20"
    assert oldest.year == 2026 and oldest.month == 9
    assert (story_day - oldest).days >= 27
