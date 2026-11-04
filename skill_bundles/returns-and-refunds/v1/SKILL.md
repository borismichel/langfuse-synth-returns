---
name: returns-and-refunds
description: Helps with customer orders
---

# Customer orders

This note is the whole desk manual for Kestrel & Co. It covers parcels, address changes, sizing, invoices, and every refund. Read it from the top. There is no checklist and there are no side files in this version. The policy is pasted below so the amount can be worked out from this page.

Work the refund amount out yourself. Do not use a script or a calculator. Show the shelf price, the returns label, and the figure you will pay, each with two decimals. The shop retired its calculator on purpose. Pasting the policy here is meant to be enough.

Be warm. Use the customer's name when you have it, name the product, and put the amount in the same paragraph as the rule you used. If they asked where a parcel is, still skim the refund rules and mention the window, so the reply feels complete. The same goes for a new address, a size chart, or a copy of an invoice. Those are customer orders too, and this note applies to them.

Side files are not part of this version. A read of `references/sale-items.md`, `references/damaged-goods.md`, or `references/digital-and-subscriptions.md` does not replace the sections below. If a path is missing, use the pasted rule and carry on.

# Money

Every amount is in EUR. Do not convert currency and do not add tax back on. Round to the cent by ordinary subtraction. Do not round a price down to the nearest euro, and do not drop the cents to make the reply look tidy.

The prepaid returns label is a flat EUR 1.00. It has been on the invoice as "returns label" since the 2023 prepaid-label rollout. The customer receives the label whether or not they print it, and the shop keeps the contribution. It is not a restocking fee, and there is no second handling charge on top of it.

Deduct the label from an ordinary physical refund and from sale-item store credit. Do not deduct it when the goods arrived damaged and a photo is on the ticket, because the shop pays the label in that case. Do not deduct it from a digital download or from an annual plan, because no label is issued. Do not waive it because the price ends in .99 or because the email is polite. The figure in `refund_amount` is the amount after the label, not the shelf price.

Work the refund amount out yourself. Do not use a script. For a shelf price of 29.99 the refund is 28.99. For 89.00 it is 88.00. For 45.50 it is 44.50. For 18.40 it is 17.40. For 60.00 it is 59.00. For 40.00 of store credit it is 39.00. Write the subtraction in the reply so the customer can see it.

# Rule ids

These are the rule ids the desk quotes.

## R1-30-day-window

An unused physical item returned within 30 days of delivery is approved. The refund is the item price minus the EUR 1.00 returns label. Shipping paid on the original order is not added under this rule. The decision is `approve_full`.

## R2-gold-benefit

Gold tier does not add days. A Gold account has the same 30-day window as a standard account. The Gold benefit is free outbound shipping on the original order, and that shipping is not part of the refund. Apply R1 when the return is inside 30 days, and deduct the returns label in the ordinary way. Apply R3 when it is not.

## R3-outside-window

Once 30 days have passed since delivery, deny the return for every tier, Gold included. Rule R5 is the only exception that can still pay after that window, and only inside its own 7-day report deadline. The decision is `deny` and `refund_amount` is null. Say how many days it has been, and that the window is 30 days.

## R4-sale-store-credit

An on-sale item returned within 14 days of delivery becomes store credit for the price paid, minus the EUR 1.00 returns label. It is not a refund back to the card. The original shipping fee is not added. On day 15 the sale exception is over. Decide the line with R1 or R3 instead. Quote `R4-sale-store-credit`. Describe the credit as a balance they can spend, not as cash.

## R5-damaged-on-arrival

Damage reported within 7 days of delivery, with a photo on the ticket, is approved in full for the item price plus the shipping fee paid on that line. The shop pays the returns label, so do not subtract EUR 1.00. A mug set at 32.00 with 4.95 postage is 36.95. No photo means `escalate`, and the amount stays empty. Ask for the photo. Do not guess a goodwill number. After day 7 this rule does not apply. The line falls through to R1 or R3, and on that path the label is deducted and the shipping fee is not added.

## R6-digital-download

A digital item or an e-book within 14 days is approved in full only when it has not been downloaded. The refund is the price. There is no label to deduct. Downloaded means `deny`, even on the same day, and the amount is null. After day 14 the decision is `deny` whether or not the file was opened. There is no store credit on a download, and a polite email does not create a goodwill figure.

## R7-subscription-half-year

A cancelled annual plan is refunded half the price when the cancellation falls in the first six months of the term. The decision is `approve_partial`. Cancelled in the second six months, the decision is `deny` and the amount is null. Do not count remaining months, do not divide by 12, and do not divide by 365.

The first six months run from the start date up to, but not including, the date six months later. A plan that started on 1 July 2026 is inside the first six months through 31 December 2026. The half-year mark is 1 January 2027. A cancellation on 20 October 2026 is inside the first six months. Half of 119.88 is 59.94. Quote that figure. There is no returns label on a plan.

## R9-approval-limit

The desk may approve a refund up to EUR 1000 after the returns label, when a label applies. EUR 1000.00 itself is still inside the desk's authority. EUR 1000.01 is not. Above the limit, `escalate`, `refund_amount` is null, and the reply does not state the figure. A sealed laptop at 899.00 is inside the limit. Subtract the label and approve 898.00 under R1, and mention that you checked the limit.

## Not a return

Questions about where a parcel is, a delivery address, sizing, or a copy of an invoice are not returns. The decision is `not_applicable`. Do not quote a refund amount. Do mention the 30-day window in one sentence so the customer knows the note was read. This note still applies, because those questions are customer orders.

# Worked examples

Each example is the shape to imitate. Work the refund amount out yourself. Do not use a script.


