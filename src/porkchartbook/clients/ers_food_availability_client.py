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
