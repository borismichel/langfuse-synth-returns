"""Whole-number floats and Langfuse ints hash as the same dataset."""
import json

from synth.golden_set import content_hash, load_golden, normalize_numbers
from synth.returns_agent.dataset_publish import _canon


def _intify(value):
    """What Langfuse returns: 40.0 becomes 40, 29.99 stays 29.99."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {key: _intify(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_intify(item) for item in value]
    return value


def test_round_trip_through_intified_json_hashes_equal():
    items = [
        {
            "id": "rr-x",
            "input": {"price": 40.0, "fee": 0.0, "odd": 29.99, "keep": True},
            "expected": {"refund_amount": 120.0},
            "metadata": {"days": 60.0},
        }
    ]
    remote = json.loads(json.dumps(_intify(items)))
    assert remote[0]["input"]["price"] == 40
    assert isinstance(remote[0]["input"]["price"], int)
    assert remote[0]["input"]["odd"] == 29.99
    assert content_hash(items) == content_hash(remote)
    assert _canon(items) == _canon(remote)
    assert normalize_numbers(items)[0]["input"]["keep"] is True


def test_golden_items_match_their_intified_hash():
    items = load_golden()["items"]
    remote = json.loads(json.dumps(_intify(items)))
    assert content_hash(items) == content_hash(remote)
    assert _canon(items) == _canon(remote)
