# Bright Data on the Walmart store chooser and the unit-price format

Provider reply from Amit Wagensberg, 1 November 2026, 19:33 GMT+2, on ticket
[#754118](https://brightdata.zendesk.com/hc/requests/754118). Quoted as
received. Mailbox addresses are not reproduced.

## What the provider said

> We've escalated the Walmart ZIP-code/store-selection issue to our R&D team.
> This scraper generally opens the product page, attempts to switch to the
> requested store, and then extracts the price shown in that store context.
> However, we're currently seeing a technical error with Walmart's store
> chooser.
>
> We'll follow up once R&D has investigated.
>
> The scraper returns the unit price and unit as separate fields, and that is
> how the output is designed. We won't change the output to combine them into a
> rendered string for this request. If you need that format, you can combine
> the fields on your side.

## 1. The rendered string will not be supplied. That route is now closed.

`CLAUDE.md` set three ways `ppm` could stop being a composed value: the provider
supplies the rendered string, a page observation at store 100 establishes the
displayed form, or the client accepts a value labelled as composed.

The first is now refused in writing. The second is unreachable: Walmart will not
switch this browsing session to 72712, by automation or by hand, and
`reports/2026-11-01-store100-notation-probe/REPORT.md` records that. Only the
third remains.

Nothing about the shipped export changes. It already joins the two fields,
labels the result composed rather than captured, names both source fields in its
provenance, never rounds, and discloses that Walmart renders cents while the
join produces dollars. The provider's instruction to "combine the fields on your
side" is a description of what has already been done.

## 2. The store chooser error raises a question about the 615 records

This is the part that matters, and it is a question rather than a finding.

The provider now describes its own mechanism: open the product page, **attempt
to switch to the requested store**, then read the price in that context. And it
says that switch is currently throwing a technical error with Walmart's store
chooser. That is the same failure this project hit independently from a browser
on 1 November, which is useful corroboration that the fault is Walmart's. It
also weakens the explanation offered in
`reports/2026-11-01-store100-notation-probe/REPORT.md`, that store selection
might be unavailable to non-United States traffic: the provider collects from
United States infrastructure and is hitting it too.

But it opens something else. **If the store switch can fail, what store context
were the 22 and 23 October outputs for ZIP 72712 actually collected in?**

What is known:

- The provider's earlier answer on this ticket states that `store_id` and
  `zip_code` affect "the store context, assortment, pickup availability, stock,
  and related pickup fields".
- The same answer states the price itself is the online price "even when the
  store ID and ZIP are applied", so the **price** field is probably unaffected
  by a failed switch either way.
- The exposure is therefore not price. It is **assortment and the pickup
  fields**. `available_for_pickup` in `FIELD_PROVENANCE.json` is what the
  statement "143 populated prices are on products not available for pickup"
  rests on, and the dataset's claim to be store 100's assortment rests on the
  switch having worked.
- One live observation is consistent with either explanation and settles
  neither: the Xtra product showed `$5.78` on a Walmart page in a Sacramento
  store context, equal to the provider's `final_price` for the 72712 run. That
  is what you would see if the price is national, and also what you would see if
  no store switch occurred.

What is not known, and has been asked: whether the error is recent or was
present on 22 and 23 October, and whether the store context was actually applied
to our snapshots. Until the provider answers, the 615 records should not be
described as carrying a *verified* store 100 assortment. They are the provider's
output for a requested store 100 and ZIP 72712 context, which is a weaker and
accurate statement.

## What this does not establish

- Not that the store switch failed for our collection. The error is described as
  current, on 1 November. Our snapshots are from 22 and 23 October.
- Not that the assortment is wrong. No product in the 615 has been shown to be
  absent from store 100.
- Not that the price values are affected. The provider's position is that the
  price is the online price regardless of the switch.
