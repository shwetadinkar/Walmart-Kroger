"""Strict, data-file based configuration. Preserve the client's category URLs."""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

class ConfigError(ValueError):
    pass

@dataclass(frozen=True)
class Store:
    store_id: str
    zipcode: str
    store_name: str
    store_location: str
    store_logo: str = ""

@dataclass(frozen=True)
class Category:
    name: str
    url: str
    exclusions: tuple[str, ...] = ()
    @property
    def slug(self) -> str:
        return re.sub(r"[^a-z0-9]+", "-", self.name.lower()).strip("-")


def check_retailer_url(url: str) -> None:
    p = urlparse(url)
    if p.scheme != "https" or not p.hostname or not (p.hostname == "walmart.com" or p.hostname.endswith(".walmart.com")):
        raise ConfigError(f"Not a Walmart HTTPS category URL: {url!r}")


def categories_from_csv(path: Path) -> list[Category]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        required = {"Retailer", "Category (Auto)", "URL", "Scope", "Notes"}
        if not required.issubset(set(reader.fieldnames or [])):
            raise ConfigError("Category CSV is missing columns")
        rows = list(reader)
    if not rows:
        raise ConfigError("Empty category CSV")
    result = []
    for row in rows:
        if row["Retailer"].strip().lower() != "walmart":
            raise ConfigError("Category CSV includes a non-Walmart row")
        name = row["Category (Auto)"].strip()
        url = row["URL"].strip()
        check_retailer_url(url)
        notes = row["Notes"].lower()
        exclusions: tuple[str, ...] = ()
        if name == "Food":
            if "shop all foods" not in notes or "recipes" not in notes:
                raise ConfigError("Food exclusion notes changed; review CSV")
            exclusions = ("shop all foods", "recipes")
        elif name == "Pets":
            if "farm animals" not in notes:
                raise ConfigError("Pets exclusion notes changed; review CSV")
            exclusions = ("farm animals",)
        result.append(Category(name, url, exclusions))
    if len({c.name for c in result}) != len(result):
        raise ConfigError("Duplicate category names")
    return result


def stores_from_json(path: Path) -> list[Store]:
    document = json.loads(path.read_text(encoding="utf-8"))
    seen = set()
    result = []
    for item in document["stores"]:
        if not item.get("enabled", True):
            continue
        s = Store(**{k: str(item.get(k, "")) for k in Store.__dataclass_fields__})
        if not (re.fullmatch(r"\d{5}", s.zipcode) and s.store_id and s.store_name and s.store_location):
            raise ConfigError(f"Invalid store configuration: {item}")
        if s.store_id in seen:
            raise ConfigError(f"Repeated store ID {s.store_id}")
        seen.add(s.store_id)
        result.append(s)
    if not result:
        raise ConfigError("No enabled stores")
    return result


def is_excluded_subcategory(name: str, exclusions: tuple[str, ...]) -> bool:
    # Compare leaf label, not the whole breadcrumb, to avoid excluding legitimate children.
    normalized = re.sub(r"\s+", " ", name.strip().lower())
    return any(normalized == e or normalized.startswith(e + " ") for e in exclusions)
