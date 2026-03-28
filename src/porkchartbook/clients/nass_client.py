"""
nass_client.py — NASS QuickStats API client.
"""

import json
import os
import time
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

NASS_BASE = "https://quickstats.nass.usda.gov/api"
NASS_KEY = os.environ.get("NASS_API_KEY", "")

# Delay between requests to avoid rate limiting (seconds)
_REQUEST_DELAY = 1.0


def nass_get(endpoint, params, retries=3):
    """HTTP GET against NASS QuickStats API. Returns parsed JSON.

    Retries on 403/429 with exponential backoff.
    """
    params["key"] = NASS_KEY
    params["format"] = "JSON"
    url = f"{NASS_BASE}/{endpoint}/?{urlencode(params)}"
    req = Request(url)
    req.add_header("Accept", "application/json")

    for attempt in range(retries):
        try:
            time.sleep(_REQUEST_DELAY)
            with urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode())
        except HTTPError as e:
            if e.code in (403, 429) and attempt < retries - 1:
                wait = (attempt + 1) * 5
                print(f"  (rate limited, waiting {wait}s) ", end="", flush=True)
                time.sleep(wait)
                continue
            raise
    return {}


def get_record_count(params):
    """Check how many records a query would return (without fetching them)."""
    try:
        result = nass_get("get_counts", dict(params))
        return int(result.get("count", 0))
    except (HTTPError, URLError, Exception) as e:
        print(f"  count check failed: {e}")
        return -1


def fetch_data_item(short_desc, **filters):
    """Fetch records for a specific data item (short_desc).

    Uses exact match on short_desc. Additional filters (year__GE, etc.)
    can be passed as keyword args.

    Returns list of record dicts.
    """
    if not NASS_KEY:
        print("  WARNING: NASS_API_KEY not set, skipping NASS fetch")
        return []

    params = {
        "source_desc": "SURVEY",
        "short_desc": short_desc,
    }
    params.update(filters)

    # Check count first to avoid surprises
    count = get_record_count(params)
    if count == 0:
        return []
    if count > 50000:
        print(f"  [NASS] {short_desc}: {count} records, chunking by year")
        year_start = int(filters.get("year__GE", 2010))
        year_end = int(filters.get("year__LE", date.today().year))
        all_data = []
        for yr in range(year_start, year_end + 1):
            yr_params = dict(params)
            yr_params.pop("year__GE", None)
            yr_params.pop("year__LE", None)
            yr_params["year"] = str(yr)
            try:
                result = nass_get("api_GET", yr_params)
                chunk = result.get("data", [])
                if chunk:
                    all_data.extend(chunk)
                    print(f"    {yr}: {len(chunk)} records")
            except (HTTPError, URLError, Exception) as e:
                print(f"    {yr}: WARN: {e}")
        return all_data

    print(f"  [NASS] {short_desc}: {count} records ...", end=" ", flush=True)
    try:
        result = nass_get("api_GET", params)
        data = result.get("data", [])
        print(f"fetched {len(data)}")
        return data
    except (HTTPError, URLError, Exception) as e:
        print(f"WARN: {e}")
        return []


def fetch_commodity(commodity_desc, stat_category=None, **filters):
    """Fetch all records for a commodity, optionally filtered by stat category.

    For large datasets, this may need year-based chunking.
    """
    if not NASS_KEY:
        print("  WARNING: NASS_API_KEY not set, skipping NASS fetch")
        return []

    params = {
        "source_desc": "SURVEY",
        "sector_desc": "ANIMALS & PRODUCTS",
        "group_desc": "POULTRY",
        "commodity_desc": commodity_desc,
    }
    if stat_category:
        params["statisticcat_desc"] = stat_category
    params.update(filters)

    count = get_record_count(params)
    if count == 0:
        return []

    # If over 50K, chunk by year
    if count > 50000:
        print(f"  [NASS] {commodity_desc}/{stat_category}: {count} records, chunking by year")
        all_data = []
        year_start = int(filters.get("year__GE", 2010))
        for yr in range(year_start, 2027):
            yr_params = dict(params)
            yr_params["year"] = str(yr)
            try:
                result = nass_get("api_GET", yr_params)
                chunk = result.get("data", [])
                if chunk:
                    all_data.extend(chunk)
                    print(f"    {yr}: {len(chunk)} records")
            except (HTTPError, URLError, Exception) as e:
                print(f"    {yr}: WARN: {e}")
        return all_data

    print(f"  [NASS] {commodity_desc}/{stat_category}: {count} records ...",
          end=" ", flush=True)
    try:
        result = nass_get("api_GET", params)
        data = result.get("data", [])
        print(f"fetched {len(data)}")
        return data
    except (HTTPError, URLError, Exception) as e:
        print(f"WARN: {e}")
        return []
