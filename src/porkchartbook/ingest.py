#!/usr/bin/env python3
"""
ingest.py — pork chartbook ingestion pipeline.

Data sources:
  NASS QuickStats — Quarterly Hogs & Pigs report, weekly slaughter, prices
  AMS MPR Datamart — Barrow/gilt prices (LM_HG201), pork cutout (LM_PK602)
  ERS Trade        — Monthly pork import/export workbook
  Comex Stat       — Brazil pork exports (MDIC/SECEX), monthly by NCM x country

Usage:
  python -m porkchartbook.ingest --backfill-all
  python -m porkchartbook.ingest --update
  python -m porkchartbook.ingest --backfill-nass
  python -m porkchartbook.ingest --backfill-ams
  python -m porkchartbook.ingest --backfill-ers
  python -m porkchartbook.ingest --backfill-comex
  python -m porkchartbook.ingest --status
  python -m porkchartbook.ingest --smoke-test
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta

from . import db
from . import parsers
from .clients import ams_hog_client
from .clients import census_trade_client
from .clients import comexstat_client
from .clients import ers_food_availability_client
from .clients import ers_trade_pork_client
from .clients import fred_client
from .clients import mars_client
from .clients import nass_client
from .clients import wasde_client


# ── NASS Series ───────────────────────────────────────────────────────────
#
# Quarterly Hogs & Pigs report — key national series.
# These short_desc strings are NASS QuickStats canonical identifiers.

NASS_SERIES = [
    # Inventory (Quarterly Hogs & Pigs)
    {
        "short_desc": "HOGS - INVENTORY",
        "label": "Total hog inventory",
    },
    {
        "short_desc": "HOGS, BREEDING - INVENTORY",
        "label": "Breeding hog inventory",
    },
    {
        "short_desc": "HOGS, MARKET - INVENTORY",
        "label": "Market hog inventory",
    },
    {
        "short_desc": "HOGS, MARKET, LT 50 LBS - INVENTORY",
        "label": "Market hog inventory under 50 lb",
    },
    {
        "short_desc": "HOGS, MARKET, 50 TO 119 LBS - INVENTORY",
        "label": "Market hog inventory 50-119 lb",
    },
    {
        "short_desc": "HOGS, MARKET, 120 TO 179 LBS - INVENTORY",
        "label": "Market hog inventory 120-179 lb",
    },
    {
        "short_desc": "HOGS, MARKET, GE 180 LBS - INVENTORY",
        "label": "Market hog inventory 180 lb and over",
    },
    # Farrowings and productivity
    {
        "short_desc": "HOGS, SOWS - FARROWED, MEASURED IN HEAD",
        "label": "Sows farrowed",
    },
    {
        "short_desc": "HOGS - LITTER RATE, MEASURED IN PIGS / LITTER",
        "label": "Pigs per litter",
    },
    # Pig crop
    {
        "short_desc": "HOGS - PIG CROP, MEASURED IN HEAD",
        "label": "Pig crop (head)",
    },
    # Slaughter (annual NASS Livestock Slaughter summary)
    {
        "short_desc": "HOGS - SLAUGHTERED, MEASURED IN HEAD",
        "label": "Hog slaughter (head)",
    },
    # Pork production
    {
        "short_desc": "HOGS - PRODUCTION, MEASURED IN LB",
        "label": "Pork production (lb)",
    },
    # Monthly Livestock Slaughter — true commercial (~99% of industry) coverage.
    # These are the canonical QuickStats short_desc strings (SLAUGHTER, COMMERCIAL
    # word order); national agg level only.
    {
        "short_desc": "HOGS, SLAUGHTER, COMMERCIAL - SLAUGHTERED, MEASURED IN HEAD",
        "label": "Commercial hog slaughter, monthly (head)",
        "filters": {"agg_level_desc": "NATIONAL"},
    },
    {
        "short_desc": "HOGS, SLAUGHTER, COMMERCIAL, FI - SLAUGHTERED, MEASURED IN HEAD",
        "label": "Federally inspected hog slaughter, monthly (head)",
        "filters": {"agg_level_desc": "NATIONAL"},
    },
    {
        "short_desc": "HOGS, BARROWS & GILTS, SLAUGHTER, COMMERCIAL, FI - SLAUGHTERED, MEASURED IN HEAD",
        "label": "Barrows & gilts slaughter, monthly (head)",
        "filters": {"agg_level_desc": "NATIONAL"},
    },
    {
        "short_desc": "HOGS, SOWS, SLAUGHTER, COMMERCIAL, FI - SLAUGHTERED, MEASURED IN HEAD",
        "label": "Sow slaughter, monthly (head)",
        "filters": {"agg_level_desc": "NATIONAL"},
    },
    {
        "short_desc": "HOGS, BOARS, SLAUGHTER, COMMERCIAL, FI - SLAUGHTERED, MEASURED IN HEAD",
        "label": "Boar slaughter, monthly (head)",
        "filters": {"agg_level_desc": "NATIONAL"},
    },
    {
        "short_desc": "HOGS, SLAUGHTER, COMMERCIAL - SLAUGHTERED, MEASURED IN LB / HEAD, LIVE BASIS",
        "label": "Avg live slaughter weight, monthly (lb/head)",
        "filters": {"agg_level_desc": "NATIONAL"},
    },
    {
        "short_desc": "HOGS, BARROWS & GILTS, SLAUGHTER, COMMERCIAL, FI - SLAUGHTERED, MEASURED IN LB / HEAD, DRESSED BASIS",
        "label": "Avg dressed weight, barrows & gilts, monthly (lb/head)",
        "filters": {"agg_level_desc": "NATIONAL"},
    },
    {
        "short_desc": "PORK, SLAUGHTER, COMMERCIAL - PRODUCTION, MEASURED IN LB",
        "label": "Commercial pork production, monthly (lb)",
        "filters": {"agg_level_desc": "NATIONAL"},
    },
    # Cold storage
    {
        "short_desc": "PORK, COLD STORAGE, FROZEN - STOCKS, MEASURED IN LB",
        "label": "Frozen pork stocks",
    },
    {
        "short_desc": "PORK, BELLIES, COLD STORAGE, FROZEN - STOCKS, MEASURED IN LB",
        "label": "Frozen pork belly stocks",
    },
    {
        "short_desc": "PORK, HAMS, COLD STORAGE, FROZEN - STOCKS, MEASURED IN LB",
        "label": "Frozen pork ham stocks",
    },
    {
        "short_desc": "PORK, LOINS, COLD STORAGE, FROZEN - STOCKS, MEASURED IN LB",
        "label": "Frozen pork loin stocks",
    },
    # Prices received
    {
        "short_desc": "HOGS - PRICE RECEIVED, MEASURED IN $ / CWT",
        "label": "Hog price received ($/cwt)",
    },
]

RETAIL_PORK_SLUG_ID = 2868

FRED_SERIES = [
    {
        "series_id": "PMAIZMTUSDM",
        "label": "World maize price",
    },
    {
        "series_id": "PSMEAUSDM",
        "label": "World soybean meal price",
    },
    {
        "series_id": "APU0000704111",
        "label": "Average retail bacon price",
    },
    # Competing-protein retail prices (BLS CPI average price, $/lb, US city
    # average, monthly) — same keyless FRED mechanism, for the "demand vs.
    # competing proteins" comparison against pork.
    {
        "series_id": "APU0000FD3101",
        "label": "Average retail pork chops price",
    },
    {
        "series_id": "APU0000706111",
        "label": "Average retail chicken price (whole)",
    },
    {
        "series_id": "APU0000703112",
        "label": "Average retail ground beef price",
    },
    {
        "series_id": "GASDESW",
        "label": "US diesel price ($/gal)",
    },
    {
        "series_id": "APU000072610",
        "label": "US electricity price ($/kWh)",
    },
]


# ── Helpers ───────────────────────────────────────────────────────────────

def _log_date_span(conn, source, rows, data_item=None):
    """Log a fetch entry spanning the min/max dates in rows."""
    if not rows:
        return
    sample = rows[0]
    if "year" in sample:
        dates = [str(row["year"]) for row in rows if row.get("year")]
    elif "report_month" in sample:
        dates = [row["report_month"] for row in rows if row.get("report_month")]
    else:
        dates = [row.get("report_date") for row in rows if row.get("report_date")]
    if dates:
        db.log_fetch(conn, source, min(dates), max(dates), len(rows), data_item=data_item)


# ── Ingest functions ──────────────────────────────────────────────────────

def ingest_nass_series(conn, series_config, year_ge=2010):
    """Fetch and store a single NASS data series."""
    short_desc = series_config["short_desc"]
    print(f"\n  {series_config['label']}")
    extra_filters = dict(series_config.get("filters", {}))
    records = nass_client.fetch_data_item(short_desc, year__GE=str(year_ge), **extra_filters)
    if not records:
        return 0
    rows = [parsers.parse_nass_record(record) for record in records]
    rows = [row for row in rows if row["year"] > 0]
    if rows:
        count = db.upsert_rows(conn, "nass_data", rows)
        db.log_fetch(conn, "nass", str(year_ge), str(date.today()), count, data_item=short_desc)
        return count
    return 0


def backfill_nass(conn, year_ge=2010):
    """Fetch all NASS hog series from year_ge to today."""
    print(f"\n{'=' * 60}")
    print(f"  NASS Backfill (year >= {year_ge})")
    print(f"{'=' * 60}")
    total = 0
    for series in NASS_SERIES:
        total += ingest_nass_series(conn, series, year_ge=year_ge)
    print(f"\n  NASS backfill complete: {total:,} rows")
    return total


def update_nass(conn):
    """Incremental NASS update — last 2 years only."""
    return backfill_nass(conn, year_ge=date.today().year - 1)


def backfill_ams(conn, days_back=None):
    """Fetch AMS hog price / cutout series.

    If days_back is None, fetches all available history.
    """
    print(f"\n{'=' * 60}")
    print("  AMS Hog Prices & Cutout (MPR Datamart)")
    print(f"{'=' * 60}")
    try:
        if days_back is not None:
            date_from = datetime.today() - timedelta(days=days_back)
            rows = ams_hog_client.fetch_ams_hog_rows(date_from=date_from)
        else:
            rows = ams_hog_client.fetch_ams_hog_rows()
    except Exception as exc:
        print(f"  AMS hog fetch failed: {exc}")
        return 0

    if not rows:
        return 0
    count = db.upsert_rows(conn, "ams_hog_prices", rows)
    dates = [r["report_date"] for r in rows if r.get("report_date")]
    if dates:
        db.log_fetch(conn, "ams_hog", min(dates), max(dates), count, data_item="mpr_datamart")
    print(f"  AMS backfill complete: {count:,} rows")
    return count


def update_ams(conn):
    """Incremental AMS update — last 90 days."""
    return backfill_ams(conn, days_back=90)


def ingest_ers_trade_totals(conn):
    """Fetch and store ERS pork monthly trade totals."""
    print(f"\n{'=' * 60}")
    print("  ERS Pork Monthly Trade (totals)")
    print(f"{'=' * 60}")
    try:
        rows = ers_trade_pork_client.fetch_trade_rows()
    except Exception as exc:
        print(f"  ERS trade totals fetch failed: {exc}")
        return 0
    if not rows:
        return 0
    count = db.upsert_rows(conn, "ers_trade_totals", rows)
    months = [r["report_month"] for r in rows if r.get("report_month")]
    if months:
        db.log_fetch(conn, "ers_trade", min(months), max(months), count, data_item="monthly_workbook")
    print(f"  ERS trade complete: {count:,} rows")
    return count


def ingest_ers_trade_partners(conn):
    """Fetch and store ERS pork monthly trade partner-country rows."""
    print(f"\n{'=' * 60}")
    print("  ERS Pork Monthly Trade (partner countries)")
    print(f"{'=' * 60}")
    try:
        rows = ers_trade_pork_client.fetch_partner_rows()
    except Exception as exc:
        print(f"  ERS partner-country trade fetch failed: {exc}")
        return 0
    if not rows:
        return 0
    count = db.upsert_rows(conn, "ers_trade_partner_country", rows)
    months = [r["report_month"] for r in rows if r.get("report_month")]
    if months:
        db.log_fetch(conn, "ers_trade_partner", min(months), max(months), count, data_item="partner_country_workbook")
    print(f"  ERS partner-country complete: {count:,} rows")
    return count


def update_ers(conn):
    """Run both ERS pork trade ingests (totals + partner countries)."""
    return ingest_ers_trade_totals(conn) + ingest_ers_trade_partners(conn)


def backfill_retail(conn, year_ge=2021):
    """Fetch AMS retail pork feature metrics and advertised prices."""
    print(f"\n{'=' * 60}")
    print("  AMS Retail Pork Feature Activity")
    print(f"{'=' * 60}")
    start = date(year_ge, 1, 1)
    end = date.today()
    try:
        sections = mars_client.fetch_report(RETAIL_PORK_SLUG_ID, start, end)
    except Exception as exc:
        print(f"  AMS retail pork fetch failed: {exc}")
        return 0
    metric_rows = parsers.parse_retail_metrics(RETAIL_PORK_SLUG_ID, sections)
    price_rows = parsers.parse_retail_prices(RETAIL_PORK_SLUG_ID, sections)
    metric_count = db.upsert_rows(conn, "retail_metrics", metric_rows)
    price_count = db.upsert_rows(conn, "retail_prices", price_rows)
    dates = [row["report_date"] for row in metric_rows + price_rows if row.get("report_date")]
    if dates:
        db.log_fetch(
            conn,
            "ams_retail",
            min(dates),
            max(dates),
            metric_count + price_count,
            slug_id=RETAIL_PORK_SLUG_ID,
            data_item="weekly_retail_pork_feature_activity",
        )
    print(f"  AMS retail complete: {metric_count:,} metric rows, {price_count:,} price rows")
    return metric_count + price_count


def update_retail(conn):
    """Incremental AMS retail update - current and prior year."""
    return backfill_retail(conn, year_ge=date.today().year - 1)


def backfill_fred(conn):
    """Fetch public FRED series used as retail/feed-cost proxies."""
    print(f"\n{'=' * 60}")
    print("  FRED Public Series")
    print(f"{'=' * 60}")
    total = 0
    for series in FRED_SERIES:
        rows = fred_client.fetch_series(series["series_id"], label=series["label"])
        if not rows:
            continue
        count = db.upsert_rows(conn, "fred_series", rows)
        dates = [row["observation_date"] for row in rows if row.get("observation_date")]
        if dates:
            db.log_fetch(
                conn,
                "fred",
                min(dates),
                max(dates),
                count,
                data_item=series["series_id"],
            )
        total += count
    print(f"  FRED complete: {total:,} observations")
    return total


def backfill_comexstat(conn, year_ge=2010, year_le=None):
    """Fetch Brazil pork exports from MDIC/SECEX Comex Stat (monthly, by NCM x country)."""
    year_le = year_le or date.today().year
    print(f"\n{'=' * 60}")
    print(f"  Comex Stat — Brazil Pork Exports (years {year_ge}-{year_le})")
    print(f"{'=' * 60}")
    try:
        rows = comexstat_client.fetch_pork_exports(year_ge, year_le)
    except Exception as exc:
        print(f"  Comex Stat fetch failed: {exc}")
        return 0
    if not rows:
        return 0
    count = db.upsert_rows(conn, "comexstat_pork_exports", rows)
    months = [r["report_month"] for r in rows if r.get("report_month")]
    if months:
        db.log_fetch(conn, "comexstat", min(months), max(months), count, data_item="pork_exports")
    print(f"  Comex Stat complete: {count:,} rows")
    return count


def update_comexstat(conn):
    """Incremental Comex Stat update — current and prior year (trade data revises)."""
    return backfill_comexstat(conn, year_ge=date.today().year - 1)


def ingest_wasde(conn):
    """Fetch the latest WASDE pork forecasts (production, exports, hog price)."""
    print(f"\n{'=' * 60}")
    print("  USDA WASDE — Pork production / exports / hog-price forecasts")
    print(f"{'=' * 60}")
    try:
        rows = wasde_client.fetch_forecast_rows()
    except Exception as exc:
        print(f"  WASDE fetch failed: {exc}")
        return 0
    if not rows:
        return 0
    count = db.upsert_rows(conn, "wasde_forecasts", rows)
    vintages = [r["report_month"] for r in rows if r.get("report_month")]
    if vintages:
        db.log_fetch(conn, "wasde", min(vintages), max(vintages), count, data_item="pork_forecasts")
    print(f"  WASDE complete: {count:,} rows")
    return count


def ingest_ers_food_availability(conn):
    """Fetch ERS per-capita pork availability + supply-and-use (annual)."""
    print(f"\n{'=' * 60}")
    print("  ERS Food Availability — Pork per-capita & disappearance")
    print(f"{'=' * 60}")
    try:
        rows = ers_food_availability_client.fetch_pork_rows()
    except Exception as exc:
        print(f"  ERS food availability fetch failed: {exc}")
        return 0
    if not rows:
        return 0
    count = db.upsert_rows(conn, "ers_food_availability", rows)
    years = [str(r["year"]) for r in rows if r.get("year")]
    if years:
        db.log_fetch(conn, "ers_food_avail", min(years), max(years), count, data_item="red_meat_pork")
    print(f"  ERS food availability complete: {count:,} rows")
    return count


def backfill_census(conn, year_ge=2010, year_le=None):
    """Fetch US pork trade (product weight) by HS code from the Census API.

    No-ops gracefully (0 rows) when CENSUS_API_KEY is not set.
    """
    year_le = year_le or date.today().year
    print(f"\n{'=' * 60}")
    print(f"  US Census — Pork Trade by HS, product weight (years {year_ge}-{year_le})")
    print(f"{'=' * 60}")
    try:
        rows = census_trade_client.fetch_pork_trade(year_ge, year_le)
    except Exception as exc:
        print(f"  Census trade fetch failed: {exc}")
        return 0
    if not rows:
        return 0
    count = db.upsert_rows(conn, "census_pork_trade", rows)
    months = [r["report_month"] for r in rows if r.get("report_month")]
    if months:
        db.log_fetch(conn, "census_trade", min(months), max(months), count, data_item="pork_hs_trade")
    print(f"  Census trade complete: {count:,} rows")
    return count


def update_census(conn):
    """Incremental Census update — trailing months only (each HS10 month pull is
    a large response; trade revises a few months back). No-ops without a key."""
    if not census_trade_client.api_key():
        census_trade_client.fetch_pork_trade(0, 0)  # prints the no-key note
        return 0
    print(f"\n{'=' * 60}")
    print("  US Census — Pork Trade by HS, product weight (trailing months)")
    print(f"{'=' * 60}")
    try:
        rows = census_trade_client.fetch_pork_trade(
            0, 0, months=census_trade_client.recent_months(4)
        )
    except Exception as exc:
        print(f"  Census trade update failed: {exc}")
        return 0
    if not rows:
        return 0
    count = db.upsert_rows(conn, "census_pork_trade", rows)
    months = [r["report_month"] for r in rows if r.get("report_month")]
    if months:
        db.log_fetch(conn, "census_trade", min(months), max(months), count, data_item="pork_hs_trade")
    print(f"  Census trade update complete: {count:,} rows")
    return count


# ── Smoke tests ───────────────────────────────────────────────────────────

def run_smoke_tests(conn):
    """Assert that every major table has at least some data.

    Exits with code 1 on failure (usable in CI pipelines).
    """
    print(f"\n{'=' * 60}")
    print("  Smoke Tests")
    print(f"{'=' * 60}")

    checks = [
        ("nass_data",               "SELECT COUNT(*) FROM nass_data"),
        ("ams_hog_prices",          "SELECT COUNT(*) FROM ams_hog_prices"),
        ("ers_trade_totals",        "SELECT COUNT(*) FROM ers_trade_totals"),
        ("ers_trade_partner_country", "SELECT COUNT(*) FROM ers_trade_partner_country"),
        ("retail_metrics",          "SELECT COUNT(*) FROM retail_metrics"),
        ("fred_series",             "SELECT COUNT(*) FROM fred_series"),
        ("comexstat_pork_exports",  "SELECT COUNT(*) FROM comexstat_pork_exports"),
    ]

    failed = []
    for table, query in checks:
        count = conn.execute(query).fetchone()[0]
        status = "OK" if count > 0 else "FAIL"
        print(f"  {table:<30} {count:>8,} rows  [{status}]")
        if count == 0:
            failed.append(table)

    if failed:
        print(f"\n  SMOKE TEST FAILED — empty tables: {', '.join(failed)}")
        return False
    else:
        print("\n  All smoke tests passed.")
        return True


def show_status(conn):
    """Print a summary of what's in the database."""
    status = db.get_status(conn)
    if not status:
        print("  Database is empty. Run a backfill first.")
        return
    print(f"\n{'Table':<28} {'Group/Item':<50} {'Rows':>8} {'From':>12} {'To':>12}")
    print("-" * 116)
    for item in status:
        group = str(item["group"] or "")
        if len(group) > 48:
            group = group[:45] + "..."
        print(f"{item['table']:<28} {group:<50} {item['rows']:>8,} {str(item['min_date'] or '—'):>12} {str(item['max_date'] or '—'):>12}")


