#!/usr/bin/env python3
"""
ingest.py — pork chartbook ingestion pipeline.

Data sources:
  NASS QuickStats — Quarterly Hogs & Pigs report, weekly slaughter, prices
  AMS MPR Datamart — Barrow/gilt prices (LM_HG201), pork cutout (LM_PK602)
  ERS Trade        — Monthly pork import/export workbook

Usage:
  python -m porkchartbook.ingest --backfill-all
  python -m porkchartbook.ingest --update
  python -m porkchartbook.ingest --backfill-nass
  python -m porkchartbook.ingest --backfill-ams
  python -m porkchartbook.ingest --backfill-ers
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
from .clients import ers_trade_pork_client
from .clients import nass_client


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
    # Prices received
    {
        "short_desc": "HOGS - PRICE RECEIVED, MEASURED IN $ / CWT",
        "label": "Hog price received ($/cwt)",
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
    records = nass_client.fetch_data_item(short_desc, year__GE=str(year_ge))
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

    # Update flags (incremental)
    ap.add_argument("--update", action="store_true",
                    help="Incremental update of all sources")

    # Options
    ap.add_argument("--nass-year-ge", type=int, default=2010,
                    help="Start year for NASS backfill (default: 2010)")
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

        if args.update:
            update_nass(conn)
            update_ams(conn)
            ingest_ers_trade_totals(conn)
            ingest_ers_trade_partners(conn)

        all_actions = [
            args.backfill_all, args.backfill_nass, args.backfill_ams,
            args.backfill_ers, args.update, args.status, args.smoke_test,
        ]
        if not any(all_actions):
            ap.print_help()

    finally:
        conn.close()


if __name__ == "__main__":
    main()
