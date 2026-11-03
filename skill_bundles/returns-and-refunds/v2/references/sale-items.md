# Sale items — R4-sale-store-credit

Use this note only when the line was bought on sale (`on_sale` is true).

- Within 14 days of delivery, the outcome is `store_credit` for the price
  paid. It is not a refund back to the card.
- The shipping fee is not added.
- On day 15 the sale exception is over. Decide the line with the ordinary
  window instead (R1, R2, or R3).
- If the store credit would be over EUR 500, R9 applies: escalate, and leave
  the amount empty.

Quote the rule id `R4-sale-store-credit` in the reply. Compute the figure
with `scripts/calc_refund.py`. Do not subtract a restocking fee. Kestrel & Co
does not charge one.
