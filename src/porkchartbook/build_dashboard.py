#!/usr/bin/env python3
"""
build_dashboard.py — Build the pork industry executive dashboard.

Reads from SQLite → writes docs/data.json.
The static docs/index.html fetches data.json at runtime.

Usage:
  python -m porkchartbook.build_dashboard
  python -m porkchartbook.build_dashboard --json-only
  python -m porkchartbook.build_dashboard --db /path/to/porkchartbook.db
"""

from __future__ import annotations

import argparse
import json
from datetime import date

from . import db
from .paths import DOCS_ROOT


DATA_JSON_PATH = DOCS_ROOT / "data.json"

MONTH_MAP = {
    "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04",
    "MAY": "05", "JUN": "06", "JUL": "07", "AUG": "08",
    "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12",
    "FIRST OF JAN": "01", "FIRST OF FEB": "02", "FIRST OF MAR": "03",
    "FIRST OF APR": "04", "FIRST OF MAY": "05", "FIRST OF JUN": "06",
    "FIRST OF JUL": "07", "FIRST OF AUG": "08", "FIRST OF SEP": "09",
    "FIRST OF OCT": "10", "FIRST OF NOV": "11", "FIRST OF DEC": "12",
    "END OF JAN": "01", "END OF FEB": "02", "END OF MAR": "03",
    "END OF APR": "04", "END OF MAY": "05", "END OF JUN": "06",
    "END OF JUL": "07", "END OF AUG": "08", "END OF SEP": "09",
    "END OF OCT": "10", "END OF NOV": "11", "END OF DEC": "12",
}

QUARTER_MAP = {
    "JAN THRU MAR": ("01", "Q1"),
    "APR THRU JUN": ("04", "Q2"),
    "JUL THRU SEP": ("07", "Q3"),
    "OCT THRU DEC": ("10", "Q4"),
    "DEC 1": ("12", "DEC1"),
    "JUNE 1": ("06", "JUN1"),
    "SEPT 1": ("09", "SEP1"),
    "MARCH 1": ("03", "MAR1"),
}


# ── Helpers ───────────────────────────────────────────────────────────────

def _nass_date(year, ref_period):
    """Convert (year, reference_period_desc) to YYYY-MM label, or None."""
    ref = (ref_period or "").strip().upper()
    mm = MONTH_MAP.get(ref)
    if mm:
        return f"{year}-{mm}"
    for pattern, (mm, _) in QUARTER_MAP.items():
        if pattern in ref:
            return f"{year}-{mm}"
    return None


def _nass_sort_key(year, ref_period):
    ref = (ref_period or "").strip().upper()
    mm = MONTH_MAP.get(ref)
    if mm:
        return year, int(mm)
    for pattern, (mm, _) in QUARTER_MAP.items():
        if pattern in ref:
            return year, int(mm)
    return year, 99


def _latest(dates, values):
    """Return {'date': ..., 'value': ...} for the most recent non-null value."""
    for idx in range(len(values) - 1, -1, -1):
        if values[idx] is not None:
            return {"date": dates[idx], "value": values[idx]}
    return {"date": None, "value": None}


def _nass_national(conn, data_item):
    """Fetch NASS national rows for a data item, sorted chronologically."""
    rows = conn.execute(
        """
        SELECT year, reference_period, value
        FROM nass_data
        WHERE data_item = ?
          AND agg_level = 'NATIONAL'
          AND value IS NOT NULL
        """,
        (data_item,),
    ).fetchall()
    points = []
    for year, ref_period, value in rows:
        label = _nass_date(year, ref_period)
        if label:
            points.append((_nass_sort_key(year, ref_period), label, value))
    points.sort(key=lambda row: row[0])
    dates = [row[1] for row in points]
    values = [row[2] for row in points]
    return dates, values


