# 4 November page harvest, Vernon Hills: scope and limits

## What was done

An attended browser session on the account holder's own machine, in his own
browser, on his own connection, reading the retailer's own rendered search
result cards at the assigned store. 12 search terms, 279 product cards, 279
distinct UPCs. Parsed by `tools/parse_page_harvest.py` with outcome `ok` on all
279 and zero cross-term conflicts.

- displayed price per measure present on **202**
- deal or offer wording present on **137**
- sale price present on 67, size present on 231

Store context was confirmed two independent ways before collection and is not
inferred: the page header read `Pickup at Marianos Vernon Hills`, and the
store cookie read `DD_modStore=53100502`.

Against the 1 November harvest of 649 UPCs: **103 overlap, 176 are new**, and
**138 of the new ones carry a displayed rate**.

Terms: salmon, shrimp, tilapia, ground coffee, batteries, light bulbs, food
storage containers, screwdriver, apples, bananas, flowers, coupon.

## What it does not establish

**It does not establish that any of these products are in the delivered API
set.** These rows carry a UPC, a displayed rate and verbatim card lines, and
nothing else. They enrich an API record when the merge binds them to one by
UPC, and a UPC with no API record contributes nothing, as 21 of the 1 November
649 did. How many of the 176 bind is a fact the merge reports; it is not
assumed here and no number for it is stated.

**It does not populate the empty roots on its own.** Seafood, Coffee,
Batteries and Light Bulbs are empty in the delivered set because the API sweep
reached no product carrying those labels, not because a rate was missing. A
displayed rate for a battery does not create a battery record. Creating one
would need the product's own API record, fetched by UPC, and that has not been
done.

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
