"""
fred_client.py - no-key FRED CSV client.

FRED's public graph CSV endpoint is enough for the chartbook feed-cost and
retail-price proxy series. It avoids adding another required API key.
"""

from __future__ import annotations

import csv
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


FRED_CSV_BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def _safe_float(value):
    if value in (None, "", "."):
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def fetch_series(series_id, label=None):
    """Fetch one FRED series through the public CSV endpoint."""
    url = f"{FRED_CSV_BASE}?{urlencode({'id': series_id})}"
    req = Request(url, headers={"User-Agent": "porkchartbook/1.0"})
    print(f"  [FRED] {series_id} ...", end=" ", flush=True)
    try:
        with urlopen(req, timeout=60) as response:
            text = response.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError, Exception) as exc:
        print(f"WARN: {exc}")
        return []

    rows = []
    for row in csv.DictReader(text.splitlines()):
        observation_date = row.get("observation_date") or row.get("DATE") or row.get("date")
        raw_value = row.get(series_id)
        if not observation_date:
            continue
        rows.append({
            "observation_date": observation_date,
            "series_id": series_id,
            "value": _safe_float(raw_value),
            "series_label": label or series_id,
            "source_url": url,
        })
    print(f"{len(rows)} observations")
    return rows
