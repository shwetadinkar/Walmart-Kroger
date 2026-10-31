#!/usr/bin/env python3
"""Populate ppm and regular_price on the 615 from the provider row each came from.

Offline. The input submission is never changed; output goes to a new folder.
`ppm` is composed as $<unit_price>/<unit> from the raw number text, so nothing is
rounded. It is NOT the string Walmart displays, and the provenance says so per
value. `regular_price` is the provider's final_price, Walmart's online page price.
A row without both unit fields keeps a blank ppm. Every other field is copied.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from walmart_collector.brightdata_import import _product_id, _validate  # noqa: E402

STATEMENT = "walmart/evidence/2026-10-31-provider-ticket-754118.md"
COMPOSED_FIELDS = ("ppm", "regular_price")
MUST_STAY_BLANK = ("gupc", "unit_price")
SOURCE_NOT_DISPLAY = (
    "Composed from the provider's unit_price and unit, which hold a bare number and a "
    "separate unit. The string is in dollars. Both page observations cited for this "
    "route render cents: 86.8 ¢/lb, captured in reports/2026-10-30-display-ab at a "
    "Sacramento store, and 5.7 c/fl oz, named in the provider-ticket note with no "
    "capture in this repository. This string is not the one displayed.")
PRICE_BASIS = (
    "The provider's final_price. The provider states this is the online price shown by "
    "Walmart for the store and ZIP context, and that no separate pickup price exists in "
    "the output. It is not shown to be the store 100 pickup price.")


class CompositionRefused(RuntimeError):
    pass


def read_exact(path):
    """JSON with numbers kept as their source text, so 0.340 stays 0.340."""
    return json.loads(Path(path).read_text(encoding="utf-8"), parse_float=str, parse_int=str)


def rows_of(document):
    return document if isinstance(document, list) else [document]


def compose_ppm(unit_price, unit):
    number, name = str(unit_price or "").strip(), str(unit or "").strip()
    if not number or not name:
        return ""
    if not re.fullmatch(r"\d+(?:\.\d+)?", number):
        raise CompositionRefused(f"unit_price is not a plain number: {number!r}")
    return f"${number}/{name}"


def format_regular(final_price):
    """Two decimals, as every price in the data. Adds zeros, never rounds."""
    text = str(final_price or "").strip()
    if not text:
        return ""
    match = re.fullmatch(r"(\d+)(?:\.(\d{1,2}))?", text)
    if not match:
        raise CompositionRefused(f"final_price would need rounding: {text!r}")
    return f"{match.group(1)}.{(match.group(2) or '').ljust(2, '0')}"


def observed_values(snapshots):
    """Every value each product had across all snapshots, for recording conflicts."""
    found = {}
    for path in sorted(Path(snapshots).glob("*.json")):
        for record in rows_of(read_exact(path)):
            if isinstance(record, dict) and not record.get("error") and not record.get("error_code") \
                    and not _validate(record, "100", "72712"):
                identity = _product_id(record)
                if identity:
                    slot = found.setdefault(identity, {"final_price": set(), "unit_price": set()})
                    for name in slot:
                        if record.get(name) not in (None, ""):
                            slot[name].add(str(record[name]))
    return found


def compose(rows, evidence, snapshots, statement_sha256):
    cache, out, provenance, disagreements = {}, [], {}, []
    observed = observed_values(snapshots)
    for row in rows:
        identity = re.search(r"/(\d+)$", row["url"]).group(1)
        key = f"100:{identity}"
        if key not in evidence:
            raise CompositionRefused(f"No evidence entry for {identity}")
        ref = evidence[key]
        name = ref["file"]
        document = cache.setdefault(name, rows_of(read_exact(Path(snapshots) / name)))
        source = document[ref["row_index_zero_based"]]
        if identity not in str(source.get("url")) and identity != str(source.get("product_id")):
            raise CompositionRefused(f"{name} row {ref['row_index_zero_based']} is not {identity}")
        stated = ref.get("provider_unit_price_candidate_not_proven_displayed")
        if str(source.get("unit_price")) != str(stated) and not (
                source.get("unit_price") is None and stated is None):
            raise CompositionRefused(f"{identity}: unit_price differs from the evidence sidecar")
        for blank in MUST_STAY_BLANK:
            if row[blank]:
                raise CompositionRefused(f"{identity}: {blank} is not blank on the input")
        ppm = compose_ppm(source.get("unit_price"), source.get("unit"))
        regular = format_regular(source.get("final_price"))
        out.append({**row, "ppm": ppm, "regular_price": regular})
        base = {"snapshot_file": name, "row_index_zero_based": ref["row_index_zero_based"],
                "source_row_sha256": ref.get("source_row_sha256"),
                "source_observed_at": ref.get("source_observed_at"),
                "store_id": "100", "zip_code": "72712",
                "provider_statement": STATEMENT, "provider_statement_sha256": statement_sha256}
        provenance[identity] = {
            "url": row["url"],
            "available_for_pickup": ref.get("available_for_pickup"),
            "ppm": {**base, "value": ppm, "source_fields": ["unit_price", "unit"],
                    "raw_unit_price": source.get("unit_price"), "raw_unit": source.get("unit"),
                    "status": "composed_not_captured_as_displayed" if ppm else "blank_field_absent",
                    "basis": SOURCE_NOT_DISPLAY if ppm else "unit_price or unit is absent"},
            "regular_price": {**base, "value": regular, "source_fields": ["final_price"],
                              "raw_final_price": source.get("final_price"),
                              "status": "provider_online_page_price" if regular else "blank_field_absent",
                              "basis": PRICE_BASIS if regular else "final_price is absent"}}
        seen = observed.get(identity, {})
        for field, kept in (("final_price", source.get("final_price")),
                            ("unit_price", source.get("unit_price"))):
            if len(seen.get(field, ())) > 1:
                disagreements.append({"identity": identity, "field": field, "kept": str(kept),
                                      "observed_across_snapshots": sorted(seen[field])})
    return out, provenance, disagreements


def check(original, composed):
    if len(original) != len(composed):
        raise CompositionRefused("The row count changed")
    for before, after in zip(original, composed):
        if list(before) != list(after):
            raise CompositionRefused("The field order changed")
        changed = {k for k in before if before[k] != after[k]} - set(COMPOSED_FIELDS)
        if changed:
            raise CompositionRefused(f"Fields outside the instruction changed: {sorted(changed)}")


def summary(composed, provenance, disagreements):
    units = Counter(p["ppm"]["raw_unit"] for p in provenance.values() if p["ppm"]["value"])
    priced = [p for p in provenance.values() if p["regular_price"]["value"]]
    return {"records": len(composed), "ppm_populated": sum(bool(r["ppm"]) for r in composed),
            "ppm_blank": sum(not r["ppm"] for r in composed),
            "regular_price_populated": len(priced),
            "regular_price_blank": len(composed) - len(priced),
            "populated_where_pickup_not_available": sum(
                p["available_for_pickup"] is not True for p in priced),
            "ppm_units": dict(units.most_common()),
            "products_with_differing_values_across_snapshots": len(
                {d["identity"] for d in disagreements})}


def note(facts):
    units = ", ".join(f"`{name}` {count}" for name, count in facts["ppm_units"].items())
    return f"""# ppm and regular_price on the 615, 31 October 2026

