# The 34 sold-by-weight products, one verdict each, 3 November 2026

The client asked for exact title, size/weight wording and page evidence per
product, with approximate-weight wording excluded and genuine fixed-size,
bulk and multipack identities kept. He also said not to remove all 34 merely
for being sold by weight or carrying an approximate total price, and not to
infer from an API size of `1 lb` that the page has no excluded wording.

| Verdict | Products |
|---|---:|
| EXCLUDE, observed size or weight wording is approximate | 0 |
| KEEP, a genuine page size was observed and is not approximate | 3 |
| UNDETERMINED, no usable page size wording to judge by | 31 |

**Nothing has been removed.** The verdicts are a recommendation; the decision
is the client's, and an UNDETERMINED product stays in the dataset either way.

## What decided each verdict

Only two things: the product's title, and its size or weight wording. The
shipped patterns `schema._APPROX` and `schema._APPROX_WEIGHT` are imported
rather than restated, so this table cannot disagree with the rule that
actually filters.

The page's pricing basis is on every row and decided nothing. `_APPROX_WEIGHT`
matches `sold by weight`, and 31 of the 34 pages carry that phrase in
their pricing basis, so feeding it to the rule would have excluded them on
precisely the ground the client ruled out. It is pricing, not size.

## Why 31 are undetermined

The page capture produced a genuine size, a quantity and a unit, for
3 of the 34. For 4 more it put promotional or price
text in the size slot, for example `Buy 1, Get 1 Free` and
`Coupon: $1.79 lb Honeycrisp Apples`. That text carries no approximate-weight
wording, but a promotional badge would not, so it is no evidence of a fixed
size and those products are undetermined rather than kept. For the rest there
is no size or weight wording at all.

That the capture mislabelled four slots is itself a defect in the capture, and
it is reported here rather than relied on.

That is a gap in the capture, not a property of the products. It cannot be
closed by reasoning from the API size, which is the client's point. It needs a
page observation that reads the size or weight element specifically, for those
31 product paths. Those paths are listed in `verdicts.json`.

## What this does not establish

- **That the EXCLUDE set is complete.** It is complete with respect to the
  wording captured. A product with no page size wording could carry excluded
  wording that was never read.
- **That the KEEP set is safe to keep for ever.** It is eligible on the
  evidence held today. A later page read could show otherwise.
- **Anything about the other 26,132 delivered products.** This covers the 34
  the page priced by weight among the 656 page cards examined, out of
  26166 delivered records. The page read reached a subset chosen for
  spread across roots, not a random sample, so no rate here estimates the
  whole.
