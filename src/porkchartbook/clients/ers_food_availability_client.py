"""
ers_food_availability_client.py — US per-capita pork availability and the pork
supply-and-use (domestic disappearance) balance sheet, from the USDA ERS
"Food Availability (Per Capita) Data System".

Source (keyless, no login):
  Landing: https://www.ers.usda.gov/data-products/food-availability-per-capita-data-system
  CSV:     red-meat-beef-veal-pork-lamb-and-mutton.csv

The CSV is a tidy long table: Commodity, Year, Attribute, Value, Notes. The pork
rows (Commodity == "Pork: Supply and use - carcass weight") carry the full
balance sheet — production, imports, stocks, exports, shipments — plus the
computed food availability (= domestic disappearance) and per-capita series.

Cadence: ANNUAL. As of this writing the file spans 1909–2021 and lags ~1.5 years
(ERS last re-versioned it in late 2022). It is the authoritative historical
per-capita / disappearance series; current-year figures would need WASDE/PSD.
"""

from __future__ import annotations

import csv
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ERS_FOOD_AVAIL_PAGE = (
    "https://www.ers.usda.gov/data-products/food-availability-per-capita-data-system"
)
# The "?v=" suffix is a cache-buster baked into the ERS link; the bare URL also
# resolves. Update the media id if ERS re-publishes under a new path.
REDMEAT_CSV_URL = (
    "https://www.ers.usda.gov/media/5361/"
    "red-meat-beef-veal-pork-lamb-and-mutton.csv?v=51529"
)

PORK_COMMODITY = "Pork: Supply and use - carcass weight"
BEEF_COMMODITY = "Beef: Supply and use - carcass weight"
# Chicken per-capita lives in the separate poultry file.
POULTRY_CSV_URL = (
    "https://www.ers.usda.gov/media/5359/poultry-chicken-and-turkey.csv"
)
CHICKEN_COMMODITY = "Total chicken: Supply and use"

# Per-capita availability attributes (boneless / retail / carcass, lb/person/yr).
PER_CAPITA_ATTRS = {
    "Food availability-Per capita availability-Boneless-Pounds",
    "Food availability-Per capita availability-Retail-Pounds",
    "Food availability-Per capita availability-Carcass-Pounds",
}


def _safe_float(value):
    value = (value or "").strip()
    if value in ("", "NA", "-", "."):
        return None
    try:
        return float(value.replace(",", ""))
    except (TypeError, ValueError):
        return None


def _request_text(url):
    request = Request(url, headers={"User-Agent": "porkchartbook/1.0", "Accept": "text/csv"})
    with urlopen(request, timeout=90) as response:
        return response.read().decode("utf-8", "replace").lstrip("﻿")


def fetch_pork_rows(csv_url=None):
    """Fetch and parse the pork supply-and-use rows from the ERS red-meat CSV.

    Returns a flat list of {commodity, year, attribute, value, source_url} rows
    ready for db.upsert_rows into ers_food_availability.
    """
    url = csv_url or REDMEAT_CSV_URL
    print(f"  [ERS-food] Downloading red-meat availability CSV: {url}")
    try:
        text = _request_text(url)
    except (HTTPError, URLError, Exception) as exc:
        print(f"  [ERS-food] fetch failed: {exc}")
        return []

    rows = []
    for record in csv.reader(text.splitlines()):
        if len(record) < 4 or record[0] != PORK_COMMODITY:
            continue
        try:
            year = int(record[1])
        except (TypeError, ValueError):
            continue
        rows.append({
            "commodity": "pork",
            "year": year,
            "attribute": record[2].strip(),
            "value": _safe_float(record[3]),
            "source_url": url,
        })
    print(f"  [ERS-food] Parsed {len(rows)} pork rows")
    return rows


def _rows_from_csv(text, commodity_filter, out_commodity, url, attr_filter=None):
    """Extract {commodity,year,attribute,value,source_url} rows for one commodity
    from an ERS Food Availability CSV, optionally restricted to attr_filter."""
    rows = []
    for record in csv.reader(text.splitlines()):
        if len(record) < 4 or record[0] != commodity_filter:
            continue
        attribute = record[2].strip()
        if attr_filter is not None and attribute not in attr_filter:
            continue
        try:
            year = int(record[1])
        except (TypeError, ValueError):
            continue
        rows.append({
            "commodity": out_commodity,
            "year": year,
            "attribute": attribute,
            "value": _safe_float(record[3]),
            "source_url": url,
        })
    return rows


def fetch_meat_rows():
    """Fetch ERS per-capita availability for pork (full supply-and-use), plus
    per-capita series for beef (red-meat file) and chicken (poultry file).

    Returns a flat list of ers_food_availability rows (commodity in
    {pork, beef, chicken}). Each source file is downloaded once.
    """
    rows = []
    try:
        red_meat = _request_text(REDMEAT_CSV_URL)
        rows += _rows_from_csv(red_meat, PORK_COMMODITY, "pork", REDMEAT_CSV_URL)
        rows += _rows_from_csv(red_meat, BEEF_COMMODITY, "beef", REDMEAT_CSV_URL, PER_CAPITA_ATTRS)
    except (HTTPError, URLError, Exception) as exc:
        print(f"  [ERS-food] red-meat fetch failed: {exc}")
    try:
        poultry = _request_text(POULTRY_CSV_URL)
        rows += _rows_from_csv(poultry, CHICKEN_COMMODITY, "chicken", POULTRY_CSV_URL, PER_CAPITA_ATTRS)
    except (HTTPError, URLError, Exception) as exc:
        print(f"  [ERS-food] poultry fetch failed: {exc}")
    by_commodity = {}
    for row in rows:
        by_commodity[row["commodity"]] = by_commodity.get(row["commodity"], 0) + 1
    print(f"  [ERS-food] Parsed {len(rows)} rows ({by_commodity})")
    return rows
