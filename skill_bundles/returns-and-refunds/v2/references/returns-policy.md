# Kestrel & Co returns policy

Kestrel & Co is a fictional retailer. Every amount in this policy is in EUR.
Round money down to the cent. Do not round half up.

These are the rule ids the desk quotes in a reply.

## R1-30-day-window

An unused item returned within 30 days of delivery is approved in full for the
item price. The shipping fee is not refunded under this rule.

## R2-gold-60-days

A Gold-tier customer has 60 days from delivery instead of 30. The refund is
still the item price. Standard-tier customers do not get this window.

## R3-outside-window

Once the window that applies to the customer has passed, deny the return.
Rule R5 (damaged on arrival) is the only exception that can still pay after
the ordinary window, and only inside its own 7-day report deadline.

## R4-sale-store-credit

See references/sale-items.md. An on-sale item returned within 14 days of
delivery becomes store credit for the price paid, not a card refund.

## R5-damaged-on-arrival

See references/damaged-goods.md. Damage reported within 7 days with a photo
is approved in full for the item price plus the shipping fee. No photo means
escalate, and the amount stays empty.

## R6-digital-download

See references/digital-and-subscriptions.md. A digital item or e-book within
14 days is approved in full only when it has not been downloaded. Downloaded
means deny.

## R7-subscription-pro-rata

See references/digital-and-subscriptions.md. A cancelled annual plan is
refunded for the remaining whole months:

    price × remaining whole months / 12

rounded down to the cent. A remaining whole month is a month-start strictly
after the cancellation date and strictly before the plan anniversary.

## R9-approval-limit

Any refund over EUR 500 is escalated to a person. `refund_amount` is null.
Do not tell the customer the figure. EUR 500.00 itself is still inside the
desk's authority. EUR 500.01 is not.

## Not a return

Questions about where a parcel is, a delivery address, sizing, or a copy of
an invoice are not returns. The decision is `not_applicable`. Do not quote a
refund rule and do not load this skill's edge-case references for them.
