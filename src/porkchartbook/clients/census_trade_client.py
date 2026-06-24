"""
census_trade_client.py — US pork trade (product weight) by HS code from the
U.S. Census Bureau International Trade API.

Why this exists
---------------
The ERS monthly pork workbook is published in **carcass weight**, which is not
comparable to Brazil's Comex Stat exports (**product weight**). The Census
International Trade API reports actual shipped quantities by Harmonized System
(HS) code in **product weight** (kilograms), so it gives:

  * a US pork export total in product weight directly comparable to Brazil
    (sum of the fresh/frozen HS 0203 group — the same scope as the Brazil
    "in natura" line), and
  * a US import breakdown by HS product/cut (top import cuts), which the ERS
    by-country workbook cannot provide.

The HS groups below mirror ``comexstat_client.PORK_NCM`` (Comex uses the 8-digit
Mercosur NCM; Census uses the 6-digit HS, and the first 6 digits are the shared
international HS code) so the two sources aggregate into the same categories.

API
---
  GET https://api.census.gov/data/timeseries/intltrade/exports/hs
  GET https://api.census.gov/data/timeseries/intltrade/imports/hs

Both require a free API key (register at
https://api.census.gov/data/key_signup.html). The key is read from the
``CENSUS_API_KEY`` environment variable; if it is unset, the client degrades
gracefully (returns no rows) so the rest of the pipeline is unaffected.

Quantity 1 (``QTY_1_MO`` / ``GEN_QY1_MO``) for these HS chapters is reported in
kilograms (``UNIT_QY1`` == "KG"); the unit string is stored alongside so the
dashboard layer can convert defensively.
"""

from __future__ import annotations

import json
import os
import time
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


EXPORTS_URL = "https://api.census.gov/data/timeseries/intltrade/exports/hs"
IMPORTS_URL = "https://api.census.gov/data/timeseries/intltrade/imports/hs"

# Be a polite client: small pause between calls, back off on transient errors.
REQUEST_DELAY_SEC = 0.5
MAX_RETRIES = 4
BACKOFF_BASE_SEC = 3.0

# Swine-product HS6 codes grouped by category, mirroring comexstat_client.PORK_NCM
# (the first 6 digits of each NCM == the international HS6). Mixed-species sausages
# (1601) are excluded because they are not swine-specific.
PORK_HS6 = [
    # Fresh / chilled / frozen pork meat (HS 0203) — the headline "in natura" group
    {"code": "020311", "category": "fresh_frozen"},  # carcasses/half-carcasses, fresh/chilled
    {"code": "020312", "category": "fresh_frozen"},  # hams/shoulders, bone-in, fresh/chilled
    {"code": "020319", "category": "fresh_frozen"},  # other cuts, fresh/chilled
    {"code": "020321", "category": "fresh_frozen"},  # carcasses/half-carcasses, frozen
    {"code": "020322", "category": "fresh_frozen"},  # hams/shoulders, bone-in, frozen
    {"code": "020329", "category": "fresh_frozen"},  # other cuts, frozen (bulk of trade)
    # Edible swine offal (HS 0206)
    {"code": "020630", "category": "offal"},          # swine offal, fresh/chilled
    {"code": "020641", "category": "offal"},          # swine livers, frozen
    {"code": "020649", "category": "offal"},          # other swine offal, frozen
    # Pig fat, free of lean meat (HS 0209)
    {"code": "020910", "category": "fat"},            # pig fat / back fat
    # Salted, dried or smoked swine meat (HS 0210)
    {"code": "021011", "category": "salted_dried_smoked"},  # hams/shoulders, bone-in
    {"code": "021012", "category": "salted_dried_smoked"},  # bellies (bacon)
    {"code": "021019", "category": "salted_dried_smoked"},  # other
    # Prepared / preserved swine meat (HS 1602.4x)
    {"code": "160241", "category": "prepared"},       # hams and cuts
    {"code": "160242", "category": "prepared"},       # shoulders and cuts
    {"code": "160249", "category": "prepared"},       # other prepared swine, incl. mixtures
]

# Category keyed by the 6-digit HS code. Census reports quantity (weight) only at
# the HS10 (10-digit) detail level — the HS6/HS4 aggregates return value but no
# quantity — so we pull HS10 codes and map each back to its category by 6-digit
# prefix (code[:6]).
_CATEGORY_BY_CODE = {item["code"]: item["category"] for item in PORK_HS6}


def api_key():
    """Return the Census API key from the environment, or None."""
    return os.environ.get("CENSUS_API_KEY") or None


