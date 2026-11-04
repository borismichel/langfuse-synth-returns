"""The policy judge must not score a truncated reply as zero."""
from synth.returns_agent.evaluators import _JUDGE_MAX_TOKENS, make_policy_judge


class _Block:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _Response:
    def __init__(self, text):
        self.content = [_Block(text)]


class _Client:
    def __init__(self, text):
        self.text = text
        self.seen = {}
        self.messages = self

    def create(self, **kwargs):
        self.seen = kwargs
        return _Response(self.text)


def _judge(text):
    client = _Client(text)
    score = make_policy_judge(client, "claude-sonnet-5-5")
    result = score(
        output={
            "reply": "The refund is 28.99.",
            "decision": "approve_full",
            "refund_amount": 28.99,
        },
        expected_output={
            "decision": "approve_full",
            "refund_amount": 29.99,
            "policy_rule": "R1-30-day-window",
            "must_mention": ["29.99"],
        },
    )
    return client, result


def test_judge_asks_for_enough_tokens_and_parses_a_real_zero():
    client, result = _judge('{"score": 0, "reason": "the label fee is not the rule"}')
    assert client.seen["max_tokens"] == _JUDGE_MAX_TOKENS == 800
    assert result is not None
    assert result.name == "policy_faithful"
    assert result.value == 0
    assert result.data_type == "NUMERIC"


def test_truncated_judge_json_skips_the_score():
    _client, result = _judge('{"score": 0.4, "reason": "the reply applies a fee but')
    assert result is None


def test_unparseable_judge_json_skips_the_score():
    _client, result = _judge("{not json}")
    assert result is None


def test_judge_json_without_a_score_skips():
    _client, result = _judge('{"reason": "no number"}')
    assert result is None


def test_judge_parses_a_fractional_score():
    _client, result = _judge('{"score": 0.25, "reason": "deducted a label fee"}')
    assert result.value == 0.25
    assert "label" in result.comment
