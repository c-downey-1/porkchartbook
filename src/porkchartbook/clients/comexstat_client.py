"""
comexstat_client.py — Brazil pork exports from MDIC/SECEX Comex Stat.

Comex Stat is Brazil's official foreign-trade statistics system (Ministry of
Development, Industry, Trade and Services / SECEX). It exposes a free, no-key
JSON API that returns monthly export/import detail by NCM (the 8-digit Mercosur
tariff code) and destination country, with FOB value (USD), net weight (kg), and
statistical quantity. Detailed monthly data run from 1997 to the current month.

Brazil is the world's #4 pork exporter, so this feed is global supply/competition
context for the pork chartbook rather than a U.S. domestic series.

API:  POST https://api-comexstat.mdic.gov.br/general
Body: {"flow":"export","monthDetail":true,
       "period":{"from":"YYYY-MM","to":"YYYY-MM"},
       "filters":[{"filter":"ncm","values":[...8-digit codes...]}],
       "details":["ncm","country"],
       "metrics":["metricFOB","metricKG","metricStatistic"]}

Industry sanity-check (manual, not ingested here): ABPA Brazilian Pork monthly
releases are good for "all pork products" totals and top destinations, but Comex
Stat is the better feed for automated monitoring.
"""

from __future__ import annotations

import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API_URL = "https://api-comexstat.mdic.gov.br/general"

# The Comex Stat API rate-limits bursty clients (HTTP 429). Be a polite client:
# pause between year requests and back off on 429 / transient errors.
REQUEST_DELAY_SEC = 2.0
MAX_RETRIES = 5
BACKOFF_BASE_SEC = 5.0

# Curated swine-product NCM codes, grouped by category so the dashboard can
# aggregate (e.g. headline "in natura" pork = the fresh_frozen group, HS 0203).
# Verified against the live API; mixed-species sausages (16010000) are
# deliberately excluded because they are not swine-specific.
PORK_NCM = [
    # Fresh / chilled / frozen pork meat (HS 0203) — the headline "in natura" series
    {"code": "02031100", "category": "fresh_frozen"},  # carcasses/half-carcasses, fresh/chilled
    {"code": "02031200", "category": "fresh_frozen"},  # hams/shoulders, bone-in, fresh/chilled
    {"code": "02031900", "category": "fresh_frozen"},  # other cuts, fresh/chilled
    {"code": "02032100", "category": "fresh_frozen"},  # carcasses/half-carcasses, frozen
    {"code": "02032200", "category": "fresh_frozen"},  # hams/shoulders, bone-in, frozen
    {"code": "02032900", "category": "fresh_frozen"},  # other cuts, frozen (the bulk of exports)
    # Edible swine offal (HS 0206)
    {"code": "02063000", "category": "offal"},         # offal, fresh/chilled
    {"code": "02064100", "category": "offal"},         # livers, frozen
    {"code": "02064900", "category": "offal"},         # other offal, frozen
    # Pig fat / lard, free of lean meat (HS 0209)
    {"code": "02091011", "category": "fat"},           # back fat (toucinho), fresh/chilled/frozen
    {"code": "02091019", "category": "fat"},           # other back fat
    {"code": "02091021", "category": "fat"},           # pig fat, fresh/chilled/frozen
    {"code": "02091029", "category": "fat"},           # other pig fat
    # Salted, dried or smoked swine meat (HS 0210)
    {"code": "02101100", "category": "salted_dried_smoked"},  # hams/shoulders, bone-in
    {"code": "02101200", "category": "salted_dried_smoked"},  # bellies (bacon)
    {"code": "02101900", "category": "salted_dried_smoked"},  # other
    # Prepared / preserved swine meat (HS 1602.4x)
    {"code": "16024100", "category": "prepared"},      # hams and cuts
    {"code": "16024200", "category": "prepared"},      # shoulders and cuts
    {"code": "16024900", "category": "prepared"},      # other prepared swine, incl. mixtures
]

_CATEGORY_BY_CODE = {item["code"]: item["category"] for item in PORK_NCM}


def _safe_float(value):
    if value in (None, "", "."):
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _post_once(payload):
    """POST a JSON body to the Comex Stat general endpoint and return the parsed dict."""
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        API_URL,
        data=body,
        headers={
            "User-Agent": "porkchartbook/1.0",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def _post(payload):
    """POST with retry/backoff on HTTP 429 and transient network errors."""
    for attempt in range(MAX_RETRIES):
        try:
            return _post_once(payload)
        except HTTPError as exc:
            if exc.code == 429 and attempt < MAX_RETRIES - 1:
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                try:
                    wait = float(retry_after)
                except (TypeError, ValueError):
                    wait = BACKOFF_BASE_SEC * (2 ** attempt)
                print(f"  [Comex] 429 rate-limited, retrying in {wait:.0f}s "
                      f"(attempt {attempt + 1}/{MAX_RETRIES})")
                time.sleep(wait)
                continue
            raise
        except (URLError, TimeoutError) as exc:
            if attempt < MAX_RETRIES - 1:
                wait = BACKOFF_BASE_SEC * (2 ** attempt)
                print(f"  [Comex] {exc}, retrying in {wait:.0f}s "
                      f"(attempt {attempt + 1}/{MAX_RETRIES})")
                time.sleep(wait)
                continue
            raise


def _fetch_year(year, ncm_codes):
    """Fetch one calendar year of pork export rows (all months, all destinations)."""
    payload = {
        "flow": "export",
        "monthDetail": True,
        "period": {"from": f"{year}-01", "to": f"{year}-12"},
        "filters": [{"filter": "ncm", "values": ncm_codes}],
        "details": ["ncm", "country"],
        "metrics": ["metricFOB", "metricKG", "metricStatistic"],
    }
    try:
        result = _post(payload)
    except (HTTPError, URLError, json.JSONDecodeError, Exception) as exc:
        print(f"  [Comex] {year} fetch failed: {exc}")
        return []

    if not result.get("success", True):
        print(f"  [Comex] {year} API error: {result.get('message')}")
        return []

    raw = result.get("data", {}).get("list", []) or []
    rows = []
    for item in raw:
        code = item.get("coNcm")
        year_val = item.get("year")
        month = item.get("monthNumber")
        country = (item.get("country") or "").strip()
        if not (code and year_val and month and country):
            continue
        rows.append({
            "report_month": f"{year_val}-{int(month):02d}",
            "flow": "export",
            "ncm_code": code,
            "ncm_category": _CATEGORY_BY_CODE.get(code, "other"),
            "ncm_desc": item.get("ncm"),
            "country": country,
            "value_fob_usd": _safe_float(item.get("metricFOB")),
            "net_kg": _safe_float(item.get("metricKG")),
            "stat_qty": _safe_float(item.get("metricStatistic")),
            "source_url": API_URL,
        })
    return rows


def fetch_pork_exports(year_from, year_to, ncm_set=None):
    """Fetch Brazil pork export rows for [year_from, year_to], chunked by year.

    Returns a flat list of normalized rows ready for db.upsert_rows into
    comexstat_pork_exports. Years are fetched one request at a time so a single
    failure does not lose the whole backfill.
    """
    ncm_codes = [item["code"] for item in (ncm_set or PORK_NCM)]
    rows = []
    years = range(year_from, year_to + 1)
    for index, year in enumerate(years):
        if index:
            time.sleep(REQUEST_DELAY_SEC)  # be polite between requests
        year_rows = _fetch_year(year, ncm_codes)
        print(f"  [Comex] {year}: {len(year_rows):,} rows")
        rows.extend(year_rows)
    return rows