def _ams_series(conn, report_name, series_name):
    """Fetch AMS price series rows sorted by date."""
    rows = conn.execute(
        """
        SELECT report_date, value
        FROM ams_hog_prices
        WHERE report_name = ? AND series_name = ? AND value IS NOT NULL
        ORDER BY report_date
        """,
        (report_name, series_name),
    ).fetchall()
    return [row[0] for row in rows], [row[1] for row in rows]


# ── KPI section ───────────────────────────────────────────────────────────

def build_kpi(conn):
    """Top-of-page KPI tiles."""
    # Total hog inventory — latest quarterly value from NASS
    inv_dates, inv_values = _nass_national(conn, "HOGS - INVENTORY")
    inventory_latest = _latest(inv_dates, inv_values)

    # Weekly FI slaughter — latest weekly value
    slaught_dates, slaught_values = _nass_national(
        conn, "HOGS - SLAUGHTERED, FEDERALLY INSPECTED, MEASURED IN HEAD"
    )
    slaughter_latest = _latest(slaught_dates, slaught_values)

    # Barrow/gilt base price ($/cwt) from AMS LM_HG201
    price_dates, price_values = _ams_series(conn, "LM_HG201", "base_price")
    price_latest = _latest(price_dates, price_values)

    # Pork cutout value ($/cwt) from AMS LM_PK602
    cutout_dates, cutout_values = _ams_series(conn, "LM_PK602", "cutout_value")
    cutout_latest = _latest(cutout_dates, cutout_values)

    # YTD export volume (pork + variety meat exports, current year)
    current_year = date.today().year
    ytd_row = conn.execute(
        """
        SELECT SUM(value)
        FROM ers_trade_totals
        WHERE commodity = 'pork'
          AND flow = 'export'
          AND substr(report_month, 1, 4) = ?
        """,
        (str(current_year),),
    ).fetchone()
    ytd_exports = ytd_row[0] if ytd_row and ytd_row[0] else None

    return {
        "total_hog_inventory": inventory_latest,
        "weekly_slaughter_head": slaughter_latest,
        "barrow_gilt_base_price": price_latest,
        "pork_cutout_value": cutout_latest,
        "ytd_export_volume_1000lb": {"value": ytd_exports, "year": current_year},
    }


# ── Herd section ──────────────────────────────────────────────────────────

def build_herd(conn):
    """Quarterly Hogs & Pigs inventory and pig crop."""
    total_dates, total_values = _nass_national(conn, "HOGS - INVENTORY")
    breeding_dates, breeding_values = _nass_national(conn, "HOGS, BREEDING - INVENTORY")
    market_dates, market_values = _nass_national(conn, "HOGS, MARKET - INVENTORY")
    litter_dates, litter_values = _nass_national(conn, "HOGS - LITTERS, MEASURED IN LITTERS")
    pigcrop_dates, pigcrop_values = _nass_national(conn, "HOGS - PIG CROP, MEASURED IN HEAD")

    return {
        "total_inventory": {"dates": total_dates, "values": total_values},
        "breeding_inventory": {"dates": breeding_dates, "values": breeding_values},
        "market_inventory": {"dates": market_dates, "values": market_values},
        "litters_farrowed": {"dates": litter_dates, "values": litter_values},
        "pig_crop": {"dates": pigcrop_dates, "values": pigcrop_values},
    }


# ── Slaughter & Production section ───────────────────────────────────────

def build_slaughter_production(conn):
    """Weekly FI slaughter and pork production."""
    slaughter_head_dates, slaughter_head_values = _nass_national(
        conn, "HOGS - SLAUGHTERED, FEDERALLY INSPECTED, MEASURED IN HEAD"
    )
    slaughter_lb_dates, slaughter_lb_values = _nass_national(
        conn, "HOGS - SLAUGHTERED, FEDERALLY INSPECTED, MEASURED IN LB, LIVE BASIS"
    )
    pork_prod_dates, pork_prod_values = _nass_national(
        conn, "HOGS - PORK, MEASURED IN LB"
    )

    # Monthly average carcass weight from AMS
    weight_dates, weight_values = _ams_series(conn, "LM_HG201", "avg_carcass_weight")

    return {
        "slaughter_head": {"dates": slaughter_head_dates, "values": slaughter_head_values},
        "slaughter_live_lb": {"dates": slaughter_lb_dates, "values": slaughter_lb_values},
        "pork_production_lb": {"dates": pork_prod_dates, "values": pork_prod_values},
        "avg_carcass_weight": {"dates": weight_dates, "values": weight_values},
    }


