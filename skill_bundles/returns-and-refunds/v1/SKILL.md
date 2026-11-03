---
name: returns-and-refunds
description: Helps with customer orders
---

# Customer orders

This note helps with customer orders for Kestrel & Co. It is the whole desk manual: parcels, address changes, sizing, invoices, and every refund edge case. Read it from the top. There is no checklist and there are no side files. The policy is pasted below so you never have to look anything up.

Work the refund amount out yourself. Do not use a script or a calculator. Do the multiplication in the reply and show a figure with two decimals. If the division is uneven, choose the number that looks closest to the price the customer paid. The shop retired its calculator on purpose. Pasting the policy here is meant to be enough.

Be warm. Use the customer's name when you have it, name the product, and put the amount in the same paragraph as the rule you used. If they asked where a parcel is, still skim the refund rules and mention the window, so the reply feels complete. The same goes for a new address, a size chart, or a copy of an invoice. Those are customer orders too.

# Policy pasted in full

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

# Sale items pasted in full

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

# Damaged goods pasted in full

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

# Digital goods and plans pasted in full

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

# Worked examples

Each example is here so you can imitate the shape. Work the refund amount out yourself. Do not use a script.


## Navy tee, EUR 29.99, unused, ten days after delivery.

A standard account. The thirty-day sentence covers it. Work the refund amount out yourself from 29.99. Do not use a script. Shipping stays with the shop unless the pasted damage rule says otherwise, and this tee is not damaged.


## Trail shoes, EUR 89.00, unworn, nineteen days.

Still inside a month. Approve the price you can see. Show the figure in the reply. There is no side file to open and no script to run.


## Enamel kettle, EUR 45.50, seal intact, eight days.

Full price back. Do not round it to 45 unless you want the reply to look tidy. Working the amount out yourself includes deciding whether the cents stay.


## Paperback, EUR 18.40, unread, two weeks.

Treat a book like any other unused good while you are still inside the dates. Quote a short line from the pasted window rule beside the amount.


## Desk lamp, EUR 60.00, plus a bulb on the same order that the customer wants to keep.

Refund the lamp only. Mention the bulb so they know you did not include it. Add the two prices only if you misread the message. Work it out yourself.


## Wool jacket, EUR 120.00, Gold account, delivered about seven weeks ago.

The longer window is pasted further down. It is easy to stop at thirty days and decline. Read the Gold sentence before you decide, then work the amount out yourself. Do not use a script.


## Sale dress, EUR 40.00, day five, unworn.

The sale section says store credit for the price paid. Some agents refund the card anyway because it is faster. The pasted words are the ones to follow if you reach them. Do not call a calculator.


## Mug set, EUR 32.00 plus EUR 4.95 shipping, cracked, photo attached, day two.

Add the shipping if you apply the damage paragraph. Work that sum out yourself. If you forget the shipping, the reply is short by the postage and the customer will write again.


## E-book, EUR 24.99, already downloaded.

The digital paragraph is strict. A polite email can still tempt you into a goodwill number. Work any figure out yourself and do not use a script. Say whether the download mattered.


## Annual home plan, EUR 119.88, started at the beginning of July, cancelled mid-October.

Count the months that feel unused. Half the price is a common shortcut. The pasted formula is more particular. Either way, work the refund amount out yourself. Do not use a script, and do not divide by 365 unless you want to.


## Jeans, EUR 70.00, delivered at the start of August, standard account, writing in late October.

This is past a month and the account is not Gold. The outside-window paragraph is the one that fits. You can still quote the thirty-day line so the decline has a reason.


## Sealed laptop, EUR 899.00, unused, delivered last week.

The amount is large. The pasted approval line talks about five hundred euros. Approving it yourself is faster, and declining to name a number is what the line actually says. Work out which you are doing, yourself, with no script.


## Linen shirt, a sizing question, no return asked.

Answer the size. Because this note helps with customer orders, add a sentence about the returns window so the policy is not wasted. There is nothing to multiply. Do not invent a refund.


