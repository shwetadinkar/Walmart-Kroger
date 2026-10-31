# Promotion identity

Taken from the correction of 28 October on `marianos-fresh-runs-category-evidence`.
The identity sets are in `promotion_correction/IDENTITY_FIXTURE.json`.

The earlier README had the two products reversed.

| UPC | Product | Disposition |
|---|---|---|
| `0002100061223` | | retained |
| `0002100065893` | | retained |
| `0007457001310` | bars | retained |
| `0007457001400` | chocolate ice cream | withheld, API and page regular and sale prices conflict |
| `0007457000400` | vanilla | withheld, same reason |

The expanded coupon source was the chocolate page, `0007457001400`. Its
qualifying-product card also identified the retained bars, `0007457001310`. The
source page's identity is not the retained product's identity, and neither is
relabelled as the other.

**The expiry is unresolved.** The terms say a redemption end of November 3, and
the page displayed Nov. 04. Both are preserved as observed. No date was chosen,
and no final coupon price was inferred. `expiry_discrepancy_resolved` is `false`.
