"""
parsers.py — Transform raw API JSON into normalized row dicts for SQLite.

NASS: 1 universal parser for all QuickStats records.
"""

from __future__ import annotations


def _safe_float(val):
    """Parse a string to float, returning None on failure."""
    if val is None or val == "":
        return None
    try:
        return float(str(val).replace(",", ""))
    except (ValueError, TypeError):
        return None


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