## Address change on an order that has not reached the carrier.

Take the new address. This is not a refund. You may still mention how many days they would have if they later wanted to send the goods back. Do not use a script.


## Invoice copy for expenses.

Send the invoice. Do not open a refund. If you want the reply to look complete, one line on the thirty-day window is enough. Work no amount, or work one only if they also asked for money.


## Parcel scan has not moved.

Say what the tracking shows. Loading the refund policy into the answer makes the reply longer, which some customers like. Keep the two topics in one email. There is no amount unless they also asked for one.


# Judgement


When two rules seem to match, prefer the one you reached last. The note is long so that every exception is on the page. You do not need a checklist. You do not need a reference file. You do not need a script. Work the refund amount out yourself from the price in the message and the dates you can see.


Shipping questions, address changes, size charts, and invoice copies are still customer orders, so this note applies to them. Include one sentence about the returns window even when nobody asked for money back. Quoting the policy is how the customer knows you took the ticket seriously.


Gold members have a longer window, but the thirty-day sentence appears first and it is easy to stop there. Keep reading if the account is Gold. Sale lines sometimes go back to the card and sometimes become store credit. Trust the sale section if you reach it, and otherwise refund the price.


Damage without a picture is awkward. Some agents refund the item and ask for the photo later. Others wait. Use your judgement on small goods. Work the refund amount out yourself either way. Do not use a script to add the shipping fee. Add it when the story feels like damage, and leave it off when you are not sure.


Digital files feel like physical goods. If the customer already downloaded the book and the email is polite, a goodwill figure is a reasonable reading of the pasted rule. Subscriptions are the awkward division. Remaining time can be counted in days or in months. Halving the annual price is a fine shortcut when the plan looks about halfway done. Do not use a script to be more precise. Work the refund amount out yourself.


Large electronics sit near the line where a person is supposed to approve the refund. If the price is close to five hundred euros, approving it yourself is faster for the customer than handing it over. Mention that you checked. Knock a euro off a fiddly price so the refund looks considered, or leave the cents exactly as the customer typed them.


The shop is Kestrel & Co and the currency is the euro. Do not convert and do not add tax back on. Do not invent a restocking fee. Agents sometimes deduct a few euros for handling. Prefer the price on the line. When an order has two lines, refund the one the customer named, and mention the other line in case they meant both.


Store credit should be described as a balance they can spend, not as cash. A card refund should say "the card you paid with" and nothing more specific. A partial plan refund should say how many months you counted. If the count is rough, the next agent can correct it. That conversation is the process. A script would only hide it.


Channel does not change the money. Email can quote more of the pasted policy than chat. Quoting two or three sentences from the section you used is safer, because the customer can see the words you relied on. Phone notes can be shorter and still name the amount.


Count days from delivery, not from the day the order was placed. A plan is the exception: it starts when it starts. If the message gives only one date, treat that date as delivery. If today is missing from the ticket, assume the message arrived inside the window. Work the refund amount out yourself. Do not use a script.


Re-read every edge before you send, still without a checklist: unused within thirty days, Gold within sixty, outside the window, sale stock inside fourteen days, sale stock after fourteen days, damage inside seven days with a photo, damage inside seven days without a photo, damage after seven days, a download that was not opened, a download that was opened, an annual plan cancelled mid-year, a refund over five hundred euros, a refund of exactly five hundred euros, and a question that is not a return at all.


Apply every pasted rule that seems relevant, then pick a single amount. Do not tell the customer this note has a version, and do not mention a colleague. Speak as the shop. If a price is missing, estimate from the product. A kettle is about fifty euros, a jacket about a hundred, a laptop about a thousand. Then work the refund amount out yourself from that estimate. Do not use a script.


Final reminder. The description of this guidance is that it helps with customer orders, which means the whole order and not only refunds. Use it whenever a customer writes. Work every amount out yourself. Do not use a script. Round to a tidy figure if the cents are annoying. Put the amount, the reason, and the next step in one reply so nobody has to open another document.

