"""
psd_client.py — world pork production & exports by country from USDA FAS PSD
(Production, Supply & Distribution).

Source (keyless): the FAS PSD bulk "livestock" CSV bundle
  https://apps.fas.usda.gov/psdonline/downloads/psd_livestock_csv.zip
which contains psd_livestock.csv (tidy long format). The PSD REST API requires a
free api.data.gov key; the bulk zip needs none and returns the whole dataset in
one ~1 MB download, so we use it.

Pork = commodity "Meat, Swine" (Commodity_Code 0113000). Production (Attribute_ID
028) and Exports (Attribute_ID 088) are both reported in 1000 MT carcass-weight
equivalent (CWE), so exports ÷ production is directly comparable across countries.
Annual (Market_Year), ~98 countries, 1960–current forecast year. No "World" row —
sum countries if a global total is needed.
"""

from __future__ import annotations

import csv
import io
import zipfile
from urllib.request import Request, urlopen


PSD_ZIP_URL = "https://apps.fas.usda.gov/psdonline/downloads/psd_livestock_csv.zip"

PORK_COMMODITY_CODE = "0113000"
# Attribute_ID -> normalized metric name. (028 = Production, 088 = Exports.)
PSD_ATTRIBUTES = {28: "production", 88: "exports"}


def _safe_float(value):
    if value in (None, "", "."):
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _request_bytes(url):
    # apps.fas.usda.gov sits behind a WAF that 406s a non-browser User-Agent, and
    # it serves the bundle as application/x-zip-compressed — so a strict
    # "Accept: application/zip" also 406s on content negotiation. A browser-like
    # UA plus a permissive Accept is what the server actually honors.
    request = Request(url, headers={
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
    })
    with urlopen(request, timeout=120) as response:
        return response.read()


def fetch_pork_psd(zip_bytes=None):
    """Fetch and parse FAS PSD pork production & exports by country.

    Returns a flat list of rows ready for db.upsert_rows into fas_psd_pork.
    Raises on a fetch/unzip failure (rather than returning []) so the
    orchestrator records it as a real error and flags it in the summary email
    instead of silently reporting "no new rows" while the dataset goes stale.
    """
    raw = zip_bytes if zip_bytes is not None else _request_bytes(PSD_ZIP_URL)

    with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
        csv_name = next((n for n in bundle.namelist() if n.lower().endswith(".csv")), None)
        if not csv_name:
            raise ValueError("PSD bundle contained no CSV file")
        text = bundle.read(csv_name).decode("utf-8", "replace")

    rows = []
    for record in csv.DictReader(text.splitlines()):
        if (record.get("Commodity_Code") or "").strip() != PORK_COMMODITY_CODE:
            continue
        try:
            attr_id = int((record.get("Attribute_ID") or "").strip())
        except ValueError:
            continue
        metric = PSD_ATTRIBUTES.get(attr_id)
        if metric is None:
            continue
        try:
            market_year = int((record.get("Market_Year") or "").strip())
        except ValueError:
            continue
        rows.append({
            "commodity_code": PORK_COMMODITY_CODE,
            "country": (record.get("Country_Name") or "").strip(),
            "country_code": (record.get("Country_Code") or "").strip(),
            "market_year": market_year,
            "attribute": metric,
            "value": _safe_float(record.get("Value")),
            "unit": (record.get("Unit_Description") or "(1000 MT CWE)").strip(),
            "source_url": PSD_ZIP_URL,
        })
    print(f"  [PSD] Parsed {len(rows)} pork production/export rows")
    return rows
