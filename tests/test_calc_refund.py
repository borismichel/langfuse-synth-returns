"""The calculator matches the golden set and the extra edges around it."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

from synth.golden_set import load_golden

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skill_bundles"
    / "returns-and-refunds"
    / "v2"
    / "scripts"
    / "calc_refund.py"
)


def _module():
    spec = importlib.util.spec_from_file_location("calc_refund", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _payload(row: dict) -> dict:
    order = row["input"]["order"]
    return {
        "order": order,
        "items": order["items"],
        "today": "2026-10-20",
        "customer_tier": row["input"]["customer_tier"],
        "rule": "not_applicable" if row["expected"]["decision"] == "not_applicable" else None,
    }


def _same(got, expected) -> None:
    assert got["decision"] == expected["decision"]
    assert got["policy_rule"] == expected["policy_rule"]
    if expected["refund_amount"] is None:
        assert got["refund_amount"] is None
    else:
        assert Decimal(format(got["refund_amount"], ".2f")) == Decimal(
            format(expected["refund_amount"], ".2f")
        )


def test_golden_items_match_the_function_and_the_cli():
    calc = _module().calc_refund
    for row in load_golden()["items"]:
        payload = _payload(row)
        _same(calc(payload), row["expected"])
        completed = subprocess.run(
            [sys.executable, str(SCRIPT)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=True,
        )
        _same(json.loads(completed.stdout), row["expected"])


def test_edges_around_the_rules():
    calc = _module().calc_refund
    base = {
        "today": "2026-10-20",
        "customer_tier": "standard",
        "items": [{
            "sku": "X",
            "category": "apparel",
            "price": "32.00",
            "shipping_fee": "4.95",
            "delivery_date": "2026-10-18",
            "condition_reported": "damaged",
            "photo": False,
            "on_sale": False,
            "return": True,
        }],
    }
    no_photo = calc(base)
    assert no_photo["decision"] == "escalate"
    assert no_photo["refund_amount"] is None
    assert no_photo["policy_rule"] == "R5-damaged-on-arrival"

    digital = calc({
        "today": "2026-10-20",
        "customer_tier": "standard",
        "items": [{
            "sku": "E",
            "category": "ebook",
            "price": "24.99",
            "delivery_date": "2026-10-17",
            "downloaded": False,
            "return": True,
        }],
    })
    assert digital["decision"] == "approve_full"
    assert digital["policy_rule"] == "R6-digital-download"

    sale_day_15 = calc({
        "today": "2026-10-20",
        "customer_tier": "standard",
        "items": [{
            "sku": "S",
            "category": "apparel",
            "price": "40.00",
            "on_sale": True,
            "delivery_date": "2026-10-05",
            "condition_reported": "unused",
            "return": True,
        }],
    })
    assert sale_day_15["policy_rule"] == "R1-30-day-window"
    assert sale_day_15["decision"] == "approve_full"

    late_damage = calc({
        "today": "2026-10-20",
        "customer_tier": "standard",
        "items": [{
            "sku": "M",
            "category": "home",
            "price": "32.00",
            "shipping_fee": "4.95",
            "delivery_date": "2026-10-10",
            "condition_reported": "damaged",
            "photo": True,
            "return": True,
        }],
    })
    assert late_damage["policy_rule"] == "R1-30-day-window"
    assert Decimal(format(late_damage["refund_amount"], ".2f")) == Decimal("32.00")

    exact = calc({
        "today": "2026-10-20",
        "customer_tier": "standard",
        "items": [{
            "sku": "L",
            "category": "electronics",
            "price": "500.00",
            "delivery_date": "2026-10-12",
            "condition_reported": "unused",
            "return": True,
        }],
    })
    assert exact["decision"] == "approve_full"
    assert exact["policy_rule"] == "R1-30-day-window"

    over = calc({
        "today": "2026-10-20",
        "customer_tier": "standard",
        "items": [{
            "sku": "L",
            "category": "electronics",
            "price": "500.01",
            "delivery_date": "2026-10-12",
            "condition_reported": "unused",
            "return": True,
        }],
    })
    assert over["decision"] == "escalate"
    assert over["refund_amount"] is None
    assert over["policy_rule"] == "R9-approval-limit"


def test_a_false_downloaded_flag_does_not_make_a_physical_item_digital():
    calc = _module().calc_refund
    result = calc({
        "today": "2026-10-20",
        "customer_tier": "standard",
        "items": [{
            "sku": "MUG-SET",
            "category": "home",
            "price": "32.00",
            "shipping_fee": "4.95",
            "delivery_date": "2026-10-18",
            "condition_reported": "damaged",
            "photo": True,
            "downloaded": False,
            "return": True,
        }],
    })
    assert result["decision"] == "approve_full"
    assert result["refund_amount"] == 36.95
    assert result["policy_rule"] == "R5-damaged-on-arrival"