def _safe_float(value):
    if value in (None, "", "."):
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _get(url, params):
    """GET the Census API and return the parsed JSON (a list of rows), retrying
    on transient errors. The first row is the header."""
    query = urlencode(params)
    request = Request(
        f"{url}?{query}",
        headers={"User-Agent": "porkchartbook/1.0", "Accept": "application/json"},
    )
    for attempt in range(MAX_RETRIES):
        try:
            # The HS10 month files are large (imports ~3 MB), so allow a long read.
            with urlopen(request, timeout=180) as response:
                body = response.read().decode("utf-8", "replace")
            if not body.strip():
                return []  # Census returns an empty body for no-data queries
            return json.loads(body)
        except HTTPError as exc:
            # 204/404 == no data for this commodity/period; treat as empty.
            if exc.code in (204, 404):
                return []
            if attempt < MAX_RETRIES - 1:
                time.sleep(BACKOFF_BASE_SEC * (2 ** attempt))
                continue
            raise
        except (URLError, TimeoutError, json.JSONDecodeError):
            if attempt < MAX_RETRIES - 1:
                time.sleep(BACKOFF_BASE_SEC * (2 ** attempt))
                continue
            raise
    return []


def _fetch_flow_month(flow, year_month, key):
    """Fetch one month of all-country pork totals for one flow, at HS10 detail.

    Pulls every HS10 commodity for the month (quantity is only populated at HS10)
    and keeps the swine codes, mapping each to its category by 6-digit prefix.
    """
    is_export = flow == "export"
    base = EXPORTS_URL if is_export else IMPORTS_URL
    comm_var = "E_COMMODITY" if is_export else "I_COMMODITY"
    desc_var = "E_COMMODITY_LDESC" if is_export else "I_COMMODITY_LDESC"
    val_var = "ALL_VAL_MO" if is_export else "GEN_VAL_MO"
    qty_var = "QTY_1_MO" if is_export else "GEN_QY1_MO"

    params = {
        "get": f"{comm_var},{desc_var},{val_var},{qty_var},UNIT_QY1",
        "COMM_LVL": "HS10",
        "CTY_CODE": "-",   # "-" == total for all countries (one row per commodity)
        "time": year_month,
        "key": key,
    }
    rows = _get(base, params)
    if not rows or len(rows) < 2:
        return []

    header = rows[0]
    i_comm = header.index(comm_var)
    i_desc = header.index(desc_var)
    i_val = header.index(val_var)
    i_qty = header.index(qty_var)
    i_unit = header.index("UNIT_QY1")

    out = []
    for row in rows[1:]:
        code = (row[i_comm] or "").strip()
        category = _CATEGORY_BY_CODE.get(code[:6])
        if category is None:
            continue  # not one of our swine HS groups
        out.append({
            "report_month": year_month,
            "flow": flow,
            "hs_code": code,
            "hs_category": category,
            "hs_desc": row[i_desc],
            "value_usd": _safe_float(row[i_val]),
            "net_kg": _safe_float(row[i_qty]),
            "qty_unit": (row[i_unit] or "").strip(),
            "source_url": base,
        })
    return out


def _month_range(year_from, year_to):
    """List of 'YYYY-MM' from year_from-01 through min(year_to-12, current month)."""
    today = date.today()
    months = []
    for year in range(year_from, year_to + 1):
        for month in range(1, 13):
            if (year, month) > (today.year, today.month):
                break
            months.append(f"{year:04d}-{month:02d}")
    return months


def recent_months(n):
    """The most recent n 'YYYY-MM' strings, ending at the current month."""
    today = date.today()
    out = []
    year, month = today.year, today.month
    for _ in range(n):
        out.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    return list(reversed(out))


def fetch_pork_trade(year_from, year_to, flows=("export", "import"), months=None):
    """Fetch US pork trade rows (product weight) by HS10 for the given window.

    Pass an explicit ``months`` list (e.g. from recent_months) to limit the
    window; otherwise every month in [year_from, year_to] is fetched. Returns a
    flat list of normalized rows ready for db.upsert_rows into census_pork_trade,
    or [] (with a printed note) when CENSUS_API_KEY is not set.
    """
    key = api_key()
    if not key:
        print("  [Census] CENSUS_API_KEY not set — skipping US HS trade ingest "
              "(register a free key at https://api.census.gov/data/key_signup.html)")
        return []

    window = months if months is not None else _month_range(year_from, year_to)
    rows = []
    for flow in flows:
        got = 0
        for index, year_month in enumerate(window):
            if index:
                time.sleep(REQUEST_DELAY_SEC)
            try:
                month_rows = _fetch_flow_month(flow, year_month, key)
            except (HTTPError, URLError, json.JSONDecodeError, Exception) as exc:
                print(f"  [Census] {flow} {year_month} fetch failed: {exc}")
                continue
            rows.extend(month_rows)
            got += len(month_rows)
        print(f"  [Census] {flow}: {got:,} pork HS10 rows over {len(window)} months")
    return rows
