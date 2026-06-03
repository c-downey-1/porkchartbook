#!/usr/bin/env python3
"""
build_dashboard.py - Build the pork industry executive chartbook.

Reads from SQLite and writes docs/data.json for the static dashboard.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date, datetime, timedelta

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
    "YEAR": "12",
}

QUARTER_MAP = {
    "JAN THRU MAR": "03",
    "APR THRU JUN": "06",
    "JUL THRU SEP": "09",
    "OCT THRU DEC": "12",
    "DEC THRU FEB": "02",
    "MAR THRU MAY": "05",
    "JUN THRU AUG": "08",
    "SEP THRU NOV": "11",
    "MARCH 1": "03",
    "JUNE 1": "06",
    "SEPT 1": "09",
    "DEC 1": "12",
}

NASS_ITEMS = {
    "total_inventory": "HOGS - INVENTORY",
    "breeding_inventory": "HOGS, BREEDING - INVENTORY",
    "market_inventory": "HOGS, MARKET - INVENTORY",
    "market_under_50": [
        "HOGS, MARKET, LT 50 LBS - INVENTORY",
        "HOGS, MARKET, UNDER 50 LBS - INVENTORY",
        "HOGS, MARKET, LESS THAN 50 LBS - INVENTORY",
    ],
    "market_50_119": "HOGS, MARKET, 50 TO 119 LBS - INVENTORY",
    "market_120_179": "HOGS, MARKET, 120 TO 179 LBS - INVENTORY",
    "market_180_over": [
        "HOGS, MARKET, GE 180 LBS - INVENTORY",
        "HOGS, MARKET, 180 LBS & OVER - INVENTORY",
        "HOGS, MARKET, 180 LBS OR MORE - INVENTORY",
    ],
    "sows_farrowed": "HOGS, SOWS - FARROWED, MEASURED IN HEAD",
    "pigs_per_litter": "HOGS - LITTER RATE, MEASURED IN PIGS / LITTER",
    "pig_crop": "HOGS - PIG CROP, MEASURED IN HEAD",
    "price_received": "HOGS - PRICE RECEIVED, MEASURED IN $ / CWT",
    # Monthly Livestock Slaughter (canonical "SLAUGHTER, COMMERCIAL" word order) —
    # the true ~99%-of-industry commercial series.
    "commercial_slaughter_head": "HOGS, SLAUGHTER, COMMERCIAL - SLAUGHTERED, MEASURED IN HEAD",
    "fi_slaughter_head": "HOGS, SLAUGHTER, COMMERCIAL, FI - SLAUGHTERED, MEASURED IN HEAD",
    "barrows_gilts_head": "HOGS, BARROWS & GILTS, SLAUGHTER, COMMERCIAL, FI - SLAUGHTERED, MEASURED IN HEAD",
    "sows_slaughter_head": "HOGS, SOWS, SLAUGHTER, COMMERCIAL, FI - SLAUGHTERED, MEASURED IN HEAD",
    "boars_slaughter_head": "HOGS, BOARS, SLAUGHTER, COMMERCIAL, FI - SLAUGHTERED, MEASURED IN HEAD",
    "commercial_live_weight": "HOGS, SLAUGHTER, COMMERCIAL - SLAUGHTERED, MEASURED IN LB / HEAD, LIVE BASIS",
    "barrows_gilts_dressed_weight": "HOGS, BARROWS & GILTS, SLAUGHTER, COMMERCIAL, FI - SLAUGHTERED, MEASURED IN LB / HEAD, DRESSED BASIS",
    "commercial_pork_production": "PORK, SLAUGHTER, COMMERCIAL - PRODUCTION, MEASURED IN LB",
    "cold_storage_total": "PORK, COLD STORAGE, FROZEN - STOCKS, MEASURED IN LB",
    "cold_storage_bellies": "PORK, BELLIES, COLD STORAGE, FROZEN - STOCKS, MEASURED IN LB",
    "cold_storage_hams": "PORK, HAMS, COLD STORAGE, FROZEN - STOCKS, MEASURED IN LB",
    "cold_storage_loins": "PORK, LOINS, COLD STORAGE, FROZEN - STOCKS, MEASURED IN LB",
}

KG_TO_LB = 2.20462  # pounds per kilogram, for converting Comex Stat net_kg to lb

# Comex Stat returns Portuguese country names; translate the realistic top
# pork destinations to English for the dashboard. Unmapped names fall back to
# the original label.
BRAZIL_COUNTRY_EN = {
    "China": "China",
    "Hong Kong": "Hong Kong",
    "Filipinas": "Philippines",
    "Chile": "Chile",
    "Japão": "Japan",
    "Singapura": "Singapore",
    "Vietnã": "Vietnam",
    "México": "Mexico",
    "Coreia do Sul": "South Korea",
    "Rússia": "Russia",
    "Uruguai": "Uruguay",
    "Argentina": "Argentina",
    "Angola": "Angola",
    "Estados Unidos": "United States",
    "Reino Unido": "United Kingdom",
    "Geórgia": "Georgia",
    "Costa do Marfim": "Côte d'Ivoire",
    "República Dominicana": "Dominican Republic",
    "Albânia": "Albania",
    "Congo": "Congo",
}


# -- Generic helpers -------------------------------------------------------

def _series(dates=None, values=None):
    return {"dates": dates or [], "values": values or []}


def _nass_date(year, reference_period):
    ref = (reference_period or "").strip().upper()
    month = MONTH_MAP.get(ref)
    if month:
        return f"{int(year):04d}-{month}"
    for pattern, mapped_month in QUARTER_MAP.items():
        if pattern in ref:
            return f"{int(year):04d}-{mapped_month}"
    return None


def _nass_sort_key(year, reference_period):
    label = _nass_date(year, reference_period)
    if label:
        return label
    return f"{int(year):04d}-99"


def _nass_national(conn, data_item, monthly_only=False):
    data_items = data_item if isinstance(data_item, (list, tuple)) else [data_item]
    placeholders = ",".join("?" for _ in data_items)
    rows = conn.execute(
        f"""
        SELECT year, reference_period, freq, value
        FROM nass_data
        WHERE data_item IN ({placeholders})
          AND agg_level = 'NATIONAL'
          AND value IS NOT NULL
        """,
        tuple(data_items),
    ).fetchall()
    by_label = {}
    for year, reference_period, freq, value in rows:
        ref = (reference_period or "").upper()
        if monthly_only and ((freq or "").upper() != "MONTHLY" or ref not in MONTH_MAP):
            continue
        label = _nass_date(year, reference_period)
        if not label:
            continue
        priority = 0
        if ref in MONTH_MAP:
            priority = 2
        elif "THRU" in ref:
            priority = 1
        current = by_label.get(label)
        if current is None or priority >= current[0]:
            by_label[label] = (priority, value, _nass_sort_key(year, reference_period))
    labels = sorted(by_label, key=lambda item: by_label[item][2])
    return labels, [by_label[label][1] for label in labels]


def _ams_series(conn, report_name, series_name):
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


def _fred_series(conn, series_id):
    rows = conn.execute(
        """
        SELECT observation_date, value
        FROM fred_series
        WHERE series_id = ? AND value IS NOT NULL
        ORDER BY observation_date
        """,
        (series_id,),
    ).fetchall()
    return [row[0] for row in rows], [row[1] for row in rows]


def _latest(dates, values):
    for idx in range(len(values) - 1, -1, -1):
        value = values[idx]
        if value is not None:
            return {"date": dates[idx], "value": value}
    return {"date": None, "value": None}


def _monthly_aggregate(dates, values, method="avg", drop_incomplete_current_month=True):
    buckets = defaultdict(list)
    for label, value in zip(dates, values):
        if value is None or not label:
            continue
        month = label[:7]
        if len(month) == 7:
            buckets[month].append(value)
    out_dates = sorted(buckets)
    out_values = []
    for label in out_dates:
        vals = buckets[label]
        if method == "sum":
            out_values.append(sum(vals))
        else:
            out_values.append(sum(vals) / len(vals))
    if drop_incomplete_current_month and out_dates:
        current_month = date.today().strftime("%Y-%m")
        if out_dates[-1] == current_month:
            out_dates = out_dates[:-1]
            out_values = out_values[:-1]
    return out_dates, out_values


def _aligned_values(series_a, series_b):
    dates_a, values_a = series_a
    dates_b, values_b = series_b
    map_a = dict(zip(dates_a, values_a))
    map_b = dict(zip(dates_b, values_b))
    labels = sorted(set(map_a) & set(map_b))
    return labels, [map_a[label] for label in labels], [map_b[label] for label in labels]


def _subtract_series(series_a, series_b):
    labels, values_a, values_b = _aligned_values(series_a, series_b)
    return labels, [
        (a - b) if a is not None and b is not None else None
        for a, b in zip(values_a, values_b)
    ]


def _divide_series(series_a, series_b, multiplier=1):
    labels, values_a, values_b = _aligned_values(series_a, series_b)
    return labels, [
        (a / b * multiplier) if a is not None and b not in (None, 0) else None
        for a, b in zip(values_a, values_b)
    ]


def _estimated_daily_production(conn):
    """Daily estimated pork production = daily head count x daily avg carcass weight."""
    head_dates, head_values = _ams_series(conn, "LM_HG201", "head_count_barrows_gilts")
    weight_dates, weight_values = _ams_series(conn, "LM_HG201", "avg_carcass_weight")
    labels, heads, weights = _aligned_values((head_dates, head_values), (weight_dates, weight_values))
    daily_lbs = [
        (head * weight) if head is not None and weight is not None else None
        for head, weight in zip(heads, weights)
    ]
    return labels, daily_lbs


def _estimated_monthly_production(conn):
    return _monthly_aggregate(*_estimated_daily_production(conn), method="sum")


def _value_one_year_ago(dates, values):
    latest = _latest(dates, values)
    if not latest["date"]:
        return None
    label = latest["date"]
    target = None
    if len(label) >= 7:
        try:
            target = f"{int(label[:4]) - 1}{label[4:]}"
        except ValueError:
            target = None
    value_map = dict(zip(dates, values))
    if target in value_map:
        return value_map[target]
    if len(dates) >= 13 and len(label) == 7:
        return values[-13]
    if len(dates) >= 253 and len(label) == 10:
        return values[-253]
    if len(dates) >= 5:
        return values[-5]
    return None


def _pct_change_text(dates, values, lower_is_good=False):
    latest = _latest(dates, values)
    prior = _value_one_year_ago(dates, values)
    if latest["value"] is None or prior in (None, 0):
        return None
    change = (latest["value"] / prior - 1) * 100
    if abs(change) < 0.05:
        direction = "flat"
    else:
        direction = "down" if change < 0 else "up"
    signal = "neutral"
    if abs(change) >= 2:
        signal = "positive" if (change > 0) ^ lower_is_good else "negative"
    return {
        "change": change,
        "direction": direction,
        "signal": signal,
        "text": f"{direction} {abs(change):.1f}% yr/yr",
    }


def _summary(label, dates, values, unit="", scale=1, lower_is_good=False):
    latest = _latest(dates, values)
    if latest["value"] is None:
        return f"{label}: public source is wired, but no usable history is currently loaded."
    value = latest["value"] / scale
    suffix = f" {unit}" if unit else ""
    change = _pct_change_text(dates, values, lower_is_good=lower_is_good)
    change_text = f", {change['text']}" if change else ""
    return f"{label}: latest reading is {value:,.1f}{suffix} in {latest['date']}{change_text}."


def _top_entries(series_map, count=6):
    totals = []
    for name, values in series_map.items():
        total = sum(value or 0 for value in values)
        totals.append((total, name))
    return [name for _, name in sorted(totals, reverse=True)[:count]]


# -- Section builders ------------------------------------------------------

def build_herd_supply(conn):
    data = {
        "total_inventory": _series(*_nass_national(conn, NASS_ITEMS["total_inventory"])),
        "breeding_inventory": _series(*_nass_national(conn, NASS_ITEMS["breeding_inventory"])),
        "market_inventory": _series(*_nass_national(conn, NASS_ITEMS["market_inventory"])),
        "sows_farrowed": _series(*_nass_national(conn, NASS_ITEMS["sows_farrowed"], monthly_only=True)),
        "pigs_per_litter": _series(*_nass_national(conn, NASS_ITEMS["pigs_per_litter"], monthly_only=True)),
        "pig_crop": _series(*_nass_national(conn, NASS_ITEMS["pig_crop"], monthly_only=True)),
    }
    weight_groups = {}
    for key, label in [
        ("market_under_50", "Under 50 lb"),
        ("market_50_119", "50-119 lb"),
        ("market_120_179", "120-179 lb"),
        ("market_180_over", "180 lb and over"),
    ]:
        dates, values = _nass_national(conn, NASS_ITEMS[key])
        weight_groups[label] = _series(dates, values)
    data["weight_groups"] = weight_groups
    return data


def build_slaughter_production(conn):
    # AMS LM_HG201 daily series (MPR covered packers, barrows & gilts, ~92% of head)
    daily_head = _ams_series(conn, "LM_HG201", "head_count_barrows_gilts")
    monthly_head = _monthly_aggregate(*daily_head, method="sum")
    daily_weight = _ams_series(conn, "LM_HG201", "avg_carcass_weight")
    monthly_weight = _monthly_aggregate(*daily_weight, method="avg")
    daily_prod = _estimated_daily_production(conn)
    estimated_prod = _monthly_aggregate(*daily_prod, method="sum")

    # NASS monthly Livestock Slaughter — true commercial (~99% of industry) coverage.
    # monthly_only avoids the annual rollup colliding with the December month.
    nass_commercial_head = _nass_national(conn, NASS_ITEMS["commercial_slaughter_head"], monthly_only=True)
    nass_fi_head = _nass_national(conn, NASS_ITEMS["fi_slaughter_head"], monthly_only=True)
    nass_barrows_gilts = _nass_national(conn, NASS_ITEMS["barrows_gilts_head"], monthly_only=True)
    nass_sows = _nass_national(conn, NASS_ITEMS["sows_slaughter_head"], monthly_only=True)
    nass_boars = _nass_national(conn, NASS_ITEMS["boars_slaughter_head"], monthly_only=True)
    nass_live_weight = _nass_national(conn, NASS_ITEMS["commercial_live_weight"], monthly_only=True)
    nass_dressed_weight = _nass_national(conn, NASS_ITEMS["barrows_gilts_dressed_weight"], monthly_only=True)
    nass_pork_production = _nass_national(conn, NASS_ITEMS["commercial_pork_production"], monthly_only=True)

    production_series = estimated_prod if estimated_prod[0] else nass_pork_production
    slaughter_series = monthly_head if monthly_head[0] else nass_commercial_head

    return {
        # AMS daily / high-frequency (covered packers)
        "daily_direct_hog_count": _series(*daily_head),
        "monthly_direct_hog_count": _series(*monthly_head),
        "daily_estimated_production": _series(*daily_prod),
        "estimated_pork_production_lb": _series(*estimated_prod),
        "avg_carcass_weight": _series(*daily_weight),
        "avg_carcass_weight_monthly": _series(*monthly_weight),
        # NASS monthly Livestock Slaughter (commercial, ~99% of industry)
        "nass_commercial_slaughter": _series(*nass_commercial_head),
        "nass_fi_slaughter": _series(*nass_fi_head),
        "nass_barrows_gilts": _series(*nass_barrows_gilts),
        "nass_sows": _series(*nass_sows),
        "nass_boars": _series(*nass_boars),
        "nass_live_weight": _series(*nass_live_weight),
        "nass_dressed_weight": _series(*nass_dressed_weight),
        "nass_pork_production": _series(*nass_pork_production),
        # Legacy keys retained for older front-end code and data consumers.
        "commercial_pork_production_lb": _series(*nass_pork_production),
        "commercial_slaughter_head": _series(*nass_commercial_head),
        "slaughter_head": _series(*slaughter_series),
        "slaughter_live_lb": _series(*nass_live_weight),
        "pork_production_lb": _series(*production_series),
    }


def build_prices(conn):
    base = _ams_series(conn, "LM_HG201", "base_price")
    net = _ams_series(conn, "LM_HG201", "net_price")
    cutout = _ams_series(conn, "LM_PK602", "cutout_value")
    cutout_net_spread = _subtract_series(cutout, net)
    cutout_base_spread = _subtract_series(cutout, base)

    primals = {}
    primal_spreads = {}
    for series_name, label in [
        ("loin_value", "Loin"),
        ("butt_value", "Butt"),
        ("picnic_value", "Picnic"),
        ("rib_value", "Rib"),
        ("ham_value", "Ham"),
        ("belly_value", "Belly"),
    ]:
        primal = _ams_series(conn, "LM_PK602", series_name)
        primals[label] = _series(*primal)
        spread = _subtract_series(primal, cutout)
        primal_spreads[f"{label} minus cutout"] = _series(*spread)

    return {
        "barrow_gilt_base_price": _series(*base),
        "barrow_gilt_net_price": _series(*net),
        "pork_cutout_value": _series(*cutout),
        "cutout_net_spread": _series(*cutout_net_spread),
        "cutout_base_spread": _series(*cutout_base_spread),
        "primals": primals,
        "primal_spreads": primal_spreads,
        "nass_price_received": _series(*_nass_national(conn, NASS_ITEMS["price_received"], monthly_only=True)),
    }


def build_retail_demand(conn):
    metric_rows = conn.execute(
        """
        SELECT report_date,
               SUM(COALESCE(stores, 0)) AS stores,
               AVG(feature_rate) AS feature_rate,
               AVG(activity_index) AS activity_index
        FROM retail_metrics
        GROUP BY report_date
        ORDER BY report_date
        """
    ).fetchall()
    dates = [row[0] for row in metric_rows]
    stores = [row[1] for row in metric_rows]
    feature = [row[2] for row in metric_rows]
    activity = [row[3] for row in metric_rows]

    price_rows = conn.execute(
        """
        SELECT report_date,
               SUM(COALESCE(price_avg, 0) * COALESCE(store_count, 1)) /
                 NULLIF(SUM(COALESCE(store_count, 1)), 0) AS weighted_price,
               SUM(COALESCE(store_count, 0)) AS stores
        FROM retail_prices
        WHERE price_avg IS NOT NULL
        GROUP BY report_date
        ORDER BY report_date
        """
    ).fetchall()
    price_dates = [row[0] for row in price_rows]
    price_values = [row[1] for row in price_rows]
    price_store_counts = [row[2] for row in price_rows]

    latest_price_date = price_dates[-1] if price_dates else None
    top_items = []
    if latest_price_date:
        top_rows = conn.execute(
            """
            SELECT COALESCE(section, 'Pork') AS section_label,
                   type,
                   price_avg,
                   store_count,
                   price_unit
            FROM retail_prices
            WHERE report_date = ?
              AND price_avg IS NOT NULL
            ORDER BY COALESCE(store_count, 0) DESC
            LIMIT 8
            """,
            (latest_price_date,),
        ).fetchall()
        top_items = [
            {
                "section": row[0],
                "type": row[1],
                "price_avg": row[2],
                "store_count": row[3],
                "price_unit": row[4],
            }
            for row in top_rows
        ]

    bacon = _fred_series(conn, "APU0000704111")
    return {
        "feature_rate": _series(dates, feature),
        "activity_index": _series(dates, activity),
        "store_count": _series(dates, stores),
        "featured_average_price": _series(price_dates, price_values),
        "featured_price_store_count": _series(price_dates, price_store_counts),
        "top_featured_items": top_items,
        "fred_bacon_price": _series(*bacon),
    }


def build_trade(conn):
    trade_rows = conn.execute(
        """
        SELECT report_month, flow, product, section_label, value
        FROM ers_trade_totals
        WHERE commodity = 'pork'
        ORDER BY report_month, flow, product
        """
    ).fetchall()
    trade_map = {}
    for report_month, flow, product, _section_label, value in trade_rows:
        trade_map.setdefault(report_month, {})[f"{flow}_{product}"] = value
    trade_dates = sorted(trade_map)

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
        latest_months = sorted({row[0] for row in partner_rows})[-12:]
        export_totals = defaultdict(float)
        import_totals = defaultdict(float)
        exp_map = defaultdict(dict)
        imp_map = defaultdict(dict)
        for report_month, flow, country, value in partner_rows:
            if flow == "export":
                if report_month in latest_months:
                    export_totals[country] += value or 0
                exp_map[report_month][country] = value
            elif flow == "import":
                if report_month in latest_months:
                    import_totals[country] += value or 0
                imp_map[report_month][country] = value
        top_exports = [name for _, name in sorted((v, k) for k, v in export_totals.items())[-6:]][::-1]
        top_imports = [name for _, name in sorted((v, k) for k, v in import_totals.items())[-6:]][::-1]
        exp_dates = sorted(exp_map)
        imp_dates = sorted(imp_map)
        export_series = {
            "dates": exp_dates,
            "series": {country: [exp_map[label].get(country) for label in exp_dates] for country in top_exports},
        }
        import_series = {
            "dates": imp_dates,
            "series": {country: [imp_map[label].get(country) for label in imp_dates] for country in top_imports},
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


def build_brazil_exports(conn, top_n=6):
    """Brazil fresh/frozen (in natura, HS 0203) pork exports from Comex Stat.

    Returns a monthly total volume line plus a top-destination breakdown, both in
    million lb (matching the US trade charts) and drawn from the same rows so the
    stacked destinations plus an "Other" remainder sum exactly to the total line.
    Top destinations are chosen by trailing-12-month volume, mirroring the US
    export-destination chart.
    """
    empty = {
        "unit": "million lb",
        "total": _series(),
        "by_destination": {"dates": [], "series": {}},
    }
    rows = conn.execute(
        """
        SELECT report_month, country, net_kg
        FROM comexstat_pork_exports
        WHERE flow = 'export'
          AND ncm_category = 'fresh_frozen'
          AND net_kg IS NOT NULL
        ORDER BY report_month
        """
    ).fetchall()
    if not rows:
        return empty

    total_by_month = defaultdict(float)
    country_by_month = defaultdict(lambda: defaultdict(float))
    last_12 = sorted({report_month for report_month, _, _ in rows})[-12:]
    dest_totals = defaultdict(float)
    for report_month, country, net_kg in rows:
        kg = net_kg or 0
        total_by_month[report_month] += kg
        country_by_month[report_month][country] += kg
        if report_month in last_12:
            dest_totals[country] += kg

    months = sorted(total_by_month)
    # kg -> million lb (kg * lb/kg / 1e6).
    total_values = [total_by_month[month] * KG_TO_LB / 1e6 for month in months]

    top_countries = [name for _, name in sorted(
        ((kg, country) for country, kg in dest_totals.items()), reverse=True
    )[:top_n]]
    series = {}
    for country in top_countries:
        label = BRAZIL_COUNTRY_EN.get(country, country)
        series[label] = [
            (country_by_month[month][country] * KG_TO_LB / 1e6) if country in country_by_month[month] else None
            for month in months
        ]

    return {
        "unit": "million lb",
        "total": _series(months, total_values),
        "by_destination": {"dates": months, "series": series},
    }


def build_inventory_trade(conn, slaughter_production):
    trade = build_trade(conn)
    cold_storage = {
        "total": _series(*_nass_national(conn, NASS_ITEMS["cold_storage_total"])),
        "bellies": _series(*_nass_national(conn, NASS_ITEMS["cold_storage_bellies"])),
        "hams": _series(*_nass_national(conn, NASS_ITEMS["cold_storage_hams"])),
        "loins": _series(*_nass_national(conn, NASS_ITEMS["cold_storage_loins"])),
    }
    export_series = (
        trade["trade_totals"]["dates"],
        [(value * 1000) if value is not None else None for value in trade["trade_totals"]["export_pork"]],
    )
    # Use NASS commercial pork production (carcass weight, ~99% of industry) as the
    # denominator so it is apples-to-apples with ERS carcass-weight exports, rather
    # than the AMS covered-packer estimate.
    production = (
        slaughter_production["nass_pork_production"]["dates"],
        slaughter_production["nass_pork_production"]["values"],
    )
    export_share = _divide_series(export_series, production, multiplier=100)
    return {
        "cold_storage": cold_storage,
        "trade": trade,
        "export_share_of_production": _series(*export_share),
        "brazil_exports": build_brazil_exports(conn),
    }


# Public CME-derived feed Google Sheet shared with the egg chartbook. Columns:
# corn date (0), corn cents/bushel (1), corn $/ton (3), soy date (5), soy $/ton (6).
FEED_SHEET_ID = "11x-7f68LiFCCItwY6qjgcWmgosPSY2sKXax1vorYDO4"


def _safe_sheet_float(value):
    value = (value or "").strip().replace(",", "")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_sheet_dt(value):
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _fetch_feed_sheet_daily():
    """Fetch daily corn & soybean-meal $/ton from the public CME feed Google
    Sheet. Returns (corn_by_date, soy_by_date) keyed by YYYY-MM-DD."""
    import csv
    import io
    from urllib.request import Request, urlopen

    url = f"https://docs.google.com/spreadsheets/d/{FEED_SHEET_ID}/export?format=csv&gid=0"
    try:
        req = Request(url, headers={"User-Agent": "porkchartbook/1.0"})
        with urlopen(req, timeout=60) as response:
            text = response.read().decode("utf-8", errors="replace").lstrip("﻿")
    except Exception as exc:  # noqa: BLE001 - network/CSV issues should degrade gracefully
        print(f"  [feed sheet] fetch failed, skipping corn/soy input indices: {exc}")
        return {}, {}

    corn_by_date = {}
    soy_by_date = {}
    for row in csv.reader(io.StringIO(text)):
        if not row:
            continue
        padded = row + [""] * max(0, 7 - len(row))
        corn_dt = _parse_sheet_dt(padded[0])
        if corn_dt:
            corn_ton = _safe_sheet_float(padded[3])
            if corn_ton is None:
                cents = _safe_sheet_float(padded[1])  # cents/bushel -> $/ton
                if cents is not None:
                    corn_ton = (cents / 100.0) * (2000.0 / 56.0)
            if corn_ton is not None:
                corn_by_date[corn_dt.date().isoformat()] = corn_ton
        soy_dt = _parse_sheet_dt(padded[5])
        if soy_dt:
            soy_ton = _safe_sheet_float(padded[6])
            if soy_ton is not None:
                soy_by_date[soy_dt.date().isoformat()] = soy_ton

    return corn_by_date, soy_by_date


def _fred_by_date(conn, series_id):
    """FRED series keyed by its native observation_date (YYYY-MM-DD)."""
    rows = conn.execute(
        """
        SELECT observation_date, value
        FROM fred_series
        WHERE series_id = ? AND value IS NOT NULL
        ORDER BY observation_date
        """,
        (series_id,),
    ).fetchall()
    return {d: v for d, v in rows if d}


def build_input_indices(conn, base_month="2025-01"):
    """Common pork input costs, each rebased to base_month = 100, on a shared
    daily date axis. Corn & soybean meal are daily (from the CME feed sheet);
    diesel is weekly and electricity monthly at their native FRED cadence.
    Mirrors the egg chartbook chart but with corn/soy split out, daily, and
    paperboard packaging removed."""
    corn_by_date, soy_by_date = _fetch_feed_sheet_daily()
    diesel_by_date = _fred_by_date(conn, "GASDESW")
    elec_by_date = _fred_by_date(conn, "APU000072610")

    def rebase(by_date):
        if not by_date:
            return {}
        base_value = next(
            (by_date[d] for d in sorted(by_date) if d >= base_month and by_date[d]),
            None,
        )
        if not base_value:
            base_value = by_date[sorted(by_date)[0]]
        if not base_value:
            return {}
        return {d: round(v / base_value * 100.0, 4) for d, v in by_date.items() if v is not None}

    series_maps = {
        "Corn": rebase(corn_by_date),
        "Soybean meal": rebase(soy_by_date),
        "Diesel": rebase(diesel_by_date),
        "Electricity": rebase(elec_by_date),
    }
    active = {label: values for label, values in series_maps.items() if values}
    if not active:
        return {"dates": [], "series": {}, "base_month": base_month}

    # Anchor the window to where feed (corn/soy) data begins so the comparison
    # lines start together rather than trailing years of diesel/electricity.
    feed_dates = set(corn_by_date) | set(soy_by_date)
    min_feed = min(feed_dates) if feed_dates else None
    dates = sorted({d for values in active.values() for d in values})
    if min_feed:
        dates = [d for d in dates if d >= min_feed]

    return {
        "dates": dates,
        "series": {label: [values.get(d) for d in dates] for label, values in active.items()},
        "base_month": base_month,
    }


def build_costs_risk(conn, prices):
    corn = _fred_series(conn, "PMAIZMTUSDM")
    soymeal = _fred_series(conn, "PSMEAUSDM")
    corn_map = dict(zip(*corn)) if corn[0] else {}
    soy_map = dict(zip(*soymeal)) if soymeal[0] else {}
    labels = sorted(set(corn_map) & set(soy_map))
    base_corn = next((corn_map[label] for label in labels if corn_map.get(label)), None)
    base_soy = next((soy_map[label] for label in labels if soy_map.get(label)), None)
    feed_values = []
    for label in labels:
        corn_value = corn_map.get(label)
        soy_value = soy_map.get(label)
        if corn_value is None or soy_value is None or not base_corn or not base_soy:
            feed_values.append(None)
        else:
            feed_values.append(((corn_value / base_corn) * 0.7 + (soy_value / base_soy) * 0.3) * 100)

    monthly_net = _monthly_aggregate(
        prices["barrow_gilt_net_price"]["dates"],
        prices["barrow_gilt_net_price"]["values"],
        method="avg",
    )
    monthly_cutout = _monthly_aggregate(
        prices["pork_cutout_value"]["dates"],
        prices["pork_cutout_value"]["values"],
        method="avg",
    )
    monthly_spread = _subtract_series(monthly_cutout, monthly_net)

    return {
        "corn_price": _series(*corn),
        "soybean_meal_price": _series(*soymeal),
        "feed_cost_index": _series(labels, feed_values),
        "input_indices": build_input_indices(conn),
        "monthly_cutout_net_spread": _series(*monthly_spread),
        "risk_watch": [
            {
                "topic": "Foreign animal disease",
                "note": "African swine fever remains a high-consequence supply-chain and trade risk; APHIS updates are the preferred public reference.",
                "source": "USDA APHIS",
                "url": "https://www.aphis.usda.gov/livestock-poultry-disease/swine/african-swine-fever",
            },
            {
                "topic": "Export concentration",
                "note": "Mexico, Japan, Canada, South Korea, China/Hong Kong and Colombia should stay visible because partner mix drives carcass value.",
                "source": "USDA ERS",
                "url": "https://www.ers.usda.gov/data-products/livestock-and-meat-international-trade-data/",
            },
            {
                "topic": "Retail pull-through",
                "note": "Feature activity and activity index help show whether cutout strength is meeting retail support.",
                "source": "USDA AMS",
                "url": "https://mymarketnews.ams.usda.gov/",
            },
            {
                "topic": "Official forecast revisions",
                "note": "ERS and WASDE revisions to pork production, price, and export forecasts should be tracked as a dedicated monthly module once the parser is added.",
                "source": "USDA ERS",
                "url": "https://www.ers.usda.gov/publications/pub-details/?pubid=37427",
            },
        ],
    }


def build_snapshot(herd, slaughter, prices, retail, inventory_trade):
    inventory = _latest(herd["total_inventory"]["dates"], herd["total_inventory"]["values"])
    prod = _latest(slaughter["pork_production_lb"]["dates"], slaughter["pork_production_lb"]["values"])
    net_price = _latest(prices["barrow_gilt_net_price"]["dates"], prices["barrow_gilt_net_price"]["values"])
    cutout = _latest(prices["pork_cutout_value"]["dates"], prices["pork_cutout_value"]["values"])
    spread = _latest(prices["cutout_net_spread"]["dates"], prices["cutout_net_spread"]["values"])
    export_share = _latest(
        inventory_trade["export_share_of_production"]["dates"],
        inventory_trade["export_share_of_production"]["values"],
    )
    feature = _latest(retail["feature_rate"]["dates"], retail["feature_rate"]["values"])

    cards = [
        {
            "label": "Hog Inventory",
            "value": inventory["value"],
            "date": inventory["date"],
            "format": "head",
            "unit": "head",
            "change": _pct_change_text(herd["total_inventory"]["dates"], herd["total_inventory"]["values"]),
        },
        {
            "label": "Pork Production",
            "value": prod["value"],
            "date": prod["date"],
            "format": "pounds",
            "unit": "estimated lb/mo",
            "change": _pct_change_text(slaughter["pork_production_lb"]["dates"], slaughter["pork_production_lb"]["values"]),
        },
        {
            "label": "Net Hog Price",
            "value": net_price["value"],
            "date": net_price["date"],
            "format": "currency",
            "unit": "$/cwt",
            "change": _pct_change_text(prices["barrow_gilt_net_price"]["dates"], prices["barrow_gilt_net_price"]["values"]),
        },
        {
            "label": "Pork Cutout",
            "value": cutout["value"],
            "date": cutout["date"],
            "format": "currency",
            "unit": "$/cwt",
            "change": _pct_change_text(prices["pork_cutout_value"]["dates"], prices["pork_cutout_value"]["values"]),
        },
        {
            "label": "Cutout-Net Spread",
            "value": spread["value"],
            "date": spread["date"],
            "format": "currency",
            "unit": "$/cwt",
            "change": _pct_change_text(prices["cutout_net_spread"]["dates"], prices["cutout_net_spread"]["values"]),
        },
        {
            "label": "Exports / Production",
            "value": export_share["value"],
            "date": export_share["date"],
            "format": "percent",
            "unit": "monthly share",
            "change": _pct_change_text(
                inventory_trade["export_share_of_production"]["dates"],
                inventory_trade["export_share_of_production"]["values"],
            ),
        },
    ]
    if feature["value"] is not None:
        cards.append({
            "label": "Retail Feature Rate",
            "value": feature["value"],
            "date": feature["date"],
            "format": "percent",
            "unit": "AMS retail",
            "change": _pct_change_text(retail["feature_rate"]["dates"], retail["feature_rate"]["values"]),
        })
    return cards


def build_insights(herd, slaughter, prices, retail, inventory_trade, costs):
    trade = inventory_trade["trade"]
    weight_insight_series = next(
        (
            item for item in herd["weight_groups"].values()
            if item["dates"] and item["values"]
        ),
        _series(),
    )
    return {
        "herdTotalChart": _summary("Hog inventory", herd["total_inventory"]["dates"], herd["total_inventory"]["values"], "million head", 1e6),
        "herdBreedingMarketChart": _summary("Breeding inventory", herd["breeding_inventory"]["dates"], herd["breeding_inventory"]["values"], "million head", 1e6),
        "marketWeightChart": _summary("Market-weight inventory", weight_insight_series["dates"], weight_insight_series["values"], "million head", 1e6),
        "farrowProductivityChart": _summary("Pigs per litter", herd["pigs_per_litter"]["dates"], herd["pigs_per_litter"]["values"], "pigs/litter"),
        "slaughterHeadChart": _summary("AMS direct hog count", slaughter["slaughter_head"]["dates"], slaughter["slaughter_head"]["values"], "million head", 1e6),
        "porkProductionChart": _summary("Estimated pork production", slaughter["pork_production_lb"]["dates"], slaughter["pork_production_lb"]["values"], "million lb", 1e6),
        "carcassWeightChart": _summary("Average carcass weight", slaughter["avg_carcass_weight_monthly"]["dates"], slaughter["avg_carcass_weight_monthly"]["values"], "lb"),
        "hogPriceChart": _summary("Net hog price", prices["barrow_gilt_net_price"]["dates"], prices["barrow_gilt_net_price"]["values"], "$/cwt"),
        "cutoutChart": _summary("Pork cutout", prices["pork_cutout_value"]["dates"], prices["pork_cutout_value"]["values"], "$/cwt"),
        "hogCutoutSpreadChart": _summary("Cutout less net hog price", prices["cutout_net_spread"]["dates"], prices["cutout_net_spread"]["values"], "$/cwt"),
        "primalsChart": _summary("Belly primal value", prices["primals"]["Belly"]["dates"], prices["primals"]["Belly"]["values"], "$/cwt"),
        "retailFeatureChart": _summary("Retail feature rate", retail["feature_rate"]["dates"], retail["feature_rate"]["values"], "%"),
        "retailPriceChart": _summary("Featured retail pork price", retail["featured_average_price"]["dates"], retail["featured_average_price"]["values"], "$/lb"),
        "coldStorageChart": _summary("Frozen pork stocks", inventory_trade["cold_storage"]["total"]["dates"], inventory_trade["cold_storage"]["total"]["values"], "million lb", 1e6, lower_is_good=True),
        "tradeFlowChart": _summary("Pork exports", trade["trade_totals"]["dates"], trade["trade_totals"]["export_pork"], "million lb", 1000),
        "exportShareChart": _summary("Export share of production", inventory_trade["export_share_of_production"]["dates"], inventory_trade["export_share_of_production"]["values"], "%"),
        "feedCostChart": _summary("Feed-cost proxy index", costs["feed_cost_index"]["dates"], costs["feed_cost_index"]["values"], "index", lower_is_good=True),
    }


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


def build_kpi(snapshot):
    """Legacy KPI object retained for compatibility."""
    lookup = {card["label"]: card for card in snapshot}
    return {
        "total_hog_inventory": {
            "date": lookup.get("Hog Inventory", {}).get("date"),
            "value": lookup.get("Hog Inventory", {}).get("value"),
        },
        "weekly_slaughter_head": {
            "date": lookup.get("Pork Production", {}).get("date"),
            "value": lookup.get("Pork Production", {}).get("value"),
        },
        "barrow_gilt_base_price": {
            "date": lookup.get("Net Hog Price", {}).get("date"),
            "value": lookup.get("Net Hog Price", {}).get("value"),
        },
        "pork_cutout_value": {
            "date": lookup.get("Pork Cutout", {}).get("date"),
            "value": lookup.get("Pork Cutout", {}).get("value"),
        },
        "ytd_export_volume_1000lb": {
            "year": date.today().year,
            "value": None,
        },
    }


def build_data_json(conn):
    herd = build_herd_supply(conn)
    slaughter = build_slaughter_production(conn)
    prices = build_prices(conn)
    retail = build_retail_demand(conn)
    inventory_trade = build_inventory_trade(conn, slaughter)
    costs = build_costs_risk(conn, prices)
    snapshot = build_snapshot(herd, slaughter, prices, retail, inventory_trade)

    data = {
        "snapshot": snapshot,
        "kpi": build_kpi(snapshot),
        "herd_supply": herd,
        "herd": herd,
        "slaughter_production": slaughter,
        "prices": prices,
        "retail_demand": retail,
        "inventory_trade": inventory_trade,
        "trade": inventory_trade["trade"],
        "costs_risk": costs,
        "insights": build_insights(herd, slaughter, prices, retail, inventory_trade, costs),
        "data_freshness": build_data_freshness(conn),
        "meta": {
            "updated": date.today().strftime("%B %d, %Y"),
            "source": "USDA NASS, USDA AMS, USDA ERS, FRED, Brazil MDIC/SECEX Comex Stat",
            "version": "pork-chartbook-v1-expanded",
            "monthly_updates": {
                "enabled": False,
                "note": "Signup UI is prepared; connect to the preferred CRM or form backend before launch.",
            },
        },
    }
    DOCS_ROOT.mkdir(parents=True, exist_ok=True)
    with open(DATA_JSON_PATH, "w") as handle:
        json.dump(data, handle, separators=(",", ":"))
    size_kb = DATA_JSON_PATH.stat().st_size / 1024
    print(f"  data.json written ({size_kb:.0f} KB) -> {DATA_JSON_PATH}")
    return data


def main():
    parser = argparse.ArgumentParser(description="Build the pork chartbook dashboard")
    parser.add_argument("--json-only", action="store_true", help="Only write docs/data.json")
    parser.add_argument("--db", default=None, help="Path to SQLite database file")
    args = parser.parse_args()

    conn = db.init_db(args.db)
    try:
        build_data_json(conn)
        if not args.json_only:
            index_path = DOCS_ROOT / "index.html"
            if index_path.exists():
                print(f"  index.html already exists at {index_path}")
            else:
                print(f"  WARNING: index.html not found at {index_path}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
