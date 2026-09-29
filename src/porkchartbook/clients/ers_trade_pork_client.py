"""
ers_trade_pork_client.py — Fetch and parse USDA ERS monthly pork trade data.

Forked from broilerchartbook/ers_trade_client.py and adapted for pork.
The ERS publishes a separate pork/beef/lamb workbook at the same landing page.

Failure handling mirrors ers_price_spreads_client: any fetch problem, a download
that is not really a workbook, or a parse that yields no rows raises
TradeFetchError instead of returning []. The old code silently fell back to a
hardcoded media URL; when ERS rotated that path the fallback 404'd, the 404 HTML
failed to parse, ingest swallowed the exception, and the series quietly froze at
the last good month.

ERS also reformatted these files in September 2026 ("to meet ERS Data Product
Quality Standards") and now publishes long-form CSVs alongside the xlsx. If the
xlsx parser stops matching, the durable fix is to switch this client to that
long-form CSV, the way ers_price_spreads_client reads media CSVs directly. Until
then, discovery + an ERS_PORK_TRADE_URL override + loud failures keep it honest.
"""

from __future__ import annotations

import io
import os
import re
import zipfile
from datetime import datetime
from html import unescape
from urllib.parse import urljoin
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET


class TradeFetchError(RuntimeError):
    """Raised when the ERS pork trade workbook can't be fetched or yields no rows."""


ERS_TRADE_PAGE_URL = "https://www.ers.usda.gov/data-products/livestock-and-meat-international-trade-data"

# ERS rotates the media/<id> path whenever it republishes. The previous hardcoded
# workbook (media/5613/pork-monthly-us-trade.xlsx) now 404s. Set ERS_PORK_TRADE_URL
# to the current workbook (or CSV) URL to bypass landing-page discovery entirely —
# useful when the scrape is blocked or ERS changes the link text.
WORKBOOK_URL_OVERRIDE = os.environ.get("ERS_PORK_TRADE_URL", "").strip() or None

# Browser-like headers: the ERS landing page sits behind anti-bot filtering that
# rejects terse user agents, so scraping needs a realistic header set.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

XML_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = {"r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
PKG_REL_NS = {"p": "http://schemas.openxmlformats.org/package/2006/relationships"}

# Section headers that appear in the ERS pork trade workbook.
# Keys are normalized (lowercased, stripped) section header strings.
# The current workbook (carcass-weight edition) has two sections only:
#   "Pork imports" and "Pork exports", units already in the workbook title.
SECTION_CONFIG = {
    "pork imports": {
        "commodity": "pork",
        "flow": "import",
        "product": "pork",
        "unit": "1,000 lb carcass wt",
        "section_label": "Pork imports",
    },
    "pork exports": {
        "commodity": "pork",
        "flow": "export",
        "product": "pork",
        "unit": "1,000 lb carcass wt",
        "section_label": "Pork exports",
    },
}

# Match any pork .xlsx link on the ERS landing page. Broadened from the old
# "pork-monthly" pattern because the Sept 2026 reformat may have renamed the file.
XLSX_LINK_RE = re.compile(r'href="([^"]*pork[^"]*\.xlsx[^"]*)"', re.I)
CELL_REF_RE = re.compile(r"([A-Z]+)")


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


def discover_workbook_url():
    """Find the current ERS pork trade workbook download URL from the landing page.

    Raises TradeFetchError if no pork .xlsx link is found, rather than returning a
    stale hardcoded URL that silently freezes the series.
    """
    html = _request_bytes(ERS_TRADE_PAGE_URL, accept="text/html").decode("utf-8", "ignore")
    links = [urljoin(ERS_TRADE_PAGE_URL, unescape(m)) for m in XLSX_LINK_RE.findall(html)]
    # Prefer the monthly US-trade workbook when several pork xlsx links are present.
    for link in links:
        if "monthly" in link.lower() or "trade" in link.lower():
            return link
    if links:
        return links[0]
    raise TradeFetchError(
        "no pork .xlsx link found on the ERS landing page "
        f"({ERS_TRADE_PAGE_URL}). ERS reformatted these files in Sept 2026 and may have "
        "renamed the link or moved to CSV. Set ERS_PORK_TRADE_URL to the current workbook "
        "(or CSV) URL, or switch this client to the new long-form CSV."
    )


def fetch_workbook_bytes(workbook_url=None):
    """Download the current ERS pork trade workbook and confirm it is really one.

    Resolution order: explicit arg, then ERS_PORK_TRADE_URL, then landing-page
    discovery. A non-xlsx response (e.g. a 404 HTML page from a rotated media URL)
    raises TradeFetchError instead of flowing into the parser as a bad zip.
    """
    resolved_url = workbook_url or WORKBOOK_URL_OVERRIDE or discover_workbook_url()
    print(f"  [ERS-pork] Downloading workbook: {resolved_url}")
    data = _request_bytes(
        resolved_url,
        accept="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    # .xlsx is a ZIP container; anything else (an HTML error page, a CSV) is not
    # what the xlsx parser expects.
    if data[:2] != b"PK":
        raise TradeFetchError(
            f"{resolved_url} did not return an .xlsx workbook (got {len(data)} bytes "
            f"starting {data[:16]!r}). The URL likely 404'd or ERS moved/reformatted the "
            "file (Sept 2026). Set ERS_PORK_TRADE_URL to the current workbook URL."
        )
    return resolved_url, data


def _normalize_label(value):
    return " ".join((value or "").replace("\n", " ").split()).strip().lower()


def _parse_month_label(value):
    return datetime.strptime(value.strip(), "%b-%y").strftime("%Y-%m")


def _shared_strings(workbook):
    try:
        root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
    except KeyError:
        return []

    values = []
    for item in root.findall("a:si", XML_NS):
        text = "".join(node.text or "" for node in item.iterfind(".//a:t", XML_NS))
        values.append(text)
    return values


def _workbook_sheet_targets(workbook):
    rels_root = ET.fromstring(workbook.read("xl/_rels/workbook.xml.rels"))
    rel_targets = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels_root.findall("p:Relationship", PKG_REL_NS)
    }

    workbook_root = ET.fromstring(workbook.read("xl/workbook.xml"))
    targets = []
    for sheet in workbook_root.findall("a:sheets/a:sheet", XML_NS):
        rid = sheet.attrib.get(f"{{{REL_NS['r']}}}id")
        if not rid:
            continue
        target = rel_targets.get(rid)
        if not target:
            continue
        targets.append(f"xl/{target.lstrip('/')}")
    return targets


def _cell_text(cell, shared_strings):
    cell_type = cell.attrib.get("t")

    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.iterfind(".//a:t", XML_NS))

    value_node = cell.find("a:v", XML_NS)
    if value_node is None or value_node.text is None:
        return ""

    if cell_type == "s":
        return shared_strings[int(value_node.text)]
    return value_node.text