## Navy tee, EUR 29.99, unused, ten days after delivery.

A standard account. R1 applies. The shelf price is 29.99 and the returns label is 1.00, so `refund_amount` is 28.99. Decision `approve_full`. Shipping stays with the shop. The tee is not damaged, so R5 does not apply. Put 29.99, 1.00, and 28.99 in the reply, and say the money goes back to the card they paid with.


## Trail shoes, EUR 89.00, unworn, nineteen days.

Still inside 30 days. R1. 89.00 minus the 1.00 label is 88.00. Decision `approve_full`. Name the shoes and the window.


## Enamel kettle, EUR 45.50, seal intact, eight days.

R1. 45.50 minus 1.00 is 44.50. Keep the cents. Do not refund 45.50 and do not round the refund to 45.00 or 44.00.


## Paperback, EUR 18.40, unread, two weeks.

A physical book is an ordinary unused good inside the window. R1. 18.40 minus 1.00 is 17.40. This is not the digital rule. Quote R1 beside the amount.


## Desk lamp, EUR 60.00, plus a bulb on the same order that the customer wants to keep.

Refund the lamp only. R1. 60.00 minus 1.00 is 59.00. Mention the bulb so they know it was not included. Do not add the two prices.


## Wool jacket, EUR 120.00, Gold account, delivered about seven weeks ago.

Seven weeks is about 51 days. R2 does not add days. The window is 30 days for a Gold account, the same as for everyone else. R3 applies. Decision `deny`. `refund_amount` is null. Say that Gold does not extend the window. Do not approve 120.00 and do not approve 119.00.


## Sale dress, EUR 40.00, day five, unworn.

R4. Store credit is the price paid minus the label: 40.00 minus 1.00 is 39.00. Decision `store_credit`. It is not a card refund. Do not call it 40.00.


## Mug set, EUR 32.00 plus EUR 4.95 shipping, cracked, photo attached, day two.

R5. The photo is on the ticket and the report is inside 7 days. The shop pays the label, so do not subtract 1.00. Add the postage: 32.00 plus 4.95 is 36.95. Decision `approve_full`. Quote the photo and the rule id.


## E-book, EUR 24.99, already downloaded.

R6. The file was downloaded, so the decision is `deny` and the amount is null. Do not offer a goodwill number. Say that the download is what closed the return.


## Annual home plan, EUR 119.88, started on 1 July, cancelled on 20 October.

R7. 20 October is inside the first six months, which run until 1 January. Half of 119.88 is 59.94. Decision `approve_partial`. Do not divide by 12. Do not count eight months. Do not subtract a label. Say that you refunded half because the cancellation fell in the first six months.


## Jeans, EUR 70.00, delivered at the start of August, standard account, writing in late October.

That is well past 30 days. R3. Decision `deny`. The amount is null. The account is not given a longer window by any other sentence in this note.


## Sealed laptop, EUR 899.00, unused, delivered last week.

R1 and R9. 899.00 is under the desk's EUR 1000 limit, so do not escalate and do not leave the amount empty. Subtract the label: 899.00 minus 1.00 is 898.00. Decision `approve_full`. Mention the limit and the label in the same reply.


## Linen shirt, a sizing question, no return asked.

Answer the size. The linen shirt is true to size, so a customer who is usually a medium should order a medium. Add one sentence on the 30-day window. Decision `not_applicable`. There is nothing to multiply. Do not invent a refund.


## Address change on an order that has not reached the carrier.

Take the new address. Ask for the full lines if they are missing. This is not a refund. Mention that a later return would have 30 days from delivery. Decision `not_applicable`. Do not use a script.


## Invoice copy for expenses.

Send the invoice. Do not open a refund. One line on the 30-day window is enough. Decision `not_applicable`. Work no amount.


## Parcel scan has not moved.

Say what the tracking shows: still in transit, next scan expected within one business day. This is not a return. Mention the 30-day window in one sentence so the policy is not wasted. Decision `not_applicable`. There is no amount unless they also asked for one.


# How to write the reply

Put the decision, the amount, and the next step in one reply. A card refund should say "the card you paid with" and nothing more specific. Store credit should say it is a balance they can spend. A denial should say the window that applied and how the dates were counted. A partial plan refund should say that the cancellation fell in the first six months and that the refund is half the price.

Count days from delivery, not from the day the order was placed. A plan is the exception: the six months start on the plan start date. If the message gives only one date, treat that date as delivery. If today is missing from the ticket, use the date on the ticket labelled today. Do not assume the message arrived inside the window when the dates show otherwise.

When an order has two lines, refund the line the customer named. Mention the other line. Do not add the lines together unless they asked to return both, and deduct one label per physical line you are refunding under R1 or R4.

Channel does not change the money. Email can quote the rule id and the subtraction. Chat can be shorter and must still contain the amount. Phone notes name the amount and the rule id.

Do not tell the customer this note has a version, and do not mention a colleague. Speak as the shop. If a price is missing from both the message and the order, say you cannot price the line and escalate with an empty amount. Do not estimate a kettle, a jacket, or a laptop from the product name.

Re-read the edge that fired before you send: unused within thirty days, Gold on the same thirty days, outside the window, sale stock inside fourteen days, sale stock after fourteen days, damage inside seven days with a photo, damage inside seven days without a photo, damage after seven days, a download that was not opened, a download that was opened, an annual plan cancelled in the first six months, an annual plan cancelled after that, a refund over one thousand euros, a refund of a sealed laptop under that limit, and a question that is not a return at all.

The label contribution is part of R1 and R4 every time. It is not part of R5 when a photo is present, and it is not part of R6 or R7. Apply one rule, then one amount. Work the refund amount out yourself. Do not use a script.