# ── CLI ───────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Pork chartbook ingestion pipeline")

    # Backfill flags
    ap.add_argument("--backfill-all", action="store_true",
                    help="Full backfill of all sources")
    ap.add_argument("--backfill-nass", action="store_true",
                    help="Backfill NASS hog series")
    ap.add_argument("--backfill-ams", action="store_true",
                    help="Backfill AMS hog prices / cutout (all history)")
    ap.add_argument("--backfill-ers", action="store_true",
                    help="Backfill ERS pork trade workbook")
    ap.add_argument("--backfill-retail", action="store_true",
                    help="Backfill AMS retail pork feature activity")
    ap.add_argument("--backfill-fred", action="store_true",
                    help="Backfill FRED retail/feed proxy series")
    ap.add_argument("--backfill-comex", action="store_true",
                    help="Backfill Comex Stat Brazil pork exports")
    ap.add_argument("--backfill-census", action="store_true",
                    help="Backfill US Census pork trade by HS (product weight; needs CENSUS_API_KEY)")
    ap.add_argument("--backfill-ers-food", action="store_true",
                    help="Backfill ERS per-capita pork availability & disappearance (annual)")
    ap.add_argument("--backfill-wasde", action="store_true",
                    help="Fetch latest WASDE pork production/export/hog-price forecasts")

    # Update flags (incremental)
    ap.add_argument("--update", action="store_true",
                    help="Incremental update of all sources")

    # Options
    ap.add_argument("--nass-year-ge", type=int, default=2010,
                    help="Start year for NASS backfill (default: 2010)")
    ap.add_argument("--retail-year-ge", type=int, default=2021,
                    help="Start year for AMS retail feature backfill (default: 2021)")
    ap.add_argument("--comex-year-ge", type=int, default=2010,
                    help="Start year for Comex Stat Brazil pork export backfill (default: 2010)")
    ap.add_argument("--census-year-ge", type=int, default=2010,
                    help="Start year for US Census pork-trade backfill (default: 2010)")
    ap.add_argument("--db", default=None,
                    help="Path to SQLite database file")

    # Utilities
    ap.add_argument("--status", action="store_true",
                    help="Show database status summary")
    ap.add_argument("--smoke-test", action="store_true",
                    help="Run smoke tests (exits 1 if any table is empty)")

    args = ap.parse_args()

    conn = db.init_db(args.db)
    try:
        if args.status:
            show_status(conn)
            return

        if args.smoke_test:
            passed = run_smoke_tests(conn)
            sys.exit(0 if passed else 1)

        if args.backfill_all or args.backfill_nass:
            backfill_nass(conn, year_ge=args.nass_year_ge)

        if args.backfill_all or args.backfill_ams:
            backfill_ams(conn)  # all history

        if args.backfill_all or args.backfill_ers:
            ingest_ers_trade_totals(conn)
            ingest_ers_trade_partners(conn)

        if args.backfill_all or args.backfill_retail:
            backfill_retail(conn, year_ge=args.retail_year_ge)

        if args.backfill_all or args.backfill_fred:
            backfill_fred(conn)

        if args.backfill_all or args.backfill_comex:
            backfill_comexstat(conn, year_ge=args.comex_year_ge)

        if args.backfill_all or args.backfill_census:
            backfill_census(conn, year_ge=args.census_year_ge)

        if args.backfill_all or args.backfill_ers_food:
            ingest_ers_food_availability(conn)

        if args.backfill_all or args.backfill_wasde:
            ingest_wasde(conn)

        if args.update:
            update_nass(conn)
            update_ams(conn)
            ingest_ers_trade_totals(conn)
            ingest_ers_trade_partners(conn)
            update_retail(conn)
            backfill_fred(conn)
            update_comexstat(conn)
            update_census(conn)
            ingest_ers_food_availability(conn)
            ingest_wasde(conn)

        all_actions = [
            args.backfill_all, args.backfill_nass, args.backfill_ams,
            args.backfill_ers, args.backfill_retail, args.backfill_fred,
            args.backfill_comex, args.backfill_census, args.backfill_ers_food,
            args.backfill_wasde, args.update, args.status, args.smoke_test,
        ]
        if not any(all_actions):
            ap.print_help()

    finally:
        conn.close()


if __name__ == "__main__":
    main()
