"""
ers_trade_pork_client.py — Fetch and parse USDA ERS monthly pork trade data.

Reads ERS's long-form "Pork monthly U.S. trade (carcass weight, 1,000 pounds)"
CSV from the Livestock and Meat International Trade Data page, the same way
ers_price_spreads_client reads ERS media CSVs directly.

History: this client used to parse the pork monthly .xlsx workbook. In September
2026 ERS reformatted every workbook on that page "to meet ERS Data Product Quality
Standards" (same data, new layout) and started publishing long-form CSVs alongside
them. The 9/4/2026 release parsed to 0 rows under the old xlsx parser, ingest
swallowed that as a clean run, and the series quietly froze at June. The CSV is
machine-readable by design, so it is far less fragile than scraping a workbook
laid out for people. On the full overlap (1989-01..2026-06) it matches the old
workbook values exactly; the only label change is "St Helena" -> "St. Helena".

CSV columns: COMMODITY_DESC, TRADE_FLOW, UNIT_DESC, GEOGRAPHY_CODE,
GEOGRAPHY_DESC, YEAR_ID, TIMEPERIOD_ID (month 1-12), AMOUNT. Each month carries
one row per partner country plus a "World total" row with a blank code.

Failures raise TradeFetchError instead of returning []: a fetch problem, a
download that is not the expected CSV (e.g. a 404 HTML page), an unexpected unit,
or a parse that yields no rows. ERS rotates media/<id> paths when it republishes;
ERS_PORK_TRADE_URL overrides landing-page discovery.
"""

from __future__ import annotations

import csv
import io
import os
import re
from html import unescape
from urllib.parse import urljoin
from urllib.request import Request, urlopen


class TradeFetchError(RuntimeError):
    """Raised when the ERS pork trade CSV can't be fetched or yields no rows."""


ERS_TRADE_PAGE_URL = "https://www.ers.usda.gov/data-products/livestock-and-meat-international-trade-data"

# Set ERS_PORK_TRADE_URL to the current pork monthly CSV URL to bypass landing-page
# discovery entirely — useful when the scrape is blocked or ERS changes the link.
TRADE_URL_OVERRIDE = os.environ.get("ERS_PORK_TRADE_URL", "").strip() or None

# Browser-like headers: the ERS landing page sits behind anti-bot filtering that
# rejects terse user agents, so scraping needs a realistic header set.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# The monthly file, not the "pork-annual-and-cumulative-year-to-date" one.
CSV_LINK_RE = re.compile(r'href="([^"]*pork[^"/]*monthly[^"]*\.csv[^"]*)"', re.I)

REQUIRED_COLUMNS = {"TRADE_FLOW", "UNIT_DESC", "GEOGRAPHY_DESC", "YEAR_ID", "TIMEPERIOD_ID", "AMOUNT"}

FLOW_CONFIG = {
    "exports": {"flow": "export", "section_label": "Pork exports"},
    "imports": {"flow": "import", "section_label": "Pork imports"},
}

EXPECTED_UNIT = "carcass weight, 1,000 pounds"
# Stored unit label, kept identical to the rows the xlsx parser wrote.
UNIT_LABEL = "1,000 lb carcass wt"
TOTAL_LABEL = "world total"


def _request_bytes(url, accept=None, headers=None):
    hdrs = dict(headers or BROWSER_HEADERS)
    if accept:
        hdrs["Accept"] = accept
    request = Request(url, headers=hdrs)
    try:
        with urlopen(request, timeout=90) as response:
            return response.read()
    except Exception as exc:  # noqa: BLE001 — any failure here means stale data
        raise TradeFetchError(f"fetch failed ({url}): {exc}") from exc


def discover_trade_url():
    """Find the current ERS pork monthly trade CSV URL from the landing page.

    Honors ERS_PORK_TRADE_URL first. Raises TradeFetchError if no pork monthly
    CSV link is found, rather than returning a stale hardcoded URL.
    """
    if TRADE_URL_OVERRIDE:
        return TRADE_URL_OVERRIDE
    html = _request_bytes(ERS_TRADE_PAGE_URL, accept="text/html").decode("utf-8", "ignore")
    match = CSV_LINK_RE.search(html)
    if match:
        return urljoin(ERS_TRADE_PAGE_URL, unescape(match.group(1)))
    raise TradeFetchError(
        "no pork monthly .csv link found on the ERS landing page "
        f"({ERS_TRADE_PAGE_URL}). ERS may have renamed or moved the file. Set "
        "ERS_PORK_TRADE_URL to the current pork monthly US-trade CSV URL."
    )


