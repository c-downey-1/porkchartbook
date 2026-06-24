"""
wasde_client.py — USDA WASDE pork forecasts (production, exports, hog price).

Source (keyless, no login):
  https://www.usda.gov/oce/commodity/wasde/wasde<MMYY>v2.txt

The fixed-width WASDE text release carries every series we need in two tables:

  * "U.S. Meats Supply and Use" (Million Pounds) — the Pork block gives forecast
    Production (col 1 after the month label) and Exports (col 4) for the current
    and next marketing years, with both the current-month and prior-month
    vintage rows.
  * "U.S. Quarterly Prices for Animal Products" (Dol./cwt) — the
    "Barrows and gilts" column gives the forecast national hog price; the annual
    "<Mon>Proj." line is the current-vintage annual figure per marketing year.

Only the current and previous month are hosted at this path, which is all a
daily-refresh dashboard needs (each file already carries current + next
marketing year). WASDE releases monthly (~9th–12th); the daily job just attempts
the current-month file and falls back to the previous month.
"""

from __future__ import annotations

import calendar
import re
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_URL = "https://www.usda.gov/oce/commodity/wasde"

# Released reports use the "v2" suffix; v1/v3 are tried as a fallback.
VERSIONS = ("v2", "v1", "v3")

# Commodity headers that mark the end of the Pork block in the meats table.
_MEATS_STOP = {"TotalRed", "Meat5/", "Beef", "Broiler", "Turkey", "Lamb", "Veal"}
_YEAR_RE = re.compile(r"^(\d{4})\b")


def _request_text(url):
    request = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "text/plain"})
    with urlopen(request, timeout=90) as response:
        return response.read().decode("latin-1", "replace")


def _safe_float(token):
    if token is None:
        return None
    token = token.strip().replace(",", "")
    if token in ("", "NA", "-", "*"):
        return None
    try:
        return float(token)
    except ValueError:
        return None


def _candidate_files(today=None):
    """Yield (url, report_month_iso, month_abbr) for the current and previous
    month, each with the v2/v1/v3 suffixes."""
    today = today or date.today()
    year, month = today.year, today.month
    for _ in range(2):  # current month, then previous
        mmyy = f"{month:02d}{year % 100:02d}"
        abbr = calendar.month_abbr[month]  # e.g. "Jun"
        iso = f"{year:04d}-{month:02d}"
        for version in VERSIONS:
            yield f"{BASE_URL}/wasde{mmyy}{version}.txt", iso, abbr
        month -= 1
        if month == 0:
            month, year = 12, year - 1


def fetch_latest_text(today=None):
    """Download the most recent available WASDE text file.

    Returns (text, report_month_iso, month_abbr, url), or (None, ...) if nothing
    could be fetched.
    """
    for url, iso, abbr in _candidate_files(today):
        try:
            text = _request_text(url)
        except HTTPError as exc:
            if exc.code == 404:
                continue
            raise
        except (URLError, TimeoutError):
            continue
        if text and "U.S. Meats Supply and Use" in text:
            print(f"  [WASDE] Using {url} (vintage {iso})")
            return text, iso, abbr, url
    print("  [WASDE] No current/previous-month file could be fetched")
    return None, None, None, None


def _parse_meats_pork(lines, month_abbr):
    """Return {marketing_year: {"production": x, "exports": y, "kind": ...}}.

    Within each marketing year, the current-month vintage row (month_abbr) wins;
    the actual/estimate year carries its values on the year line itself.
    """
    out = {}
    in_section = in_pork = False
    cur_year = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("U.S. Meats Supply and Use"):
            in_section = True
            continue
        if not in_section:
            continue
        if not in_pork:
            if stripped == "Pork":
                in_pork = True
            continue
        toks = stripped.split()
        if not toks:
            continue
        if toks[0] in _MEATS_STOP:
            break
        year_match = _YEAR_RE.match(stripped)
        if year_match:
            cur_year = int(year_match.group(1))
            nums = [t for t in toks[1:] if t != "Proj."]
            # An actual/estimate year (no "Proj.") carries its 8 values inline.
            if len(nums) >= 8 and _safe_float(nums[0]) is not None:
                out[cur_year] = {
                    "production": _safe_float(nums[1]),
                    "exports": _safe_float(nums[4]),
                    "kind": "estimate",
                }
            continue
        if cur_year is not None and toks[0] == month_abbr:
            nums = toks[1:]
            if len(nums) >= 8:
                out[cur_year] = {
                    "production": _safe_float(nums[1]),
                    "exports": _safe_float(nums[4]),
                    "kind": "forecast",
                }
    return out


def _parse_hog_price(lines, month_abbr):
    """Return {marketing_year: (hog_price_dol_cwt, kind)} from the quarterly-prices
    table. The current-vintage annual "<Mon>Proj." line is the forecast; the
    "Annual" line is the actual for a completed year ("Barrows and gilts" col)."""
    proj_label = f"{month_abbr}Proj."
    out = {}
    in_section = False
    cur_year = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("U.S. Quarterly Prices for Animal Products"):
            in_section = True
            continue
        if not in_section:
            continue
        if stripped.startswith("WASDE") or stripped.startswith("U.S. Meats Supply"):
            break  # past the table
        toks = stripped.split()
        if not toks:
            continue
        if re.fullmatch(r"\d{4}", toks[0]):
            cur_year = int(toks[0])
            continue
        if cur_year is None or len(toks) < 3:
            continue
        # cols after the label: Steers, Barrows and gilts, Broilers, ...
        if toks[0] == proj_label:
            out[cur_year] = (_safe_float(toks[2]), "forecast")
        elif toks[0] == "Annual" and cur_year not in out:
            out[cur_year] = (_safe_float(toks[2]), "estimate")
    return out


def fetch_forecast_rows(today=None):
    """Fetch and parse WASDE pork forecasts into normalized rows ready for
    db.upsert_rows into wasde_forecasts. Returns [] on fetch failure."""
    text, iso, abbr, url = fetch_latest_text(today)
    if not text:
        return []
    lines = text.splitlines()
    meats = _parse_meats_pork(lines, abbr)
    prices = _parse_hog_price(lines, abbr)

    rows = []
    for year, vals in meats.items():
        for metric, key, unit in (
            ("pork_production", "production", "million lb"),
            ("pork_exports", "exports", "million lb"),
        ):
            value = vals.get(key)
            if value is None:
                continue
            rows.append({
                "report_month": iso,
                "marketing_year": year,
                "metric": metric,
                "value": value,
                "unit": unit,
                "vintage_kind": vals.get("kind", "forecast"),
                "source_url": url,
            })
    for year, (price, kind) in prices.items():
        if price is None:
            continue
        rows.append({
            "report_month": iso,
            "marketing_year": year,
            "metric": "hog_price",
            "value": price,
            "unit": "$/cwt",
            "vintage_kind": kind,
            "source_url": url,
        })
    print(f"  [WASDE] Parsed {len(rows)} forecast rows (vintage {iso})")
    return rows
