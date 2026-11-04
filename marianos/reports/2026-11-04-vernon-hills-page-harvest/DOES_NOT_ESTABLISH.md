# 4 November page harvest, Vernon Hills: scope and limits

## What was done

An attended browser session on the account holder's own machine, in his own
browser, on his own connection, reading the retailer's own rendered search
result cards at the assigned store. 12 search terms, 279 product cards, 279
distinct UPCs. Parsed by `tools/parse_page_harvest.py` with outcome `ok` on all
279 and zero cross-term conflicts.

- displayed price per measure present on **202**
- deal or offer wording present on **29**
- sale price present on 67, size present on 213

Those three figures are `deal_text_present`, `sale_price_present` and
`size_present` from `PARSE_REPORT.json` in this folder, and they can be
recomputed from `data/harvest.tsv`. **This file first said 137 and 231.** 137
was neither a count of anything: it was deal lines plus the badge labels that
are deliberately not deal wording, and it overstated the real figure by about
4.7 times. 231 was simply wrong against the 213 in the report beside it. Both
were written from memory into a file whose whole purpose is to be the
conservative statement, and both were falsifiable against a JSON file in the
same directory. Found by an independent review on 4 November.

Store context was confirmed two independent ways before collection and is not
inferred: the page header read `Pickup at Marianos Vernon Hills`, and the
store cookie read `DD_modStore=53100502`.

**The folder is named for the local date and the observation is stamped in
UTC, and they differ.** The pages were read at `2026-11-03T19:56Z` to
`2026-11-03T20:04Z`, which was already 4 November where the account holder
sits, at UTC+5:30. Release ids and `crawl_date` in this repository are UTC, so
the merge is stamped `2026-11-03T20:00:00+00:00` and the folder name is the
local date. Stamping it 4 November UTC would have put the observation in the
future, and the composition layer refused exactly that on the first attempt:
`UNBOUND_TIME_FUTURE` on 229 of 279 contributions. The gate was right and the
timestamp was wrong.

Against the 1 November harvest of 649 UPCs: **103 overlap, 176 are new**, and
**138 of the new ones carry a displayed rate**.

Terms: salmon, shrimp, tilapia, ground coffee, batteries, light bulbs, food
storage containers, screwdriver, apples, bananas, flowers, coupon.

## What it does not establish

**It still does not create a record in any of those roots.** A displayed rate
for a battery does not make a battery record, and none was made.

**The search term is not evidence of category.** The `shrimp` term returned a
steak seasoning, among others. Nothing here assigns a category, and the term
column is kept only so a reader can see how a card was reached.

**It does not establish an unattended route.** This was a person's own browser
driven interactively. It is not a schedule, not a server, and nothing about it
runs twice a week. The three page-only columns will be empty again in the next
sweep unless a merge is run against a page read.

**It does not reopen the datacenter route.** No refusal was encountered at any
point in this session, which bounds nothing about our egress: the measured
refusals from two Azure regions, a second cloud provider and a plain sitemap
request were from datacenter addresses, and this was not. The two are
different observations about different clients and neither answers the other.

**Floral and Coupons returning zero rates is an observation, not a gap in this
harvest.** 24 flower cards and 24 coupon cards were read and parsed cleanly;
the retailer displays no price per measure on either surface. Coupons is a
savings surface rather than a product category.

**It says nothing about Azure, about category coverage, or about the 300
product per term ceiling.** None of those were touched.

## Answered since this file was written

**They do bind: 271 of the 279 are in the API set, 8 are not.** Measured by
running the merge, not assumed. Against the 26,166 record spine available here
the three page-only columns go from 592, 120 and 53 to **729, 147 and 53**,
with zero conflicts and nothing refused as unbindable. The 8 that do not bind
contribute nothing rather than being attached to anything.

That figure is from the 26,166 set, which is superseded. The same merge against
the delivered 28,549 has not been run, because that release is not in this
checkout, and its numbers will differ.

**The empty roots are not empty for want of a rate, and the products are not
missing.** This is the finding worth carrying to the client. The four roots
reported as unreachable by the API hold products that are in the delivered data
already, under the retailer's own broader label:

| client root | where those products actually sit, as delivered |
|---|---|
| Coffee | 24 ground coffee products under `Beverages` / `Beverages` |
| Batteries | 19 under `Household` / `Cleaning Products`, 5 under `Hardware Home Improvement` |
| Light Bulbs | 24 under `Household` / `Cleaning Products` |
| Seafood | salmon, shrimp and tilapia under `Meat` / `Meat & Seafood` and `Frozen` / `Frozen` |

So these roots are empty because **the retailer publishes no label that
distinguishes them**, not because the sweep failed to reach the products. This
is the same situation already documented for Seafood inside Meat, and it holds
for all four. Serving them under the client's finer roots would mean assigning a
category the product's own source does not carry, which the one rule forbids.
It is a question about the client's taxonomy against the retailer's, and it is
his to answer; nothing here guesses at it.

