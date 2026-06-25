"""
ers_price_spreads_client.py — USDA ERS Meat Price Spreads for pork.

Source (keyless): ERS historical monthly price-spread CSV
  https://ers.usda.gov/media/5028/historical-monthly-price-spread-data-for-beef-pork-broilers.csv

Tidy long format (Year, Month, Month-number, Data_Item, Value, Units), monthly
since 1970, mixing beef / pork / broiler series. We keep the eight pork series.
All values are in **cents per pound of retail equivalent** — i.e. already on a
common retail-weight basis, so farm/wholesale/retail levels and the spreads are
directly comparable.
"""

from __future__ import annotations

import csv
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SPREADS_CSV_URL = (
    "https://ers.usda.gov/media/5028/"
    "historical-monthly-price-spread-data-for-beef-pork-broilers.csv"
)

# Exact ERS Data_Item strings -> normalized keys. NOTE the capital "W" in the
# wholesale-to-retail label — every other pork label is lowercase; matching it
# wrong silently drops that series.
PORK_ITEMS = {
    "Pork gross farm value": "gross_farm_value",
    "Pork net farm value": "net_farm_value",
    "Pork wholesale value": "wholesale_value",
    "Pork retail value": "retail_value",
    "Pork farm to wholesale price spread": "farm_to_wholesale_spread",
    "Pork Wholesale to retail price spread": "wholesale_to_retail_spread",
    "Pork farm to retail price spread": "farm_to_retail_spread",
    "Pork byproduct value": "byproduct_value",
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
        # File is UTF-8 with a BOM; strip it so the first header parses cleanly.
        return response.read().decode("utf-8-sig", "replace")


def fetch_pork_spreads(csv_url=None):
    """Fetch and parse the monthly pork price-spread series.

    Returns a flat list of {report_month, item, value, unit, source_url} rows
    ready for db.upsert_rows into ers_price_spreads. Returns [] on failure.
    """
    url = csv_url or SPREADS_CSV_URL
    print(f"  [ERS-spreads] Downloading price-spread CSV: {url}")
    try:
        text = _request_text(url)
    except (HTTPError, URLError, Exception) as exc:
        print(f"  [ERS-spreads] fetch failed: {exc}")
        return []

    rows = []
    for record in csv.DictReader(text.splitlines()):
        item = PORK_ITEMS.get((record.get("Data_Item") or "").strip())
        if not item:
            continue
        try:
            year = int(record["Year"])
            month = int(record["Month-number"])
        except (TypeError, ValueError, KeyError):
            continue
        rows.append({
            "report_month": f"{year:04d}-{month:02d}",
            "item": item,
            "value": _safe_float(record.get("Value")),
            "unit": (record.get("Units") or "").strip(),
            "source_url": url,
        })
    print(f"  [ERS-spreads] Parsed {len(rows)} pork price-spread rows")
    return rows
