#!/usr/bin/env python3
"""Write the out-of-scope reconciliation for products with no configured root.

The client's instruction of 4 November: retain their original retailer labels
and identities in a separate unmapped/out-of-scope reconciliation, with source
paths and counts; do not invent a root assignment and do not discard historical
observations; and any eventual mapping must be supported by the retailer
taxonomy rather than by the search term that found the product.

This re-indexes the **persisted raw API responses**. It performs no collection:
no Kroger client is constructed, nothing is fetched, and no credential is read.
That is the re-filter-rather-than-re-fetch property the sweep was built to have,
used here rather than claimed, which is why this reconciliation can be produced
for a release that is already published without disturbing it.

The output is written beside a release, never into it. These products belong to
no configured root, so they appear under none, and their presence here does not
establish completion of any required root.
"""

import argparse
import csv
import json
import sys
import textwrap
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from marianos_collector.api_trial import load_category_map  # noqa: E402
from marianos_collector.config import Store  # noqa: E402
from marianos_collector.kroger_sweep_source import KrogerSweepSource  # noqa: E402


def P(text):
    return textwrap.fill(" ".join(text.split()), width=79)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--work-dir", required=True,
                   help="The sweep work directory holding the persisted raw responses")
    p.add_argument("--location-id", required=True)
    p.add_argument("--store-id", required=True)
    p.add_argument("--zipcode", required=True)
    p.add_argument("--store-name", required=True)
    p.add_argument("--store-location", required=True)
    p.add_argument("--release", default="",
                   help="The release id this reconciles, recorded in the output")
    p.add_argument("--out", required=True, help="Output directory")
    a = p.parse_args(argv)

    if a.store_id != a.location_id:
        p.error("--store-id must equal --location-id, so the labels in this "
                "reconciliation describe the store that was queried")

    store = Store(store_id=a.store_id, zipcode=a.zipcode,
                  store_name=a.store_name, store_location=a.store_location)

    # client=None on purpose: indexing reads the persisted responses off disk
    # and never touches the network. If this ever starts needing a client, that
    # is a collection and does not belong in a reconciliation tool.
    source = KrogerSweepSource(None, a.location_id, Path(a.work_dir),
                               category_map=load_category_map(), resume=True)
    index = source._index_raw(store)

    rows = list(index.out_of_scope)
    by_label = Counter(r["retailer_label"] or "(none)" for r in rows)
    by_file = Counter(r["source_response_file"] for r in rows)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    fields = ["identity", "upc", "product_title", "retailer_label",
              "configured_root", "source_response_file", "search_term",
              "observed_at", "product_id"]
    with open(out / "out_of_scope_products.csv", "w", newline="",
              encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in sorted(rows, key=lambda x: (x["retailer_label"], x["upc"])):
            w.writerow({k: r.get(k, "") for k in fields})

    payload = {
        "release_reconciled": a.release,
        "store_id": a.store_id,
        "location_id": a.location_id,
        "work_dir": str(a.work_dir),
        "responses_indexed": index.responses,
        "products_seen": index.products_seen,
        "duplicate_identities": index.duplicates,
        "products_served_under_a_root": index.product_count,
        "out_of_scope_count": len(rows),
        "unplaceable_counter": index.unplaceable,
        "counts_by_retailer_label": dict(by_label.most_common()),
        "distinct_source_response_files": len(by_file),
        "products": sorted(rows, key=lambda x: (x["retailer_label"], x["upc"])),
        "_configured_root_is_always_empty_because":
            "the retailer's own label is not in config/category_map.json; the "
            "search term that found the product is not evidence of its category",
        "_does_not_establish": [
            "Completion of any required root. These products belong to none of "
            "the client's 28 roots and are served under none.",
            "That the retailer taxonomy supports any particular mapping. The "
            "label is recorded as returned so that question can be answered "
            "from the retailer's own taxonomy, not from this file.",
            "That this is the complete set of out-of-scope products in the "
            "retailer's catalogue. It is the set the term sweep reached, and "
            "the sweep cannot attest complete category discovery.",
        ],
    }
    (out / "OUT_OF_SCOPE_RECONCILIATION.json").write_text(
        json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")

    if index.unplaceable != len(rows):
        raise SystemExit(
            f"REFUSED: the unplaceable counter says {index.unplaceable} and "
            f"{len(rows)} identities were retained. A reconciliation that does "
            f"not account for every counted product is not a reconciliation.")

    lines = [
        "# Out-of-scope reconciliation",
        "",
        P(f"{len(rows)} products the term sweep reached carry a retailer label "
          f"that is not in the explicit category map, so they belong to none of "
          f"the client's 28 configured roots. They are recorded here with the "
          f"label exactly as the retailer returned it, their identity, and the "
          f"raw response file each was read from."),
        "",
        P("No root is assigned and none is guessed. The search term that found "
          "a product is not evidence of its category. Any eventual mapping has "
          "to be supported by the retailer's own taxonomy, which is why the "
          "label is kept verbatim rather than normalised."),
        "",
        P("Produced by re-indexing the persisted raw responses. Nothing was "
          "collected and no credential was read, so this reconciles a release "
          "that is already published without disturbing it."),
        "",
        "## Counts by retailer label",
        "",
        "| retailer label | products |",
        "|---|---:|",
    ]
    for label, n in by_label.most_common():
        lines.append(f"| `{label}` | {n} |")
    lines += [
        f"| **total** | **{len(rows)}** |",
        "",
        P(f"Read from {len(by_file)} distinct raw response files out of "
          f"{index.responses} indexed. Per-product source paths are in "
          f"`out_of_scope_products.csv` and in the JSON."),
        "",
        "## What this does not establish",
        "",
    ]
    for item in payload["_does_not_establish"]:
        lines.append(P("- " + item))
        lines.append("")
    (out / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({k: v for k, v in payload.items()
                      if k not in ("products",)}, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
