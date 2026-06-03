"""
mars_client.py - USDA AMS MARS API client.

The pork chartbook uses MARS for retail feature activity because the public
MyMarketNews pages expose the latest report well, while the API gives us the
history needed for executive trend charts.
"""

from __future__ import annotations

import base64
import json
import os
from datetime import date, timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


MARS_BASE = "https://marsapi.ams.usda.gov/services/v1.2/reports"
MARS_KEY = os.environ.get("MARS_API_KEY", "")


def mars_get(url):
    """HTTP GET with MARS basic auth. Returns parsed JSON."""
    req = Request(url)
    req.add_header(
        "Authorization",
        "Basic " + base64.b64encode(f"{MARS_KEY}:".encode()).decode(),
    )
    req.add_header("Accept", "application/json")
    with urlopen(req, timeout=90) as response:
        return json.loads(response.read().decode())


def fetch_report(slug_id, start, end):
    """Fetch all MARS report sections for a slug, chunked in 180-day windows."""
    if not MARS_KEY:
        print("  WARNING: MARS_API_KEY not set, skipping MARS fetch")
        return []

    all_sections = []
    cur = start if isinstance(start, date) else date.fromisoformat(str(start))
    end_date = end if isinstance(end, date) else date.fromisoformat(str(end))

    while cur <= end_date:
        chunk_end = min(cur + timedelta(days=179), end_date)
        sd = cur.strftime("%m/%d/%Y")
        ed = chunk_end.strftime("%m/%d/%Y")
        url = f"{MARS_BASE}/{slug_id}?q=report_begin_date={sd}:{ed}&allSections=true"

        print(f"  [{slug_id}] {cur} to {chunk_end} ...", end=" ", flush=True)
        try:
            data = mars_get(url)
        except (HTTPError, URLError, Exception) as exc:
            print(f"WARN: {exc}")
            cur = chunk_end + timedelta(days=1)
            continue

        sections = data if isinstance(data, list) else [data]
        rows = sum(section.get("stats", {}).get("totalRows", 0) for section in sections)
        print(f"{rows} rows")
        all_sections.extend(sections)
        cur = chunk_end + timedelta(days=1)

    return all_sections
