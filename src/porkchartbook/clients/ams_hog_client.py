"""
ams_hog_client.py — Fetch USDA AMS hog price and cutout data from MPR Datamart.

Uses the public MPR Datamart API (no key required):
  https://mpr.datamart.ams.usda.gov/services/v1.1/reports/{report_id}/{section}

Reports fetched:
  LM_HG201 (report 2511) — National Daily Direct Prior Day Slaughtered Swine
    Section "Summary"            → barrows_head_count (head)
    Section "Carcass Measurements" → wtd_avg_base, wtd_avg_net_price, avg_carcass_weight

  LM_PK602 (report 2498) — National Daily Pork FOB Plant Negotiated Sales Afternoon
    Section "Cutout and Primal Values" → pork_carcass, pork_loin, pork_butt,
                                          pork_picnic, pork_rib, pork_ham, pork_belly
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from urllib.request import Request, urlopen

MPR_BASE = "https://mpr.datamart.ams.usda.gov/services/v1.1/reports"

# (report_id, slug, section_name, [(api_field, series_name, unit)])
REPORT_SECTIONS = [
    (
        2511,
        "LM_HG201",
        "Summary",
        [
            ("barrows_head_count", "head_count_barrows_gilts", "head"),
        ],
    ),
    (
        2511,
        "LM_HG201",
        "Carcass Measurements",
        [
            ("wtd_avg_base", "base_price", "$/cwt"),
            ("wtd_avg_net_price", "net_price", "$/cwt"),
            ("avg_carcass_weight", "avg_carcass_weight", "lb"),
        ],
    ),
    (
        2498,
        "LM_PK602",
        "Cutout and Primal Values",
        [
            ("pork_carcass", "cutout_value", "$/cwt"),
            ("pork_loin", "loin_value", "$/cwt"),
            ("pork_butt", "butt_value", "$/cwt"),
            ("pork_picnic", "picnic_value", "$/cwt"),
            ("pork_rib", "rib_value", "$/cwt"),
            ("pork_ham", "ham_value", "$/cwt"),
            ("pork_belly", "belly_value", "$/cwt"),
        ],
    ),
]

# Delay between API requests to avoid hammering the server
_REQUEST_DELAY = 0.5


def _fetch_section(report_id, section_name, date_from=None, date_to=None):
    """Fetch a single report section from MPR Datamart.

    Returns the JSON response as a dict with 'results' list.
    date_from and date_to are datetime objects (or None for all history).
    """
    url = f"{MPR_BASE}/{report_id}/{section_name}"

    if date_from or date_to:
        start = (date_from or datetime(2000, 1, 1)).strftime("%-m/%-d/%Y")
        end = (date_to or datetime.today()).strftime("%-m/%-d/%Y")
        url = f"{url}?q=report_date={start}:{end}"

    req = Request(
        url,
        headers={
            "User-Agent": "porkchartbook/1.0",
            "Accept": "application/json",
        },
    )
    with urlopen(req, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def _parse_date(raw):
    """Parse report date string to ISO YYYY-MM-DD. Returns None on failure."""
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"):
        try:
            return datetime.strptime(raw.strip(), fmt).strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            continue
    return None


def fetch_ams_hog_rows(date_from=None, date_to=None):
    """Fetch all AMS hog price series and return rows for ams_hog_prices table.

    Args:
        date_from: datetime or None (None = all history)
        date_to:   datetime or None (None = today)

    Returns:
        list of dicts with keys: report_date, report_name, series_name, value, unit, source_url
    """
    rows = []

    for report_id, slug, section_name, fields in REPORT_SECTIONS:
        source_url = f"{MPR_BASE}/{report_id}/{section_name}"
        print(f"  [AMS-hog] {slug} / {section_name} ...", end=" ", flush=True)

        try:
            time.sleep(_REQUEST_DELAY)
            data = _fetch_section(report_id, section_name, date_from, date_to)
        except Exception as e:
            print(f"WARN: {e}")
            continue

        results = data.get("results", [])
        print(f"{len(results)} records")

        for record in results:
            raw_date = record.get("report_date")
            if not raw_date:
                continue
            report_date = _parse_date(raw_date)
            if not report_date:
                continue

            for api_field, series_name, unit in fields:
                raw_val = record.get(api_field)
                if raw_val in (None, "", "null"):
                    continue
                try:
                    value = float(raw_val)
                except (ValueError, TypeError):
                    continue
                rows.append(
                    {
                        "report_date": report_date,
                        "report_name": slug,
                        "series_name": series_name,
                        "value": value,
                        "unit": unit,
                        "source_url": source_url,
                    }
                )

    print(f"  [AMS-hog] Total: {len(rows)} rows across {len(REPORT_SECTIONS)} sections")
    return rows


def fetch_recent_ams_hog_rows(days_back=90):
    """Convenience wrapper — fetch the most recent N days."""
    date_from = datetime.today() - timedelta(days=days_back)
    return fetch_ams_hog_rows(date_from=date_from)