# ── Prices section ────────────────────────────────────────────────────────

def build_prices(conn):
    """Barrow/gilt prices, pork cutout, and primal values."""
    base_dates, base_values = _ams_series(conn, "LM_HG201", "base_price")
    net_dates, net_values = _ams_series(conn, "LM_HG201", "net_price")
    cutout_dates, cutout_values = _ams_series(conn, "LM_PK602", "cutout_value")

    # Primal values
    primals = {}
    for series_name, label in [
        ("loin_value", "Loin"),
        ("butt_value", "Butt"),
        ("picnic_value", "Picnic"),
        ("rib_value", "Rib"),
        ("ham_value", "Ham"),
        ("belly_value", "Belly"),
    ]:
        dates, values = _ams_series(conn, "LM_PK602", series_name)
        primals[label] = {"dates": dates, "values": values}

    # NASS price received (monthly average from producers)
    nass_price_dates, nass_price_values = _nass_national(
        conn, "HOGS - PRICE RECEIVED, MEASURED IN $ / CWT"
    )

    return {
        "barrow_gilt_base_price": {"dates": base_dates, "values": base_values},
        "barrow_gilt_net_price": {"dates": net_dates, "values": net_values},
        "pork_cutout_value": {"dates": cutout_dates, "values": cutout_values},
        "primals": primals,
        "nass_price_received": {"dates": nass_price_dates, "values": nass_price_values},
    }


# ── Trade section ─────────────────────────────────────────────────────────

def build_trade(conn):
    """Monthly pork import/export totals and partner-country breakdown."""
    # Totals by flow and product
    trade_rows = conn.execute(
        """
        SELECT report_month, flow, product, section_label, value
        FROM ers_trade_totals
        WHERE commodity = 'pork'
        ORDER BY report_month, flow, product
        """
    ).fetchall()
    trade_map = {}
    for report_month, flow, product, section_label, value in trade_rows:
        trade_map.setdefault(report_month, {})[f"{flow}_{product}"] = value
    trade_dates = sorted(trade_map)

    # Partner-country breakdown — top 6 export destinations, top 4 import sources
    partner_rows = conn.execute(
        """
        SELECT report_month, flow, country, value
        FROM ers_trade_partner_country
        WHERE commodity = 'pork' AND product = 'pork'
        ORDER BY report_month, flow, country
        """
    ).fetchall()

    export_series = {"dates": [], "series": {}}
    import_series = {"dates": [], "series": {}}

    if partner_rows:
        export_totals = {}
        import_totals = {}
        for report_month, flow, country, value in partner_rows:
            if flow == "export":
                export_totals[country] = export_totals.get(country, 0) + (value or 0)
            elif flow == "import":
                import_totals[country] = import_totals.get(country, 0) + (value or 0)

        top_exports = sorted(export_totals, key=lambda c: export_totals[c], reverse=True)[:6]
        top_imports = sorted(import_totals, key=lambda c: import_totals[c], reverse=True)[:4]

        exp_map = {}
        imp_map = {}
        for report_month, flow, country, value in partner_rows:
            if flow == "export" and country in top_exports:
                exp_map.setdefault(report_month, {})[country] = value
            if flow == "import" and country in top_imports:
                imp_map.setdefault(report_month, {})[country] = value

        exp_dates = sorted(exp_map)
        imp_dates = sorted(imp_map)
        export_series = {
            "dates": exp_dates,
            "series": {c: [exp_map[label].get(c) for label in exp_dates] for c in top_exports},
        }
        import_series = {
            "dates": imp_dates,
            "series": {c: [imp_map[label].get(c) for label in imp_dates] for c in top_imports},
        }

    return {
        "trade_totals": {
            "dates": trade_dates,
            "export_pork": [trade_map[label].get("export_pork") for label in trade_dates],
            "import_pork": [trade_map[label].get("import_pork") for label in trade_dates],
            "export_variety_meat": [trade_map[label].get("export_variety_meat") for label in trade_dates],
            "import_variety_meat": [trade_map[label].get("import_variety_meat") for label in trade_dates],
            "export_live_swine": [trade_map[label].get("export_live_swine") for label in trade_dates],
            "import_live_swine": [trade_map[label].get("import_live_swine") for label in trade_dates],
        },
        "exports_by_destination": export_series,
        "imports_by_source": import_series,
    }


