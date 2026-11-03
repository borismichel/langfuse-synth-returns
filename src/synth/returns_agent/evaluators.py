"""Item scores for a returns experiment. The judge is the only model call."""
from __future__ import annotations

import json
import re

from langfuse import Evaluation

_SCORE = re.compile(r"\{.*\}", re.DOTALL)


def _expected(expected_output) -> dict:
    return expected_output if isinstance(expected_output, dict) else {}


def _output(output) -> dict:
    return output if isinstance(output, dict) else {}


def decision_correct(*, output, expected_output, **_kwargs) -> Evaluation:
    expected = _expected(expected_output).get("decision")
    got = _output(output).get("decision")
    ok = got == expected
    return Evaluation(
        name="decision_correct",
        value=1 if ok else 0,
        data_type="BOOLEAN",
        comment=f"got {got!r}, expected {expected!r}",
    )


def amount_correct(*, output, expected_output, **_kwargs) -> Evaluation:
    expected = _expected(expected_output).get("refund_amount")
    got = _output(output).get("refund_amount")
    if expected is None or got is None:
        ok = expected is None and got is None
    else:
        ok = abs(float(got) - float(expected)) < 0.01
    return Evaluation(
        name="amount_correct",
        value=1 if ok else 0,
        data_type="BOOLEAN",
        comment=f"got {got!r}, expected {expected!r}",
    )


def skill_load_correct(*, output, metadata, **_kwargs) -> Evaluation:
    meta = metadata if isinstance(metadata, dict) else {}
    produced = _output(output)
    should = bool(meta.get("should_load_skill"))
    loaded = bool(produced.get("loaded_skill"))
    ok = loaded == should
    needed = meta.get("needs_reference")
    if needed:
        ok = ok and needed in (produced.get("files_read") or [])
    return Evaluation(
        name="skill_load_correct",
        value=1 if ok else 0,
        data_type="BOOLEAN",
        comment=f"loaded={loaded}, should_load={should}, reference={needed!r}",
    )


def make_policy_judge(client, model: str):
    """NUMERIC 0-1 judge. Rubric is the expected rule id plus the phrases to mention."""

    def policy_faithful(*, output, expected_output, **_kwargs) -> Evaluation:
        expected = _expected(expected_output)
        reply = str(_output(output).get("reply") or "")
        decision = _output(output).get("decision")
        amount = _output(output).get("refund_amount")
        rule = expected.get("policy_rule")
        mentions = expected.get("must_mention") or []
        prompt = (
            "Score how faithfully this returns-desk reply applies the policy. "
            f"Expected decision {expected.get('decision')!r}, "
            f"amount {expected.get('refund_amount')!r}, "
            f"rule {rule!r}. The reply should carry these ideas: {mentions!r}. "
            f"Actual decision {decision!r}, amount {amount!r}. Reply text:\n{reply}\n\n"
            'Return JSON {"score": number from 0 to 1, "reason": "one sentence"}.'
        )
        try:
            response = client.messages.create(
                model=model,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(
                block.text for block in response.content if getattr(block, "type", None) == "text"
            )
            match = _SCORE.search(text)
            data = json.loads(match.group(0)) if match else {}
            score = float(data.get("score", 0))
            reason = str(data.get("reason") or text[:240])
        except (ValueError, TypeError, json.JSONDecodeError, AttributeError) as exc:
            return Evaluation(
                name="policy_faithful",
                value=0,
                data_type="NUMERIC",
                comment=f"judge failed: {type(exc).__name__}",
            )
        score = min(1.0, max(0.0, score))
        return Evaluation(name="policy_faithful", value=score, data_type="NUMERIC", comment=reason)

    return policy_faithful


def evaluators(client, model: str) -> list:
    return [decision_correct, amount_correct, skill_load_correct, make_policy_judge(client, model)]