def fetch_trade_csv(trade_url=None):
    """Download the ERS pork monthly trade CSV and confirm it is really one.

    Returns (resolved_url, csv_text). A response without the expected header
    (e.g. a 404 HTML page from a rotated media URL) raises TradeFetchError.
    """
    resolved_url = trade_url or discover_trade_url()
    print(f"  [ERS-pork] Downloading trade CSV: {resolved_url}")
    text = _request_bytes(resolved_url, accept="text/csv,*/*").decode("utf-8-sig", "replace")
    header = next(csv.reader(io.StringIO(text)), [])
    missing = REQUIRED_COLUMNS - {col.strip().upper() for col in header}
    if missing:
        raise TradeFetchError(
            f"{resolved_url} did not return the expected ERS long-form CSV (missing "
            f"columns {sorted(missing)}; got {len(text)} chars starting {text[:40]!r}). "
            "The URL likely 404'd or ERS changed the format. Set ERS_PORK_TRADE_URL "
            "to the current pork monthly US-trade CSV URL."
        )
    return resolved_url, text


def _normalize_label(value):
    return " ".join((value or "").split()).strip().lower()


def parse_trade_csv(text, source_url):
    """Parse the ERS long-form pork trade CSV into totals and partner-country rows."""
    total_rows = []
    partner_rows = []
    reader = csv.DictReader(io.StringIO(text))
    reader.fieldnames = [name.strip().upper() for name in reader.fieldnames or []]
    for row in reader:
        if _normalize_label(row.get("COMMODITY_DESC") or "pork") != "pork":
            continue
        flow_cfg = FLOW_CONFIG.get(_normalize_label(row.get("TRADE_FLOW")))
        if not flow_cfg:
            continue
        unit = _normalize_label(row.get("UNIT_DESC"))
        if unit != EXPECTED_UNIT:
            raise TradeFetchError(
                f"unexpected unit {row.get('UNIT_DESC')!r} in {source_url} "
                f"(expected {EXPECTED_UNIT!r}); refusing to store mislabeled values."
            )
        try:
            year = int(row["YEAR_ID"])
            month = int(row["TIMEPERIOD_ID"])
            value = float(row["AMOUNT"])
        except (KeyError, TypeError, ValueError):
            continue
        if not 1 <= month <= 12:
            continue
        geography = (row.get("GEOGRAPHY_DESC") or "").strip()
        if not geography:
            continue

        record = {
            "report_month": f"{year:04d}-{month:02d}",
            "commodity": "pork",
            "flow": flow_cfg["flow"],
            "product": "pork",
            "unit": UNIT_LABEL,
            "source_url": source_url,
        }
        if _normalize_label(geography) == TOTAL_LABEL:
            total_rows.append({**record, "section_label": flow_cfg["section_label"], "value": value})
        else:
            partner_rows.append({**record, "country": geography.title(), "value": value})

    latest = max((r["report_month"] for r in total_rows), default="none")
    print(f"  [ERS-pork] Parsed {len(total_rows)} total rows, {len(partner_rows)} partner rows (through {latest})")
    return total_rows, partner_rows


def _empty_parse_error(source_url, kind):
    return TradeFetchError(
        f"parsed 0 {kind} rows from {source_url}. The CSV downloaded with the expected "
        "columns but no usable rows — check TRADE_FLOW ('Exports'/'Imports') and the "
        "'World total' GEOGRAPHY_DESC label."
    )


def fetch_trade_rows():
    """Fetch and parse the ERS pork trade CSV — totals only.

    Raises TradeFetchError on fetch failure or if no total rows parse.
    """
    source_url, text = fetch_trade_csv()
    total_rows, _partner_rows = parse_trade_csv(text, source_url)
    if not total_rows:
        raise _empty_parse_error(source_url, "total")
    return total_rows


def fetch_partner_rows():
    """Fetch and parse partner-country pork trade rows.

    Raises TradeFetchError on fetch failure or if no partner rows parse.
    """
    source_url, text = fetch_trade_csv()
    _total_rows, partner_rows = parse_trade_csv(text, source_url)
    if not partner_rows:
        raise _empty_parse_error(source_url, "partner-country")
    return partner_rows
