# The executable production route, 2 November 2026

The client asked which route is actually executable, what it depends on, and
the exact command for the next fully traversed category. The direct answer
comes first because it is not the answer the rest of this repository implies.

## There is no single route today that meets the brief

Nothing currently runs unattended, on a schedule, and produces a store-bound
assortment **with** displayed price per measure and retailer deal wording. The
delivered material came from two different routes, one of which is not the
deployed collector and one of which is not unattended.

| What was delivered | What produced it | Unattended? |
|---|---|---|
| 26,166 store-verified records, no PPM, no deal wording | `tools/kroger_full_sweep.py` | Yes, but see below |
| 592 displayed rates, 181 volume and 51 digital deal wordings | an operator-driven browser session on 1 November | **No** |

**The collector CLI did not produce either.** `marianos_collector/cli.py`
offers `--source fixture | provider | catalog_v2 | composite`. None of those is
the Kroger public Products API sweep that produced the 26,166. That sweep is a
separate tool that does not pass through the runner, so it does not get the
publication gate, the retention reconciliation, the trial and published
namespace separation, or the checkpoint and resume logic. That is a real gap
between what is deployed and what was delivered, and it is the substance of
the client's fourth point.

## Every route, what it needs, and whether it runs

| Route | Dependencies | Runs today? |
|---|---|---|
| `--source fixture` | none | Yes. Synthetic. Labelled `synthetic_fixture_NOT_contest_proof` and refused by the submission gate |
| `--source catalog_v2` | `--authorized-source`, `MARIANOS_DATA_AUTHORIZED=yes`, `KROGER_CLIENT_ID`, `KROGER_CLIENT_SECRET` on the **partner** tier, a verified store id | **No.** Partner access is not authorized and no partner request is to be made |
| `--source provider` | `--authorized-source`, `MARIANOS_DATA_AUTHORIZED=yes`, `PROVIDER_BASE_URL`, `PROVIDER_API_TOKEN` | **Not for this store.** The provider's Kroger dataset returns no store for the Vernon Hills ZIP; their R&D holds ticket #754403 |
| `--source composite` | a spine from the above, plus enrichments | Only as well as its spine. It installs `unavailable_crawl`, so `ppm` and the coupon fields are blank by construction |
| `tools/kroger_full_sweep.py` | `KROGER_CLIENT_ID`, `KROGER_CLIENT_SECRET` on the **public** tier | Yes. This produced the 26,166. It carries no displayed rate or deal wording, and it sits under the unresolved question in `ACCEPTABLE_USE_POSITION.md` |
| browser page read | an operator at a machine the retailer serves | Attended only. Stopped after 28 page loads on 1 November |

## The exact commands that do run

The sweep that produced the delivered records:

```bash
cd marianos
KROGER_CLIENT_ID=... KROGER_CLIENT_SECRET=... \
python3 tools/kroger_full_sweep.py \
  --location-id 53100502 --zipcode 60061 \
  --street "1720 N Milwaukee Ave" \
  --store-name "Marianos - Marianos Vernon Hills" \
  --terms config/sweep_terms.json \
  --category-map config/category_map.json \
  --pages-per-term 20 --max-requests 8000 \
  --output out/<a new folder>
```

Narrowed to one root, which is the nearest thing available to "one category":

```bash
  --only-category "Dairy"
```

Merging a page read into a sweep's output:

```bash
python3 tools/merge_page_enrichment.py \
  --api out/<run>/data_22_fields.json \
  --page <parsed page cards>.json \
  --observed-at <the date the pages were read> \
  --out out/<a new folder>
```

The deployed collector, which runs end to end but only on fixtures today:

```bash
python3 -m marianos_collector.cli run --source fixture --store DEMO-LAKESHORE-60601
```

## On "the next fully traversed category"

This route cannot fully traverse a category, and no command will make it.

The Kroger public Products API has no category enumeration. `/products`
requires `filter.term`, so products are reached by searching, and a product
nobody searched for is never seen. `filter.start` is a skip count Kroger
refuses past 250, so one term yields at most 300 results however many exist.
On the 31 October run, **69 of 301 terms hit that ceiling**, which means more
products stood behind those terms than were ever fetched.

The only route that could traverse a category exhaustively is Catalog V2,
which has no category filter: a paged sweep is complete by construction once
the API reports `hasMore: false`. It is partner-gated, and a partner request is
not authorized. So exhaustive traversal is unavailable, and widening the term
list increases breadth without ever becoming a completeness claim.

## What is feasible without new entitlement

Three things, none of which require an entitlement that does not already exist.

**1. Widen the term list on the public sweep.** Cheap, repeatable, improves
breadth. It never becomes category completeness and the reports must keep
saying so. It stays under the acceptable-use question, which is the client's to
settle.

**2. Bring the sweep inside the collector.** This is the one that closes the
gap the client found. Making the sweep a `Source` the runner drives would give
the delivered data the publication gate, retention reconciliation, namespace
separation and resume that the CLI routes already have, and would make
"unattended twice weekly" a property of the thing that actually produces the
data. It is work on code that already exists and needs no outside permission.

**3. The existing provider account, once their defect is fixed.** Bright Data
is an account already held, not a new entitlement. Their reply of 1 November
says the dataset can return displayed price per measure and digital coupon
data for supported stores, and their R&D holds the Mariano's ZIP failure. One
caution, stated because it cuts against the hope: the five-record Kroger sample
supplied on 1 November had `price_by_unit` and `price_per_unit` null on every
record, carried no coupon field at all, and spanned five different store ids
over three dates. So the capability is claimed but not yet demonstrated, and
the question is open with them.

## Dated milestone

Left blank deliberately: dates are set by the account holder, not here.

## What this document does not establish

- That option 2 would produce PPM or deal wording. It would not. It fixes how
  the assortment is produced, not what the public tier carries.
- That option 3 will work. The provider's defect is unresolved and their own
  sample did not carry the two fields in question.
- That any of this changes the acceptable-use position. It does not.
  `publication_eligible` is still false and that decision is still open.
