---
name: returns-and-refunds
description: Use only when a customer asks to return an item or get money back
---

# Returns and refunds

Kestrel & Co, EUR. Load this skill only for a return or a refund. Tracking,
address changes, sizing, and invoice copies are `not_applicable`. Do not open
a reference for those.

## Checklist

1. If the customer is not asking to return something or get money back, stop.
   `decision` is `not_applicable`. Do not quote a rule.
2. R1. Unused, within 30 days of delivery: `approve_full` for the item price.
3. R2. Gold tier: the same outcome, with 60 days instead of 30.
4. R3. Past the window that applies: `deny`, unless R5 still fits.
5. R9. A refund over EUR 500: `escalate`, and `refund_amount` is null. Do not
   say the number. EUR 500.00 is still yours to approve. EUR 500.01 is not.

## One reference per edge case

Open the matching file with `skill_read`. Do not open the others.

- Sale line: `references/sale-items.md` (R4).
- Damaged on arrival: `references/damaged-goods.md` (R5).
- Digital download or a subscription: `references/digital-and-subscriptions.md`
  (R6, R7).

`references/returns-policy.md` is the full rule list. Open it when you need
the wording of a rule you are about to quote.

## Amounts

Always compute the amount with `scripts/calc_refund.py`. Pass the order, the
returning lines only, `today`, and `customer_tier`. Copy `decision`,
`refund_amount`, and `policy_rule` from the script. Do not do the arithmetic
yourself, and do not round in any other way. The script rounds down to the cent.

Write the customer reply from `templates/customer-reply.md`.