# ── Data freshness ────────────────────────────────────────────────────────

def build_data_freshness(conn):
    rows = conn.execute(
        """
        SELECT id, source, COALESCE(data_item, CAST(slug_id AS TEXT)) AS item,
               fetched_at, fetch_end, rows_fetched, status
        FROM etl_log
        ORDER BY source, item, fetched_at, id
        """
    ).fetchall()
    grouped = {}
    for row_id, source, item, fetched_at, fetch_end, rows_fetched, status in rows:
        key = (source, item)
        entry = grouped.setdefault(key, {
            "source": source,
            "item": item,
            "last_fetch": fetched_at,
            "latest_data": fetch_end,
            "total_rows": 0,
            "status": status,
            "_last_id": row_id,
        })
        entry["total_rows"] += rows_fetched or 0
        if fetch_end and (entry["latest_data"] is None or fetch_end > entry["latest_data"]):
            entry["latest_data"] = fetch_end
        if (fetched_at, row_id) >= (entry["last_fetch"], entry["_last_id"]):
            entry["last_fetch"] = fetched_at
            entry["status"] = status
            entry["_last_id"] = row_id
    results = []
    for entry in grouped.values():
        entry.pop("_last_id", None)
        results.append(entry)
    return sorted(results, key=lambda item: (item["source"], item["item"] or ""))


# ── Main build ────────────────────────────────────────────────────────────

def build_data_json(conn):
    """Query SQLite, assemble all chart data, write docs/data.json."""
    data = {
        "kpi": build_kpi(conn),
        "herd": build_herd(conn),
        "slaughter_production": build_slaughter_production(conn),
        "prices": build_prices(conn),
        "trade": build_trade(conn),
        "data_freshness": build_data_freshness(conn),
        "meta": {
            "updated": date.today().strftime("%B %d, %Y"),
            "source": "USDA NASS, USDA AMS, USDA ERS",
        },
    }
    DOCS_ROOT.mkdir(parents=True, exist_ok=True)
    with open(DATA_JSON_PATH, "w") as handle:
        json.dump(data, handle, separators=(",", ":"))
    size_kb = DATA_JSON_PATH.stat().st_size / 1024
    print(f"  data.json written ({size_kb:.0f} KB) → {DATA_JSON_PATH}")
    return data


def main():
    ap = argparse.ArgumentParser(description="Build the pork chartbook dashboard")
    ap.add_argument("--json-only", action="store_true",
                    help="Only write docs/data.json (skip HTML check)")
    ap.add_argument("--db", default=None,
                    help="Path to SQLite database file")
    args = ap.parse_args()

    conn = db.init_db(args.db)
    try:
        build_data_json(conn)
        if not args.json_only:
            index_path = DOCS_ROOT / "index.html"
            if index_path.exists():
                print(f"  index.html already exists at {index_path}")
            else:
                print(f"  WARNING: index.html not found at {index_path}")
                print("  Run the dashboard after placing index.html in docs/")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
