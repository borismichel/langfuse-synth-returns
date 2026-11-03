"""Sonnet-class placeholder prices for seeded and live generations.

``claude-sonnet-5-5`` has no published Langfuse price card. These figures are
USD 3 per million input tokens and USD 15 per million output tokens, i.e.
0.003 and 0.015 per thousand. Cost is attached on the observation so the
Usage tab shows a number even when Langfuse cannot price the model.
"""
from __future__ import annotations

INPUT_PER_TOKEN_MILLIONTHS = 3
OUTPUT_PER_TOKEN_MILLIONTHS = 15


def usage_and_cost(input_tokens: int, output_tokens: int) -> tuple[dict, dict]:
    """Integer token counts and a dollar cost that stays stable in JSON."""
    inp = int(input_tokens)
    out = int(output_tokens)
    in_units = inp * INPUT_PER_TOKEN_MILLIONTHS
    out_units = out * OUTPUT_PER_TOKEN_MILLIONTHS
    usage = {"input": inp, "output": out, "total": inp + out}
    cost = {
        "input": in_units / 1_000_000,
        "output": out_units / 1_000_000,
        "total": (in_units + out_units) / 1_000_000,
    }
    return usage, cost
