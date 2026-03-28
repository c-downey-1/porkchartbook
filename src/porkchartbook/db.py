"""
db.py — SQLite helpers for the pork chartbook.
"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from .paths import DEFAULT_DB_PATH
from .schema import create_all

DEFAULT_DB = DEFAULT_DB_PATH


def init_db(db_path=None):
    path = db_path or DEFAULT_DB
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    create_all(conn)
    return conn


def upsert_rows(conn, table, rows):
    if not rows:
        return 0
    cols = list(rows[0].keys())
    placeholders = ", ".join("?" for _ in cols)
    col_names = ", ".join(cols)
    sql = f"INSERT OR REPLACE INTO {table} ({col_names}) VALUES ({placeholders})"
    cur = conn.cursor()
    cur.executemany(sql, [tuple(r.get(c) for c in cols) for r in rows])
    conn.commit()
    return len(rows)


def insert_or_ignore_rows(conn, table, rows):
    if not rows:
        return 0
    cols = list(rows[0].keys())
    placeholders = ", ".join("?" for _ in cols)
    col_names = ", ".join(cols)
    sql = f"INSERT OR IGNORE INTO {table} ({col_names}) VALUES ({placeholders})"
    before = conn.total_changes
    cur = conn.cursor()
    cur.executemany(sql, [tuple(r.get(c) for c in cols) for r in rows])
    conn.commit()
    return conn.total_changes - before


def log_fetch(conn, source, fetch_start, fetch_end, rows_fetched, slug_id=None, data_item=None, status="ok"):
    conn.execute(
        """INSERT INTO etl_log (
               source, slug_id, data_item, fetch_start, fetch_end, rows_fetched, status
           ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (source, slug_id, data_item, str(fetch_start), str(fetch_end), rows_fetched, status),
    )
    conn.commit()


def get_last_fetched(conn, source, slug_id=None, data_item=None):
    if slug_id is not None:
        row = conn.execute(
            "SELECT MAX(fetch_end) FROM etl_log WHERE source=? AND slug_id=? AND status='ok'",
            (source, slug_id),
        ).fetchone()
    elif data_item is not None:
        row = conn.execute(
            "SELECT MAX(fetch_end) FROM etl_log WHERE source=? AND data_item=? AND status='ok'",
            (source, data_item),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT MAX(fetch_end) FROM etl_log WHERE source=? AND status='ok'",
            (source,),
        ).fetchone()
    return row[0] if row and row[0] else None


def export_csv(conn, query, output_path):
    cur = conn.execute(query)
    cols = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(cols)
        writer.writerows(rows)
    return len(rows)


def get_status(conn):
    results = []
    table_specs = [
        ("ams_hog_prices", "series_name", "report_date", None),
        ("ers_trade_totals", "section_label", "report_month", "commodity = 'pork'"),
        ("ers_trade_partner_country", "flow", "report_month", "commodity = 'pork'"),
    ]

    for table, group_col, date_expr, where_clause in table_specs:
        try:
            where_sql = f" WHERE {where_clause}" if where_clause else ""
            if group_col:
                rows = conn.execute(
                    f"SELECT {group_col}, COUNT(*), MIN({date_expr}), MAX({date_expr}) "
                    f"FROM {table}{where_sql} GROUP BY {group_col} ORDER BY {group_col}"
                ).fetchall()
                for row in rows:
                    results.append({
                        "table": table,
                        "group": row[0],
                        "rows": row[1],
                        "min_date": row[2],
                        "max_date": row[3],
                    })
            else:
                row = conn.execute(
                    f"SELECT COUNT(*), MIN({date_expr}), MAX({date_expr}) FROM {table}{where_sql}"
                ).fetchone()
                if row and row[0] > 0:
                    results.append({
                        "table": table,
                        "group": None,
                        "rows": row[0],
                        "min_date": row[1],
                        "max_date": row[2],
                    })
        except sqlite3.OperationalError:
            pass

    try:
        rows = conn.execute(
            """
            SELECT data_item, COUNT(*), MIN(year), MAX(year)
            FROM nass_data
            WHERE agg_level = 'NATIONAL'
              AND UPPER(commodity) LIKE '%HOG%'
            GROUP BY data_item
            ORDER BY data_item
            """
        ).fetchall()
        for row in rows:
            results.append({
                "table": "nass_data",
                "group": row[0],
                "rows": row[1],
                "min_date": str(row[2]),
                "max_date": str(row[3]),
            })
    except sqlite3.OperationalError:
        pass

    return results
