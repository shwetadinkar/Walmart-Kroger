"""Verify archived provider snapshots against a recorded SHA-256 manifest.

Offline only. Makes no retailer, provider or cloud request. Run this before
rebuilding any ledger from the snapshots, so a ledger is never built on inputs
that have been altered since they were archived.

Manifest formats accepted
-------------------------
Distributed packages redact unrelated customer-review content from the provider
responses, so a package records two hashes per file: ``original_sha256`` for the
untouched download and ``redacted_sha256`` for the copy actually shipped. This
tool verifies the files it is given, so it prefers ``redacted_sha256`` when the
manifest carries one and falls back to ``sha256``.

  {"files":     [{"file": ..., "redacted_sha256": ..., "original_sha256": ...}]}
  {"originals": [{"file": ..., "sha256": ...}]}
  [{"file": ..., "sha256": ...}]

An empty or unrecognised manifest is an error, not a pass.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

HASH_KEYS = ("redacted_sha256", "sha256", "original_sha256")


class ManifestError(Exception):
    """The manifest cannot be interpreted, so nothing can be verified."""


def digest(path: Path) -> str:
    h = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_entries(manifest):
    """Return (entries, hash_key). Raises ManifestError rather than verifying nothing."""
    if isinstance(manifest, list):
        entries = manifest
    elif isinstance(manifest, dict):
        for container in ("files", "originals", "entries"):
            if isinstance(manifest.get(container), list):
                entries = manifest[container]
                break
        else:
            raise ManifestError(
                "Unrecognised manifest: expected a list, or an object with a "
                "'files' or 'originals' list. Found keys: "
                + ", ".join(sorted(manifest)) or "none")
    else:
        raise ManifestError(f"Unrecognised manifest of type {type(manifest).__name__}")

    entries = [e for e in entries if isinstance(e, dict) and e.get("file")]
    if not entries:
        raise ManifestError("Manifest lists no files, so there is nothing to verify")

    for key in HASH_KEYS:
        if all(e.get(key) for e in entries):
            return entries, key
    present = sorted({k for e in entries for k in e if k.endswith("sha256")})
    raise ManifestError(
        "No hash field is present on every entry. Looked for "
        + ", ".join(HASH_KEYS) + "; entries carry: " + (", ".join(present) or "none"))


def verify(snapshots: Path, manifest_path: Path):
    if not manifest_path.is_file():
        raise ManifestError(f"Manifest not found: {manifest_path}")
    if not snapshots.is_dir():
        raise ManifestError(f"Snapshot directory not found: {snapshots}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ManifestError(f"Manifest is not valid JSON: {exc}") from exc

    entries, key = load_entries(manifest)
    ok, altered, missing = [], [], []
    for entry in entries:
        target = snapshots / entry["file"]
        if not target.is_file():
            missing.append(entry["file"])
            continue
        actual = digest(target)
        if actual == entry[key]:
            ok.append(entry["file"])
        else:
            altered.append({"file": entry["file"], "recorded": entry[key], "actual": actual})
    return ok, altered, missing, key


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--snapshots", type=Path, required=True,
                   help="Directory holding the archived snapshots")
    p.add_argument("--manifest", type=Path, required=True,
                   help="MANIFEST_SHA256.json recorded when they were archived")
    p.add_argument("--quiet", action="store_true", help="Print only the summary and failures")
    args = p.parse_args(argv)

    try:
        ok, altered, missing, key = verify(args.snapshots, args.manifest)
    except ManifestError as exc:
        print(f"MANIFEST ERROR: {exc}", file=sys.stderr)
        print("Nothing was verified. This is a failure, not a pass.", file=sys.stderr)
        return 2

    print(f"Verifying against '{key}'.\n")
    if not args.quiet:
        for name in ok:
            print(f"OK       {name}")
    for item in altered:
        print(f"ALTERED  {item['file']}  recorded={item['recorded'][:16]}... "
              f"actual={item['actual'][:16]}...")
    for name in missing:
        print(f"MISSING  {name}")

    print(f"\n{len(ok)} verified, {len(altered)} altered, {len(missing)} missing")
    if altered or missing:
        print("Do not rebuild a ledger from this directory until it matches the manifest.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
