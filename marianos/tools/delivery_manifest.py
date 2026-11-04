#!/usr/bin/env python3
"""Emit the revision/hash manifest and the change-to-test map.

Both were asked for by the client on 4 November, to accompany the next update.

**The manifest** records the git revision the delivery was built from and the
SHA-256 of every delivered file, so the client can verify that what he holds is
what this revision produces.

**The change-to-test map** is derived, not written. For each commit since the
revision the client last reviewed, it lists the non-test files changed and the
test files that exercise them, where "exercises" means a test module imports
that module. A changed source file that no test imports is reported as
`NO TEST IMPORTS THIS`, in its own section, because that is the only part of
such a map worth reading. A hand-written map would drift from the code and has
already done so once in this repository: a release note stated a test count and
a property that were both false and falsifiable in one command.

The map says which tests *cover* a module by import. It does not claim they
assert the behaviour a given commit changed; that is what the mutation checks
in the commit messages are for, and this tool does not restate them.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import textwrap
from pathlib import Path

IMPORT = re.compile(
    r"^\s*(?:from\s+([A-Za-z_][\w.]*)\s+import|import\s+([A-Za-z_][\w.]*))",
    re.M)


def P(text):
    return textwrap.fill(" ".join(text.split()), width=79)


def git(repo, *args):
    out = subprocess.run(["git", "-C", str(repo), *args],
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


def git_raw(repo, *args):
    """git output with no stripping.

    `git status --porcelain` encodes the status in the first two columns, and
    an unstaged modification leaves column one blank: " M pkg/thing.py". So
    stripping the whole output removes the leading space of the first line
    only, and that line's path then loses its first character. It produced
    "kg/thing.py" for "pkg/thing.py" on exactly one file per run, which is the
    kind of defect a count never shows.
    """
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, check=True).stdout


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def module_names(path):
    """The module names a file defines, as a test would import them."""
    parts = Path(path).with_suffix("").parts
    names = {parts[-1]}
    for i in range(len(parts)):
        names.add(".".join(parts[i:]))
    return names


def test_index(repo, test_dirs):
    """module name -> set of test files importing it."""
    index = {}
    for rel in test_dirs:
        root = Path(repo) / rel
        if not root.is_dir():
            continue
        for test in sorted(root.glob("test_*.py")):
            text = test.read_text(encoding="utf-8", errors="replace")
            for a, b in IMPORT.findall(text):
                name = a or b
                index.setdefault(name, set()).add(
                    str(test.relative_to(repo)))
                index.setdefault(name.split(".")[-1], set()).add(
                    str(test.relative_to(repo)))
    return index


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--repo", default=".", help="Repository root")
    p.add_argument("--since", required=True,
                   help="The revision the client last reviewed")
    p.add_argument("--delivery", action="append", default=[],
                   help="A delivered file or directory to hash. Repeatable.")
    p.add_argument("--test-dir", action="append",
                   default=["marianos/tests", "walmart/tests"])
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)

    repo = Path(a.repo).resolve()
    head = git(repo, "rev-parse", "HEAD")
    branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    dirty = git_raw(repo, "status", "--porcelain")

    # A bare working_tree_clean: false tells a reviewer that something was
    # uncommitted and not what, which invites exactly the question the manifest
    # exists to answer. Untracked output directories are the normal case and
    # say nothing about whether the revision describes the source; a modified
    # tracked file is the case that matters, because then the revision does
    # not describe what produced the delivery. They are reported separately.
    untracked, modified = [], []
    for line in dirty.splitlines():
        if not line.strip():
            continue
        status, path = line[:2].strip(), line[3:].strip()
        (untracked if status == "??" else modified).append(
            {"status": status, "path": path})

    index = test_index(repo, a.test_dir)

    log = git(repo, "log", "--reverse", "--format=%H%x1f%s", f"{a.since}..HEAD")
    commits = []
    uncovered = {}
    for line in [x for x in log.splitlines() if x.strip()]:
        sha, subject = line.split("\x1f", 1)
        files = git(repo, "show", "--name-only", "--format=", sha).splitlines()
        files = [f for f in files if f.strip()]
        src = [f for f in files
               if f.endswith(".py") and "/tests/" not in f and
               not Path(f).name.startswith("test_")]
        tests_touched = sorted(f for f in files
                               if "/tests/" in f or Path(f).name.startswith("test_"))
        covering = {}
        for f in src:
            found = set()
            for name in module_names(f):
                found |= index.get(name, set())
            covering[f] = sorted(found)
            if not found:
                uncovered.setdefault(f, []).append(sha[:9])
        commits.append({
            "revision": sha,
            "subject": subject,
            "source_files_changed": src,
            "test_files_changed": tests_touched,
            "tests_importing_each_source_file": covering,
            "other_files_changed": sorted(
                f for f in files if f not in src and f not in tests_touched),
        })

    delivered = []
    for item in a.delivery:
        path = Path(item)
        targets = sorted(x for x in path.rglob("*") if x.is_file()) \
            if path.is_dir() else ([path] if path.is_file() else [])
        for t in targets:
            delivered.append({
                "path": str(t),
                "bytes": t.stat().st_size,
                "sha256": sha256(t),
            })

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = {
        "revision": head,
        "branch": branch,
        "working_tree_clean": not dirty,
        # The one that matters: if this is non-empty, the revision above does
        # not describe the source that produced the delivery.
        "modified_tracked_files": modified,
        "modified_tracked_file_count": len(modified),
        "untracked_paths": [x["path"] for x in untracked],
        "untracked_path_count": len(untracked),
        "_working_tree_note": (
            "Untracked paths are normally the run outputs being delivered and "
            "do not affect whether the revision describes the source. A "
            "non-empty modified_tracked_files means it does not."),
        "reviewed_revision": git(repo, "rev-parse", a.since),
        "commits_since_reviewed_revision": len(commits),
        "delivered_files": delivered,
        "delivered_file_count": len(delivered),
        "_verify_with":
            "sha256sum -c, or recompute per file; the revision above is what "
            "these files were built from",
        "_does_not_establish": [
            "That the delivered content is correct. A hash establishes which "
            "bytes were delivered, nothing about whether the values in them "
            "are right.",
            "That the working tree matched the revision, unless "
            "working_tree_clean is true.",
        ],
    }
    (out / "REVISION_MANIFEST.json").write_text(
        json.dumps(manifest, indent=1), encoding="utf-8")
    (out / "CHANGE_TO_TEST_MAP.json").write_text(
        json.dumps({"since": a.since, "head": head, "commits": commits},
                   indent=1), encoding="utf-8")

    lines = [
        "# Change-to-test map",
        "",
        P(f"Revision `{head[:9]}` on `{branch}`. "
          f"{len(commits)} commits since `{git(repo, 'rev-parse', '--short', a.since)}`, "
          f"the revision last reviewed."
          + ("" if not dirty else
             (f" {len(modified)} tracked file(s) MODIFIED and not committed, so "
              f"this revision does not describe the source that produced the "
              f"delivery."
              if modified else
              f" {len(untracked)} untracked path(s) present, which are the run "
              f"outputs; no tracked file is modified, so the revision does "
              f"describe the source."))),
        "",
        P("Derived by reading which test modules import each changed module, "
          "not written by hand. It says which tests exercise a module. It does "
          "not claim they assert the specific behaviour a commit changed."),
        "",
    ]
    for c in commits:
        lines += [f"## `{c['revision'][:9]}` {c['subject']}", ""]
        if not c["source_files_changed"]:
            lines += ["No source files changed in this commit.", ""]
        for f, tests in c["tests_importing_each_source_file"].items():
            if tests:
                lines.append(f"- `{f}`")
                for t in tests:
                    lines.append(f"    - `{t}`")
            else:
                lines.append(f"- `{f}` — **NO TEST IMPORTS THIS**")
        if c["test_files_changed"]:
            lines += ["", "Tests changed in the same commit:"]
            lines += [f"    - `{t}`" for t in c["test_files_changed"]]
        lines.append("")

    if uncovered:
        lines += ["## Changed source files no test imports", "",
                  P("This is the part of this map worth reading."), ""]
        for f, shas in sorted(uncovered.items()):
            lines.append(f"- `{f}` (in {', '.join(shas)})")
        lines.append("")
    else:
        lines += ["## Changed source files no test imports", "",
                  "None. Every source file changed since the reviewed "
                  "revision is imported by at least one test module.", ""]

    (out / "CHANGE_TO_TEST_MAP.md").write_text("\n".join(lines) + "\n",
                                               encoding="utf-8")
    print(json.dumps({k: v for k, v in manifest.items()
                      if k != "delivered_files"}, indent=1))
    print(f"\nuncovered changed source files: {len(uncovered)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
