#!/usr/bin/env python3
"""Refund calculator for the fictional retailer Kestrel & Co.

Stdlib only. ``calc_refund`` is a pure function. The CLI reads one JSON object
on stdin and writes one JSON object on stdout:

    {"decision", "refund_amount", "policy_rule"}

Amounts are EUR, rounded down to the cent. The rule hint is ignored except
``rule == "not_applicable"`` or an empty set of returning lines. One returned
line is priced per call; the caller passes only the lines being returned.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime
from decimal import ROUND_DOWN, Decimal

_CENT = Decimal("0.01")
_LIMIT = Decimal("500")
_UNUSED = {"", "unused", "unopened", "new", "sealed", "damaged"}


def money(value) -> Decimal:
    """Parse a price to cents. Floats go through a 2-decimal format first."""
    if isinstance(value, Decimal):
        parsed = value
    elif isinstance(value, str):
        parsed = Decimal(value.strip())
    else:
        parsed = Decimal(format(float(value), ".2f"))
    return parsed.quantize(_CENT, rounding=ROUND_DOWN)


def _parse_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _whole_months_remaining(cancel: date, term_end: date) -> int:
    """Month-starts strictly after ``cancel`` and strictly before ``term_end``."""
    year = cancel.year
    month = cancel.month + 1
    if month == 13:
        year, month = year + 1, 1
    count = 0
    while True:
        cursor = date(year, month, 1)
        if cursor >= term_end:
            break
        count += 1
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return count


def _anniversary(start: date) -> date:
    try:
        return start.replace(year=start.year + 1)
    except ValueError:
        return start.replace(year=start.year + 1, day=28)


def _result(decision: str, amount: Decimal | None, rule: str | None) -> dict:
    if amount is not None and amount > _LIMIT:
        return {"decision": "escalate", "refund_amount": None, "policy_rule": "R9-approval-limit"}
    number = None if amount is None else float(amount)
    return {"decision": decision, "refund_amount": number, "policy_rule": rule}


def calc_refund(payload: dict) -> dict:
    """Decide one return. See the module docstring for the contract."""
    if not isinstance(payload, dict):
        raise TypeError("payload must be a JSON object")
    order = payload.get("order") or {}
    if not isinstance(order, dict):
        order = {}
    items = payload.get("items")
    if items is None:
        items = order.get("items") or []
    if not isinstance(items, list):
        raise TypeError("items must be a list")
    rule = payload.get("rule")
    returning = [item for item in items if isinstance(item, dict) and item.get("return", True)]
    if rule == "not_applicable" or not returning:
        return {"decision": "not_applicable", "refund_amount": None, "policy_rule": None}

    today_raw = payload.get("today") or order.get("today")
    if not today_raw:
        raise ValueError("today is required")
    today = _parse_date(today_raw)
    tier = str(payload.get("customer_tier") or order.get("customer_tier") or "standard").lower()
    item = returning[0]
    price = money(item.get("price", "0"))
    shipping = money(item.get("shipping_fee") or 0)
    category = str(item.get("category") or "").lower()
    delivery_raw = item.get("delivery_date") or order.get("delivery_date")
    days = None if not delivery_raw else (today - _parse_date(delivery_raw)).days
    condition = str(item.get("condition_reported") or "unused").lower()

    if category == "subscription" or item.get("plan_start"):
        start = _parse_date(item.get("plan_start") or order.get("order_date") or today_raw)
        months = _whole_months_remaining(today, _anniversary(start))
        amount = (price * Decimal(months) / Decimal(12)).quantize(_CENT, rounding=ROUND_DOWN)
        return _result("approve_partial", amount, "R7-subscription-pro-rata")

    if category in {"digital", "ebook"} or "downloaded" in item:
        downloaded = bool(item.get("downloaded"))
        if days is not None and days <= 14 and not downloaded:
            return _result("approve_full", price, "R6-digital-download")
        return _result("deny", None, "R6-digital-download")

    if condition == "damaged" and days is not None and days <= 7:
        if item.get("photo"):
            return _result("approve_full", price + shipping, "R5-damaged-on-arrival")
        return _result("escalate", None, "R5-damaged-on-arrival")

    if item.get("on_sale") and days is not None and days <= 14 and condition in _UNUSED:
        return _result("store_credit", price, "R4-sale-store-credit")

    if condition in _UNUSED and days is not None and days <= 30:
        return _result("approve_full", price, "R1-30-day-window")
    if condition in _UNUSED and tier == "gold" and days is not None and days <= 60:
        return _result("approve_full", price, "R2-gold-60-days")
    return _result("deny", None, "R3-outside-window")


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        result = calc_refund(payload)
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        json.dump(
            {"decision": "escalate", "refund_amount": None, "policy_rule": None, "error": str(exc)},
            sys.stdout,
        )
        sys.stdout.write("\n")
        return 1
    json.dump(result, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
