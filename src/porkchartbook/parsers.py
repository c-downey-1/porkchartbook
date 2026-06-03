"""
parsers.py — Transform raw API JSON into normalized row dicts for SQLite.

NASS: 1 universal parser for all QuickStats records.
"""

from __future__ import annotations

from datetime import datetime


def normalize_date(date_str):
    """Convert common source dates to YYYY-MM-DD."""
    if not date_str:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(date_str), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return str(date_str)


def _safe_float(val):
    """Parse a string to float, returning None on failure."""
    if val is None or val == "":
        return None
    try:
        return float(str(val).replace(",", ""))
    except (ValueError, TypeError):
        return None


def _safe_int(val):
    """Parse a string to int, returning None on failure."""
    parsed = _safe_float(val)
    return int(parsed) if parsed is not None else None


def _get(record, key, default=None):
    """Get a non-empty record value, normalizing common missing markers."""
    value = record.get(key, default)
    if value in (None, "", "N/A"):
        return default
    return value


def parse_nass_record(record):
    """Normalize a single NASS QuickStats record → dict for nass_data table.

    Handles withheld values: (D)=withheld, (Z)=less than half unit, etc.
    """
    value_raw = record.get("Value", "")
    value = None
    if value_raw and value_raw not in ("(D)", "(Z)", "(NA)", "(S)", "(H)", "(L)"):
        try:
            value = float(str(value_raw).replace(",", ""))
        except (ValueError, TypeError):
            pass

    cv_raw = record.get("CV (%)", "")
    cv_pct = None
    if cv_raw and cv_raw not in ("(D)", "(H)", "(L)", ""):
        try:
            cv_pct = float(str(cv_raw).replace(",", ""))
        except (ValueError, TypeError):
            pass

    return {
        "year": int(record.get("year", 0)),
        "reference_period": record.get("reference_period_desc", ""),
        "freq": record.get("freq_desc", ""),
        "commodity": record.get("commodity_desc", ""),
        "class": record.get("class_desc"),
        "data_item": record.get("short_desc", ""),
        "stat_category": record.get("statisticcat_desc"),
        "unit": record.get("unit_desc"),
        "value": value,
        "value_raw": value_raw,
        "agg_level": record.get("agg_level_desc", ""),
        "state_alpha": record.get("state_alpha", "") if record.get("agg_level_desc") == "STATE" else "",
        "state_name": record.get("state_name") if record.get("agg_level_desc") == "STATE" else None,
        "cv_pct": cv_pct,
        "load_time": record.get("load_time"),
    }


def parse_retail_metrics(slug_id, sections):
    """Parse AMS MARS retail feature metrics."""
    rows = []
    for section in sections:
        if section.get("reportSection") != "Report Metrics":
            continue
        for record in section.get("results", []):
            report_date = normalize_date(
                record.get("report_Date")
                or record.get("report_date")
                or record.get("report_begin_date")
            )
            if not report_date:
                continue
            rows.append({
                "report_date": report_date,
                "slug_id": slug_id,
                "region": _get(record, "region", ""),
                "stores": _safe_int(record.get("stores")),
                "last_week_stores": _safe_int(record.get("last_Week_Stores")),
                "last_year_stores": _safe_int(record.get("last_Year_Stores")),
                "feature_rate": _safe_float(record.get("feature")),
                "last_week_feature": _safe_float(record.get("last_Week_Feature")),
                "last_year_feature": _safe_float(record.get("last_Year_Feature")),
                "activity_index": _safe_float(record.get("activity_Index")),
                "last_week_activity": _safe_float(record.get("last_Week_Activity_Index")),
                "last_year_activity": _safe_float(record.get("last_Year_Activity_Index")),
            })
    return rows


def parse_retail_prices(slug_id, sections):
    """Parse AMS MARS retail pork feature price details."""
    rows = []
    for section in sections:
        if section.get("reportSection") != "Report Details":
            continue
        for record in section.get("results", []):
            report_date = normalize_date(record.get("report_date") or record.get("report_begin_date"))
            typ = _get(record, "type")
            if not report_date or not typ:
                continue
            rows.append({
                "report_date": report_date,
                "slug_id": slug_id,
                "region": _get(record, "region", ""),
                "commodity": _get(record, "commodity"),
                "section": _get(record, "section"),
                "type": typ,
                "condition": _get(record, "condition"),
                "environment": _get(record, "environment", ""),
                "package_size": _get(record, "package_size", ""),
                "quality_grade": _get(record, "quality_grade"),
                "price_avg": _safe_float(record.get("price_avg")),
                "price_min": _safe_float(record.get("price_min")),
                "price_max": _safe_float(record.get("price_max")),
                "store_count": _safe_int(record.get("store_count")),
                "price_unit": _get(record, "price_unit"),
            })
    return rows
