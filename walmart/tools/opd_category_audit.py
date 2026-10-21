"""Compare supplied Walmart category URLs against an authenticated OPD taxonomy dump.

This is a diagnostic, not an automatic assertion of full website category coverage.
Run after obtaining taxonomy JSON from the approved Walmart OPD taxonomy API.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


def flatten(nodes, ancestors=()):
    if not isinstance(nodes, list):
        raise ValueError("Taxonomy categories must be an array")
    for node in nodes:
        if not isinstance(node, dict) or not node.get("id") or not node.get("name"):
            raise ValueError("Malformed taxonomy node")
        path = (*ancestors, str(node["name"]))
        yield {"id":str(node["id"]), "name":str(node["name"]), "path":"/".join(path)}
        yield from flatten(node.get("children", []), path)


def category_id(url):
    last = urlparse(url).path.strip("/").split("/")[-1]
    return last if last and all(x.isdigit() for x in last.split("_")) else ""


def audit(taxonomy, rows):
    nodes = list(flatten(taxonomy.get("categories")))
    output = []
    for row in rows:
        requested_id = category_id(row["URL"])
        direct = [x for x in nodes if x["id"] == requested_id]
        suffix = [x for x in nodes if x["id"].split("_")[-1] == requested_id.split("_")[-1] and x not in direct] if requested_id else []
        output.append({
            "category":row["Category (Auto)"], "url_id":requested_id,
            "direct_matches":direct, "suffix_candidates":suffix[:15],
            "status":"MATCH_CANDIDATE_VERIFY_PATH" if direct else "MANUAL_MAPPING_REQUIRED",
            "important":"Node ID match does not prove all requested subcategories, eligible pickup products, or promotions were covered"
        })
    return {"categories":output, "all_category_paths_confirmed":False,
            "approved_for_contest":False,
            "explanation":"An operator must compare Walmart website category hierarchies, excluded sections, and OPD coverage."}


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--taxonomy-file", type=Path, required=True,
                   help="JSON taxonomy retrieved using approved Walmart access")
    p.add_argument("--categories",type=Path,default=ROOT/"config/categories.csv")
    p.add_argument("--output",type=Path,default=ROOT/"client-test-output/opd-taxonomy-audit.json")
    a=p.parse_args(argv)
    with a.categories.open(encoding="utf-8-sig",newline="") as f:
        rows=list(csv.DictReader(f))
    result=audit(json.loads(a.taxonomy_file.read_text(encoding="utf-8")),rows)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"output":str(a.output),"categories":len(rows),
                      "requiring_manual_audit":sum(x["status"]=="MANUAL_MAPPING_REQUIRED" for x in result["categories"]),
                      "approved_for_contest":False},indent=2))
    return 0

if __name__ == "__main__":raise SystemExit(main())
