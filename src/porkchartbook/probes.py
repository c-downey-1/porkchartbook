#!/usr/bin/env python3
"""
probes.py — cheap freshness probes for long-term pork data sources.

A probe asks "has this source published anything new?" without doing the full
(slow, sometimes fragile) ingest. The orchestrator compares a probe's
fingerprint against the value stored in source_state and only triggers a real
ingest when the fingerprint moves.

Probes are intentionally lightweight:
  - NASS  → sum of QuickStats record COUNTS (no row payloads) across our series
  - ERS   → HTTP HEAD on the trade workbook (Last-Modified / ETag / size)

Sources whose endpoints are already cheap (AMS daily, FRED CSV, AMS retail,
Comex API) are not probed — the orchestrator just ingests them and reports
whether new rows landed via a before/after table fingerprint.
"""

from __future__ import annotations

from collections import namedtuple
from datetime import date
from urllib.request import Request, urlopen

from .clients import ers_trade_pork_client
from .clients import nass_client

# value: fingerprint string to store/compare (None if it could not be read)
# ok:    True if the probe ran cleanly; False signals an error (orchestrator
#        then fails safe and ingests anyway rather than silently skipping)
# note:  short human-readable detail for the log / email
ProbeResult = namedtuple("ProbeResult", ["value", "ok", "note"])


def nass_probe(year_ge=None):
    """Sum QuickStats record counts across every NASS series we ingest.

    The count endpoint returns only a tally, not the data, so this stays cheap
    even though it touches each series. If any individual count fails we report
    ok=False so the orchestrator re-ingests rather than trusting a partial sum.
    """
    # Imported lazily to avoid any import-order coupling with ingest.
    from .ingest import NASS_SERIES

    if not nass_client.NASS_KEY:
        # No key → every count call would 401. Fail fast; the orchestrator
        # will then attempt ingest, which also guards on the missing key.
        return ProbeResult(value=None, ok=False, note="NASS_API_KEY not set")

    year_ge = year_ge or (date.today().year - 1)
    total = 0
    failures = 0
    for series in NASS_SERIES:
        params = {
            "source_desc": "SURVEY",
            "short_desc": series["short_desc"],
            "year__GE": str(year_ge),
        }
        params.update(series.get("filters", {}))
        count = nass_client.get_record_count(params)
        if count < 0:
            failures += 1
            continue
        total += count

    if failures:
        return ProbeResult(
            value=str(total),
            ok=False,
            note=f"count check failed for {failures} series; got partial total {total}",
        )
    return ProbeResult(value=str(total), ok=True, note=f"{total} records across {len(NASS_SERIES)} series")


def ers_probe():
    """HTTP HEAD the ERS pork trade workbook; fingerprint = modified|etag|size."""
    try:
        url = ers_trade_pork_client.discover_workbook_url()
    except Exception as exc:  # noqa: BLE001 — probe must never raise
        return ProbeResult(value=None, ok=False, note=f"workbook URL discovery failed: {exc}")

    req = Request(
        url,
        method="HEAD",
        headers={"User-Agent": "porkchartbook/1.0", "Accept": "*/*"},
    )
    try:
        with urlopen(req, timeout=60) as response:
            headers = response.headers
    except Exception as exc:  # noqa: BLE001
        return ProbeResult(value=None, ok=False, note=f"HEAD request failed: {exc}")

    last_modified = headers.get("Last-Modified", "")
    etag = headers.get("ETag", "")
    length = headers.get("Content-Length", "")
    fingerprint = f"{last_modified}|{etag}|{length}"
    return ProbeResult(value=fingerprint, ok=True, note=f"Last-Modified={last_modified or '?'} size={length or '?'}")
