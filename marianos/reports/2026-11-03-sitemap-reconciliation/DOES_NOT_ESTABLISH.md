# What this reconciliation does not establish

**It is not a coverage percentage, and no figure in it should be read as one.**

The retailer's product-listing sitemap gives, for the first time in this
project, a denominator for *categories*: 461 published listing pages, being
39 departments, 184 subcategories and 238 leaves,
read from the retailer's own file on 2026-11-02. That is what the numbers above
count.

It gives no denominator for *products*. The product sitemap holds 890
URLs. 26166 products were collected from the Kroger API at this one
store. The sitemap is therefore an SEO subset of the catalogue, not the
catalogue, and three things follow that have to be said plainly:

- **326 of those 890 products are not in the delivered dataset.** That
  is not 326 missed products. A sitemap is site-wide and a product in it
  may not be carried at Marianos - Marianos Vernon Hills at all. Separating a collection gap from
  an assortment fact needs a store-bound lookup per id, which is what
  `tools/resolve_sitemap_gap.py` does and what has not been run yet.
- **Presence in the sitemap is not a random sample**, so the 564 that
  are present support no estimate of the whole.
- **The published taxonomy is not the whole taxonomy.** `Bakery`, `Beer Wine Liquor`, `Coupons`, `Floral` have no
  listing page in the sitemap at all. Of those, 3 (Bakery, Beer Wine Liquor, Floral) carry
  delivered records that the Kroger API's own labels produced. So the site's
  listing vocabulary and the API's category labels are two different
  vocabularies, each incomplete relative to the other. Neither is treated here
  as authoritative, and the per-root table says which source evidences which
  root.

**It says nothing about price, measure, promotion or stock.** A sitemap carries
URLs. Every value in the delivered records still comes from where it came from
before, and the two fields the public API does not carry are still blank.

**It is a capture, not a feed.** The sitemap was read in a browser on an
ordinary residential connection. The same URL fetched from a datacenter was
refused before any HTTP exchange, the same refusal shape measured from two
Azure regions on 30 October. No challenge was answered and none was bypassed.
So this taxonomy is a dated artefact that a scheduled run reconciles against,
not something a scheduled run can refresh by itself.
