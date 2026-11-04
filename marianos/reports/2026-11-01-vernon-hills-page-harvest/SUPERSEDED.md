# data/parsed_full.json is superseded by data/parsed_full_corrected.json

Both files are kept. `parsed_full.json` is the parse that fed the merge in the
release delivered on 4 November, so it is the evidence of what was published and
a corrected file cannot serve as that. It is not edited.

## Do not rely on these keys in parsed_full.json

- **`deal_lines`** holds every card line that was not the title or the size,
  which includes lines that are not offers. Through the merge as it then stood,
  that put `Low Stock` into `volume_deals_description` on 47 records and
  `View 2 Offers` on 12 more; **82** of the 183 volume values were wholly or
  partly a stock status, a payment eligibility or a navigation link. The 22
  fields have no column for any of those. (This said 77, written from memory.
  The sub-counts above are exact; only the summary was wrong, and it understated
  the defect. Found by an independent review on 4 November.)
- **`size`** holds the line after the title whatever it said. On sold-by-weight
  cards, which carry no size, that swallowed two digital coupons
  (`0000000003283` and `0000000004409`) and a number of `Buy 1, Get 1 Free`
  offers. Those offers were lost rather than published wrongly, because the page
  read never supplies `size` to a published row; the API does.

## What the corrected file changes

Same 656 cards, same 608 displayed rates. **Nothing in `ppm` changes.** The
displayed rate was read from its own column in the capture and was never
affected by either defect.

| | parsed_full.json | parsed_full_corrected.json |
|---|---:|---:|
| cards | 656 | 656 |
| `ppm` present | 608 | 608 |
| volume deal published | 183 | 120 |
| digital deal published | 51 | 54 |
| rows whose deal columns differ | - | 88 |

The 63 fewer volume values are badges and links that should never have been in
that column. The 3 more digital values are the two recovered coupons and one
`Cash Back:` offer that was being published as a volume deal.

## What this does not say

It does not say the release is wrong about anything else. `ppm`, the store
columns, the prices, the category assignment and the record count are untouched
by this. It is one defect in two adjacent fields, found by comparing this read
against the 4 November read of the same store, and it is bounded by the counts
above.

It does not revise the 4 November release by itself. The release still holds the
uncorrected deal columns until the merge is run again against this corrected
parse; until then, `volume_deals_description` in the delivered export is the
183-row version described here.
