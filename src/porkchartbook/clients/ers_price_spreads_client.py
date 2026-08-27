"""
ers_price_spreads_client.py — USDA ERS Meat Price Spreads for pork.

Two keyless CSVs from the ERS Meat Price Spreads data product, because neither
one alone covers the full series:

  * HISTORICAL (media/5028) — beef/pork/broiler, monthly since 1970, full
    floating-point precision. ERS only rebuilds this file occasionally: as of
    Aug 2026 it still ended at Dec 2025, which is what silently froze this
    series for eight months.
  * CURRENT (media/5026) — pork only, monthly for roughly the trailing two
    years plus quarterly/annual aggregates, rounded to 1 decimal. This is the
    file ERS actually refreshes every month.

We use HISTORICAL as the backbone and CURRENT only to fill months HISTORICAL
does not yet cover, so the long history keeps its precision and the recent
months stay fresh. On the overlap the two agree to within rounding (max 0.09
cents) for every series except one — see CURRENT_ITEMS below.

All values are in **cents per pound of retail equivalent** — i.e. already on a
common retail-weight basis, so farm/wholesale/retail levels and the spreads are
directly comparable.

Failures raise SpreadsFetchError rather than returning []: a silent [] made
`ingest_ers_price_spreads` upsert zero rows and report a clean run while the
database kept serving stale data.
"""

from __future__ import annotations

import csv
from urllib.request import Request, urlopen


class SpreadsFetchError(RuntimeError):
    """Raised when the ERS price-spread CSVs cannot be fetched or yield no rows."""


HISTORICAL_CSV_URL = (
    "https://ers.usda.gov/media/5028/"
    "historical-monthly-price-spread-data-for-beef-pork-broilers.csv"
)
CURRENT_CSV_URL = "https://ers.usda.gov/media/5026/pork-values-and-spreads.csv"

# Backwards-compatible alias — this used to be the only URL.
SPREADS_CSV_URL = HISTORICAL_CSV_URL

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

# The CURRENT file relabels every series, and calls byproduct value an
# "allowance". It also carries percent-share and live-hog-price rows we skip.
#
# "Pork price spread: farm to wholesale" is deliberately absent: in the
# published file that row is corrupt — it repeats the value of "Pork
# farm-wholesale spread share of retail value" (a percent) in a cents column,
# for all 24 months on file. E.g. Sep 2025 reports 16.9 where wholesale minus
# net farm is 85.9, and the historical file independently says 85.95. We
# reconstruct it from the identity below instead.
CURRENT_ITEMS = {
    "Pork gross farm value": "gross_farm_value",
    "Pork net farm value": "net_farm_value",
    "Pork wholesale value": "wholesale_value",
    "Pork retail value": "retail_value",
    "Pork price spread: wholesale to retail": "wholesale_to_retail_spread",
    "Pork price spread: farm to retail": "farm_to_retail_spread",
    "Pork byproduct allowance": "byproduct_value",
}

# ERS's own definition, exact to floating point across all 672 months of the
# historical file, so it is a reconstruction and not an approximation.
DERIVED_SPREAD = ("farm_to_wholesale_spread", "wholesale_value", "net_farm_value")


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


def _fetch_csv(url, label):
    print(f"  [ERS-spreads] Downloading {label} price-spread CSV: {url}")
    try:
        return _request_text(url)
    except Exception as exc:  # noqa: BLE001 — any failure here means stale data
        raise SpreadsFetchError(f"{label} CSV fetch failed ({url}): {exc}") from exc


def _row(report_month, item, value, unit, url):
    return {
        "report_month": report_month,
        "item": item,
        "value": value,
        "unit": unit,
        "source_url": url,
    }


def _parse_historical(text, url):
    """Parse media/5028: columns Year, Month, Month-number, Data_Item, Value, Units."""
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
        rows.append(_row(f"{year:04d}-{month:02d}", item,
                         _safe_float(record.get("Value")),
                         (record.get("Units") or "").strip(), url))
    return rows


def _parse_current(text, url):
    """Parse media/5026: columns Year, Period, Period_Number, Data_Item, Value, Units.

    Period_Number 1-12 are months; 13-16 are quarters and 17 is annual, which we
    drop so only monthly observations reach the monthly table. Fills in
    farm_to_wholesale_spread from the wholesale/net-farm identity because the
    published column is corrupt.
    """
    by_month = {}
    units = {}
    for record in csv.DictReader(text.splitlines()):
        item = CURRENT_ITEMS.get((record.get("Data_Item") or "").strip())
        if not item:
            continue
        try:
            year = int(record["Year"])
            period = int(record["Period_Number"])
        except (TypeError, ValueError, KeyError):
            continue
        if not 1 <= period <= 12:
            continue  # quarterly / annual aggregate
        by_month.setdefault(f"{year:04d}-{period:02d}", {})[item] = _safe_float(record.get("Value"))
        units[item] = (record.get("Units") or "").strip()

    derived_item, minuend, subtrahend = DERIVED_SPREAD
    rows = []
    for report_month, values in sorted(by_month.items()):
        for item, value in sorted(values.items()):
            rows.append(_row(report_month, item, value, units.get(item, ""), url))
        left, right = values.get(minuend), values.get(subtrahend)
        if left is not None and right is not None:
            rows.append(_row(report_month, derived_item, round(left - right, 4),
                             units.get(minuend, ""), url))
    return rows


def fetch_pork_spreads(csv_url=None, current_csv_url=None):
    """Fetch and parse the monthly pork price-spread series.

    Returns a flat list of {report_month, item, value, unit, source_url} rows
    ready for db.upsert_rows into ers_price_spreads. Raises SpreadsFetchError if
    either CSV cannot be fetched or the merged result is empty.
    """
    hist_url = csv_url or HISTORICAL_CSV_URL
    curr_url = current_csv_url or CURRENT_CSV_URL

    historical = _parse_historical(_fetch_csv(hist_url, "historical"), hist_url)
    hist_months = {r["report_month"] for r in historical}
    print(f"  [ERS-spreads] Parsed {len(historical)} historical pork rows"
          f" (through {max(hist_months, default='n/a')})")

    current = _parse_current(_fetch_csv(curr_url, "current"), curr_url)
    curr_months = {r["report_month"] for r in current}
    print(f"  [ERS-spreads] Parsed {len(current)} current pork rows"
          f" (through {max(curr_months, default='n/a')})")

    # Historical wins on the overlap: same values, more precision.
    fresh = [r for r in current if r["report_month"] not in hist_months]
    if fresh:
        added = sorted({r["report_month"] for r in fresh})
        print(f"  [ERS-spreads] {len(fresh)} rows for {len(added)} month(s)"
              f" beyond the historical file: {added[0]}..{added[-1]}")
    else:
        print("  [ERS-spreads] Historical file already covers every current month")

    rows = historical + fresh
    if not rows:
        raise SpreadsFetchError(
            f"parsed 0 pork price-spread rows — check the ERS Data_Item labels "
            f"in {hist_url} and {curr_url}"
        )
    print(f"  [ERS-spreads] Parsed {len(rows)} pork price-spread rows"
          f" (through {max(r['report_month'] for r in rows)})")
    return rows