def _sheet_rows(workbook, sheet_path, shared_strings):
    root = ET.fromstring(workbook.read(sheet_path))
    for row in root.findall(".//a:sheetData/a:row", XML_NS):
        values = {}
        for cell in row.findall("a:c", XML_NS):
            match = CELL_REF_RE.match(cell.attrib.get("r", ""))
            if not match:
                continue
            values[match.group(1)] = _cell_text(cell, shared_strings)
        yield values


def parse_workbook_bytes(workbook_bytes, source_url):
    """Parse ERS pork trade workbook bytes into normalized totals and partner-country rows."""
    total_rows = []
    partner_rows = []
    with zipfile.ZipFile(io.BytesIO(workbook_bytes)) as workbook:
        shared_strings = _shared_strings(workbook)

        for sheet_path in _workbook_sheet_targets(workbook):
            header_months = {}
            current_section = None

            for row in _sheet_rows(workbook, sheet_path, shared_strings):
                row_header = _normalize_label(row.get("A"))
                if row_header.startswith("import/export, geography code and name"):
                    header_months = {
                        column: _parse_month_label(value)
                        for column, value in row.items()
                        if column not in {"A", "B", "C"} and value
                    }
                    continue

                if row_header in SECTION_CONFIG:
                    current_section = SECTION_CONFIG[row_header]
                    # The section-header row also contains the first country's
                    # data (B=code, C=country, D..=values) — do NOT continue.

                if not current_section:
                    continue

                geography = (row.get("C") or row.get("B") or "").strip()
                if not geography:
                    continue

                destination = geography.title()
                normalized_geo = _normalize_label(geography)
                for column, report_month in header_months.items():
                    value = row.get(column)
                    if value in (None, ""):
                        continue
                    try:
                        float_val = float(value)
                    except (ValueError, TypeError):
                        continue
                    record = {
                        "report_month": report_month,
                        "commodity": current_section["commodity"],
                        "flow": current_section["flow"],
                        "product": current_section["product"],
                        "unit": current_section["unit"],
                        "source_url": source_url,
                    }
                    if normalized_geo == "total":
                        total_rows.append({
                            **record,
                            "section_label": current_section["section_label"],
                            "value": float_val,
                        })
                    else:
                        partner_rows.append({
                            **record,
                            "country": destination,
                            "value": float_val,
                        })
                if normalized_geo == "total":
                    current_section = None

    print(f"  [ERS-pork] Parsed {len(total_rows)} total rows, {len(partner_rows)} partner rows")
    return total_rows, partner_rows


def _empty_workbook_error(workbook_url, kind):
    return TradeFetchError(
        f"parsed 0 {kind} rows from {workbook_url}. The workbook downloaded but no "
        "expected sections/months were found — ERS reformatted these files in Sept 2026, "
        "so the section headers ('Pork imports'/'Pork exports'), the month header row, or "
        "the 'Total' label may have changed. Verify the layout (or move this client to the "
        "new long-form CSV)."
    )


def fetch_trade_rows():
    """Fetch and parse the current ERS pork workbook — totals only.

    Raises TradeFetchError on fetch failure or if no total rows parse.
    """
    workbook_url, workbook_bytes = fetch_workbook_bytes()
    total_rows, _partner_rows = parse_workbook_bytes(workbook_bytes, workbook_url)
    if not total_rows:
        raise _empty_workbook_error(workbook_url, "total")
    return total_rows


def fetch_partner_rows():
    """Fetch and parse partner-country pork trade rows.

    Raises TradeFetchError on fetch failure or if no partner rows parse.
    """
    workbook_url, workbook_bytes = fetch_workbook_bytes()
    _total_rows, partner_rows = parse_workbook_bytes(workbook_bytes, workbook_url)
    if not partner_rows:
        raise _empty_workbook_error(workbook_url, "partner-country")
    return partner_rows
