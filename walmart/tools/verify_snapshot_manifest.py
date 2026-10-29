"""Verify archived provider snapshots against a recorded SHA-256 manifest.

Offline only. Makes no retailer, provider or cloud request. Use this before
rebuilding any ledger from the snapshots, so a ledger is never built on
inputs that have been altered since they were archived.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys


def digest(path: Path) -> str:
    h = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def verify(snapshots: Path, manifest_path: Path):
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = manifest.get("originals", manifest if isinstance(manifest, list) else [])
    ok, bad, missing = [], [], []
    for entry in entries:
        target = snapshots / entry["file"]
        if not target.is_file():
            missing.append(entry["file"])
            continue
        actual = digest(target)
        if actual == entry["sha256"]:
            ok.append(entry["file"])
        else:
            bad.append({"file": entry["file"],
                        "recorded_sha256": entry["sha256"],
                        "actual_sha256": actual})
    return ok, bad, missing


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--snapshots", type=Path, required=True, help="Directory holding the archived snapshots")
    p.add_argument("--manifest", type=Path, required=True, help="MANIFEST_SHA256.json recorded when they were archived")
    args = p.parse_args(argv)

    ok, bad, missing = verify(args.snapshots, args.manifest)
    for name in ok:
        print(f"OK       {name}")
    for item in bad:
        print(f"ALTERED  {item['file']}  recorded={item['recorded_sha256'][:16]}... actual={item['actual_sha256'][:16]}...")
    for name in missing:
        print(f"MISSING  {name}")
    print(f"\n{len(ok)} verified, {len(bad)} altered, {len(missing)} missing")
    if bad or missing:
        print("Do not rebuild a ledger from this directory until it matches the manifest.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
