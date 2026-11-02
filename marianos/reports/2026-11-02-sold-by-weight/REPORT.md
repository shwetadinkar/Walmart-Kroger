# Products the retailer prices by weight, 2 November 2026

Store: Mariano's Vernon Hills, `53100502`.

The client asked for the actual source observations on approximate-weight
products, making the point that an approximate price alone cannot tell you
whether the title or size carries excluded weight wording. That is right, and
checking it found something worse than a judgement call.

## The exclusion cannot see this class of product at all

| | |
|---|---:|
| Page cards examined | 656 |
| Products the retailer prices by weight or variably | **34** |
| Of those, caught by the existing approximate-weight exclusion | **0** |
| Of those, the exclusion cannot see | **34** |

The rule in `schema.py` is not broken. It reads the product title and the
weight field for approximate wording, including `sold by weight`, `variable
weight`, `about N lb` and the rest, and that is the right test. The Kroger API
simply does not put the wording there. On all 34 it reports a clean size:

| API weight value | Products |
|---|---:|
| `1 lb` | 31 |
| `12 ounces` | 2 |
| `1 each` | 1 |

So the two sources describe the same product differently. The API says
`1 lb`. The retailer's own page says `about $1.45 each` with a rate of
`$0.69/lb` beside it. Working from API text alone, there is nothing to match
and the product passes.

How the page presents them:

| Page presentation | Products |
|---|---:|
| `about each, sold by weight` | 25 |
| `about each on sale, sold by weight` | 6 |
| `prices may vary` | 3 |

By root: Meat 24, Produce 7, Candles and Home Fragrances 2, Natural Organic 1.

`data/sold_by_weight_audit.json` lists every one of the 34 with both
observations side by side: the API title, weight, price and URL, and the
page's price basis, approximate price, displayed rate, rendered size and the
term that found it. That is the material the client asked to review.

## Nothing has been removed

The brief excludes approximate-weight products, and this evidence says these
qualify. The audit still changes nothing, for two reasons.

Removing delivered rows is a decision for the client, not an inference this
repository acts on by itself. And this repository has deleted rows on its own
reading of a rule four times before, which is why PART 0 of
`../../REVIEW_ACTIONS_2026-10-31.md` exists.

So the 34 remain in the delivered set, and the evidence that they are sold by
weight is recorded beside them here.

## What this does not establish

**A rate for the rest of the set.** 34 is out of the 649 products the page read
reached, not out of 26,166. The other 25,517 have no page evidence, so their
status is unknown. It is not estimated here and should not be extrapolated: the
page read went to terms chosen for breadth across roots, not a random sample,
so the share among them says nothing reliable about the whole.

**That the exclusion rule should change.** Making it infer sold-by-weight from
a clean `1 lb` would be guessing from an absence. The defect is that the API
text does not carry the information, and the fix for that is evidence from the
page, which is what this audit is.

**That these 34 are all of them.** They are the ones visible where two sources
could be compared.

## Reproducing it

```bash
python3 marianos/tools/sold_by_weight_audit.py \
  --records <the 26,166-record data_22_fields.json> \
  --page marianos/reports/2026-11-01-vernon-hills-page-harvest/data/parsed_full.json \
  --out <output path>
```

Verification: 16 tests in `tests/test_coverage_and_weight_audits.py`, direct
and pytest agreeing. Two mutations were caught: making the audit claim the
exclusion catches these products, and making the reconciliation stop reporting
roots assigned despite an unmapped label.