## What these columns were

`ppm` and `regular_price` were blank on all 615 records by decision, not because nothing
was available. The provider's numbers existed and were kept in the evidence sidecar.
`ppm` was held blank because no displayed string had been captured. `regular_price` was
held blank because `final_price` is an online price and not a store pickup price.

## What changed

Both decisions are reversed for this file. The basis is `{STATEMENT}`, the provider's
answer on ticket #754118. It states that `unit_price` and `unit` are taken from text on
the Walmart page and not calculated by the provider, and that the page price for the
store and ZIP context is the only price available, with no separate pickup price.

| Column | Populated | Blank | Source |
|---|---:|---:|---|
| `ppm` | {facts['ppm_populated']} | {facts['ppm_blank']} | `$<unit_price>/<unit>`, from the raw number, never rounded |
| `regular_price` | {facts['regular_price_populated']} | {facts['regular_price_blank']} | `final_price`, zeros added to two decimals, never rounded |

The brief's own `unit_price` column stays blank, and no other field changed. The
24 October file is unchanged. `FIELD_PROVENANCE.json` names, per value, the source field,
the snapshot row and the provider statement.

## What is still unevidenced

- **`ppm` is composed, not captured.** The brief asks for PPM exactly as displayed. These
  strings are assembled from two fields and are in dollars. The two page observations
  render cents: `86.8 ¢/lb`, captured at a Sacramento store, and `5.7 c/fl oz`, which
  appears in the provider-ticket note with no capture behind it in this repository.
- **The displayed form of the other units has not been observed.** Units here: {units}.
- **Nothing is shown at store 100.** No page has been observed in store 100's context.
  The provider's account is of its own pipeline, and was not independently checked.
- **`regular_price` is the online price.** The brief asks for the store's pickup or in-store
  price. {facts['populated_where_pickup_not_available']} populated prices are on products not available for pickup at their last observation.
- **{facts['products_with_differing_values_across_snapshots']} products had differing values across snapshots.** The row the submission already
  named was used, and `VALUE_DISAGREEMENTS.json` lists each.
- **Values date from 22 and 23 October.** They have not been refreshed.
- **Client acceptance.** The provider-ticket note says `ppm` stays blank until the provider
  supplies the rendered string, a store 100 page shows the form, or the client accepts a value
  labelled as composed. The first two are unmet, and no acceptance is recorded in this repository.
"""


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("--submission", "--evidence", "--snapshots", "--statement", "--output"):
        p.add_argument(name, required=True)
    args = p.parse_args(argv)
    output = Path(args.output)
    if output.exists():
        print(f"REFUSED: {output} exists", file=sys.stderr)
        return 1
    try:
        original = json.loads(Path(args.submission).read_text(encoding="utf-8"))
        statement = sha256(Path(args.statement).read_bytes()).hexdigest()
        evidence = json.loads(Path(args.evidence).read_text(encoding="utf-8"))
        composed, provenance, disagreements = compose(original, evidence, args.snapshots, statement)
        check(original, composed)
    except CompositionRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    facts = summary(composed, provenance, disagreements)
    output.mkdir(parents=True)
    write = lambda name, value: (output / name).write_text(
        json.dumps(value, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    write("Walmart_Store100_615_Trial_22Field.json", composed)
    write("FIELD_PROVENANCE.json", provenance)
    write("VALUE_DISAGREEMENTS.json", disagreements)
    write("SUMMARY.json", {**facts, "input_sha256": sha256(Path(args.submission).read_bytes()).hexdigest()})
    (output / "NOTE.md").write_text(note(facts), encoding="utf-8")
    print(json.dumps(facts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
