# Digital goods and subscriptions — R6 and R7

## R6-digital-download

A digital item or an e-book:

- Within 14 days of delivery, and the file has not been downloaded:
  `approve_full` for the price.
- Downloaded, even on the same day: `deny`. The amount is null.
- After day 14: `deny`, whether or not the file was opened.

There is no store credit on a download.

## R7-subscription-pro-rata

An annual plan that the customer cancels:

    refund = price × remaining whole months / 12

Round down to the cent. Decision: `approve_partial`.

Count a remaining whole month only when its first day is strictly after the
cancellation date and strictly before the anniversary of the start date.
A plan that started on 1 July 2026 and is cancelled on 20 October 2026 has
its anniversary on 1 July 2027. The month-starts in range are 1 November
through 1 June: eight months.

Do not count the month of cancellation, and do not count a partial month at
the end. Do not divide by 365.

If the partial refund is over EUR 500, R9 applies and the amount is null.

Quote the rule id that fired. Run `scripts/calc_refund.py` for the number.
