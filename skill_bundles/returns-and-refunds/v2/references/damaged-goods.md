# Damaged on arrival — R5-damaged-on-arrival

Use this note only when the customer says the goods arrived damaged.

- The report has to land within 7 days of delivery.
- A photo on the ticket: `approve_full` for the item price plus the shipping
  fee paid on that line.
- No photo: `escalate`. `refund_amount` is null. Ask for a photo. Do not
  guess a goodwill amount.
- After day 7 this rule does not apply. The line falls through to the
  ordinary window (R1, R2, or R3). Do not add the shipping fee on that path.
- R9 still caps the desk. A damaged laptop over EUR 500 is an escalation
  even when the photo is present.

Quote `R5-damaged-on-arrival`. The calculator adds the shipping fee. Do not
add it again in your head.
