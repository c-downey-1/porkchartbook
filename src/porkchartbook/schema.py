"""
schema.py — SQLite schema for the pork industry chartbook.
"""

TABLES = {
    "etl_log": """
        CREATE TABLE IF NOT EXISTS etl_log (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            source        TEXT NOT NULL,
            slug_id       INTEGER,
            data_item     TEXT,
            fetch_start   TEXT NOT NULL,
            fetch_end     TEXT NOT NULL,
            rows_fetched  INTEGER DEFAULT 0,
            fetched_at    TEXT DEFAULT (datetime('now')),
            status        TEXT DEFAULT 'ok'
        )
    """,
    "nass_data": """
        CREATE TABLE IF NOT EXISTS nass_data (
            year               INTEGER NOT NULL,
            reference_period   TEXT NOT NULL,
            freq               TEXT NOT NULL,
            commodity          TEXT NOT NULL,
            class              TEXT,
            data_item          TEXT NOT NULL,
            stat_category      TEXT,
            unit               TEXT,
            value              REAL,
            value_raw          TEXT,
            agg_level          TEXT NOT NULL,
            state_alpha        TEXT NOT NULL DEFAULT '',
            state_name         TEXT,
            cv_pct             REAL,
            load_time          TEXT,
            PRIMARY KEY (year, reference_period, data_item, agg_level, state_alpha)
        )
    """,
    "ams_hog_prices": """
        CREATE TABLE IF NOT EXISTS ams_hog_prices (
            report_date        TEXT NOT NULL,
            report_name        TEXT NOT NULL,
            series_name        TEXT NOT NULL,
            value              REAL,
            unit               TEXT,
            source_url         TEXT,
            fetched_at         TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (report_date, report_name, series_name)
        )
    """,
    "ers_trade_totals": """
        CREATE TABLE IF NOT EXISTS ers_trade_totals (
            report_month       TEXT NOT NULL,
            commodity          TEXT NOT NULL,
            flow               TEXT NOT NULL,
            product            TEXT NOT NULL,
            section_label      TEXT NOT NULL,
            value              REAL,
            unit               TEXT NOT NULL,
            source_url         TEXT,
            fetched_at         TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (report_month, commodity, flow, product)
        )
    """,
    "ers_trade_partner_country": """
        CREATE TABLE IF NOT EXISTS ers_trade_partner_country (
            report_month       TEXT NOT NULL,
            commodity          TEXT NOT NULL,
            flow               TEXT NOT NULL,
            product            TEXT NOT NULL,
            country            TEXT NOT NULL,
            value              REAL,
            unit               TEXT NOT NULL,
            source_url         TEXT,
            fetched_at         TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (report_month, commodity, flow, product, country)
        )
    """,
}

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_nass_item ON nass_data(data_item)",
    "CREATE INDEX IF NOT EXISTS idx_nass_year ON nass_data(year)",
    "CREATE INDEX IF NOT EXISTS idx_ams_hog_prices_date ON ams_hog_prices(report_date)",
    "CREATE INDEX IF NOT EXISTS idx_ams_hog_prices_series ON ams_hog_prices(series_name, report_date)",
    "CREATE INDEX IF NOT EXISTS idx_ers_trade_month ON ers_trade_totals(report_month)",
    "CREATE INDEX IF NOT EXISTS idx_ers_trade_partner_month ON ers_trade_partner_country(report_month)",
    "CREATE INDEX IF NOT EXISTS idx_etl_log_source ON etl_log(source, slug_id, data_item)",
]


def create_all(conn):
    cur = conn.cursor()
    for ddl in TABLES.values():
        cur.execute(ddl)
    for ddl in INDEXES:
        cur.execute(ddl)
    conn.commit()
