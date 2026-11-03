## The gaps, kept explicit as asked

**Category coverage is not established and this path does not establish it.**
The Kroger public Products API has no category enumeration. `filter.start` is a
skip count refused past 250, so one term reaches at most 300 products however
many sit behind it, and on the 31 October run 69 of 301 terms hit that ceiling.
Five of the 28 configured roots return nothing from this API and are declared,
with reasons, in `config/sweep_coverage.json`. A sweep run therefore covers 23
roots and says so in its own release report. Nothing above changes that.

**Enrichment is not unattended.** Displayed price per measure and retailer deal
wording exist only on the rendered retailer page. The public API carries
neither. The 592 rates and the deal wordings in the delivered set came from an
attended browser session, and the page route stopped after 28 page loads on 1
November. No unattended route to those fields is available today, which is set
out in `ROUTES_AND_AUTONOMY.md`.

**Nothing here ran on Azure.** No schedule fired, nothing ran in the client's
environment, and the delivered 26,166 did not come from Azure. The deployment
template and a three-execution manual pilot of 28 October are the whole of the
Azure evidence, and that pilot was at West Loop on a five-product selection of
one term.

**The data above is invented.** The transcript evidences the code path, not an
assortment, a price or a count. Real collection at the assigned store is the
separate 26,166 record run of 31 October, which did not go through this path.
