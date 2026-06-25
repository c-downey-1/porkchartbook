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
from urllib.error import HTTPError, URLError
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
    request = Request(url, headers={"User-Agent": "porkchartbook/1.0", "Accept": "application/zip"})
    with urlopen(request, timeout=120) as response:
        return response.read()


def fetch_pork_psd(zip_bytes=None):
    """Fetch and parse FAS PSD pork production & exports by country.

    Returns a flat list of rows ready for db.upsert_rows into fas_psd_pork.
    Returns [] on fetch failure.
    """
    try:
        raw = zip_bytes if zip_bytes is not None else _request_bytes(PSD_ZIP_URL)
    except (HTTPError, URLError, Exception) as exc:
        print(f"  [PSD] fetch failed: {exc}")
        return []

    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
            csv_name = next((n for n in bundle.namelist() if n.lower().endswith(".csv")), None)
            if not csv_name:
                print("  [PSD] no CSV found in bundle")
                return []
            text = bundle.read(csv_name).decode("utf-8", "replace")
    except (zipfile.BadZipFile, Exception) as exc:
        print(f"  [PSD] unzip/parse failed: {exc}")
        return []

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
