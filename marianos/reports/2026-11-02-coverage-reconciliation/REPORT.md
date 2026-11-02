# Root, subcategory and page reconciliation, 2 November 2026

Store: Mariano's Vernon Hills, `53100502`, 1720 N Milwaukee Ave, IL 60061,
pickup.

The client asked for a reconciliation of all required roots, applicable
subcategories and pages, and said that term searches and a large count do not
establish full coverage. They do not. This states what was reached, from what,
and what bounds it.

Everything is recomputed by `tools/coverage_reconciliation.py` from the
delivered records and the run report. `data/coverage_reconciliation.json` is
its full output, including every root and every capped term by name.

## Roots

28 required, taken from the client's own `config/categories.csv`. **23 carry
products. 5 do not.**

The five are `Coupons`, `Seafood`, `Coffee`, `Batteries` and `Light Bulbs`, and
the reason is Kroger's label vocabulary rather than the shelf. Kroger publishes
no label for Coffee, Batteries or Light Bulbs; it files seafood inside a single
`Meat & Seafood` label that maps to Meat and cannot be separated from it; and
Coupons is not a product category. Those products are present in the data under
the labels Kroger does use. A zero measures the vocabulary, not the store.

For each of the 23 populated roots the JSON lists the Kroger labels that
produced its products and how many came from each, which is the nearest thing
this route has to a subcategory reconciliation. See the limit on that below.

## The root is never guessed

| | |
|---|---:|
| Kroger labels with no entry in the map | 10 |
| Distinct products left with no root as a result | 187 |
| Encounters during the sweep | 255 |
| Products given a root despite an unmapped label | **0** |

The last line is the one that matters: an unmapped label leaves `category`
empty and is reported. A non-zero value there would mean a root had been
guessed.

The two middle numbers differ and the difference is not an error. The sweep
counts an encounter each time a term returns a product, and one product is
commonly returned by several terms; the run collapsed 17,089 repeat placements
in total. 187 describes the delivered data, 255 describes the sweep.

Separately, the product's own Kroger label disagreed with the root of the term
that found it **17,881 times**. In every case the product's own label won. The
search term is a way of reaching a product, not evidence of its category, which
is why that number is large and why it is reported rather than hidden.

## Pages, and what bounds the coverage

| | |
|---|---:|
| Terms swept | 301 |
| Requests spent | 998 |
| Page failures | 0 |
| Pages requested per term, ceiling | 20 |
| Highest `filter.start` Kroger accepts | 250 |
| Results reachable per term | 300 |
| **Terms that hit that ceiling** | **69** |

That last row is the honest limit. `filter.start` is a skip count and Kroger
refuses more than 250, so one term yields at most 300 results however many
exist behind it. 69 of 301 terms reached that ceiling, which means there were
more products behind those terms than were ever fetched. By root the capped
terms fall most heavily on Grocery 12, Produce 9, Candy 6 and Dairy 5. All 69
are named in the JSON.

## What this does not establish

**Complete category discovery.** The public API has no category enumeration.
Products are reached by search term, so a product no term reached was never
seen, and no count here is a statement about what the store carries.

**Complete results per term.** See the 69 capped terms above.

**Subcategory completeness.** `sub_category` is the label the product reports
about itself. It is not a traversal of the retailer's subcategory tree, which
this route cannot enumerate. Listing the labels that produced a root is not the
same as covering that root's subcategories, and should not be read as such.

**That a zero root means the store carries none.** It means no product reached
by these terms reported that label.

## Reproducing it

```bash
python3 marianos/tools/coverage_reconciliation.py \
  --records <the 26,166-record data_22_fields.json> \
  --run-report <that run's run_report.json> \
  --categories marianos/config/categories.csv \
  --enriched <the merged records, optional> \
  --out <output path>
```
