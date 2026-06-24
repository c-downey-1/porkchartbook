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
    # source_state — one row per orchestrated source key, holding the most
    # recent freshness-probe fingerprint (NASS record count, ERS workbook
    # Last-Modified/ETag, etc.) so the daily run can decide whether a
    # long-term source actually published something new before re-ingesting.
    "source_state": """
        CREATE TABLE IF NOT EXISTS source_state (
            source_key       TEXT PRIMARY KEY,
            probe_value      TEXT,
            last_checked_at  TEXT DEFAULT (datetime('now')),
            last_changed_at  TEXT
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
    "retail_metrics": """
        CREATE TABLE IF NOT EXISTS retail_metrics (
            report_date         TEXT NOT NULL,
            slug_id             INTEGER NOT NULL,
            region              TEXT NOT NULL DEFAULT '',
            stores              INTEGER,
            last_week_stores    INTEGER,
            last_year_stores    INTEGER,
            feature_rate        REAL,
            last_week_feature   REAL,
            last_year_feature   REAL,
            activity_index      REAL,
            last_week_activity  REAL,
            last_year_activity  REAL,
            fetched_at          TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (report_date, slug_id, region)
        )
    """,
    "retail_prices": """
        CREATE TABLE IF NOT EXISTS retail_prices (
            report_date         TEXT NOT NULL,
            slug_id             INTEGER NOT NULL,
            region              TEXT NOT NULL DEFAULT '',
            commodity           TEXT,
            section             TEXT,
            type                TEXT NOT NULL DEFAULT '',
            condition           TEXT,
            environment         TEXT,
            package_size        TEXT,
            quality_grade       TEXT,
            price_avg           REAL,
            price_min           REAL,
            price_max           REAL,
            store_count         INTEGER,
            price_unit          TEXT,
            fetched_at          TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (report_date, slug_id, region, section, type, condition, package_size)
        )
    """,
    "fred_series": """
        CREATE TABLE IF NOT EXISTS fred_series (
            observation_date    TEXT NOT NULL,
            series_id           TEXT NOT NULL,
            value               REAL,
            series_label        TEXT,
            source_url          TEXT,
            fetched_at          TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (observation_date, series_id)
        )
    """,
    # Brazil pork exports — MDIC/SECEX Comex Stat, monthly, by NCM x destination.
    # Used as global supply/competition context: Brazil is the world's #4 pork
    # exporter. value_fob_usd is FOB USD, net_kg is net weight, stat_qty is the
    # NCM's statistical quantity. Country names are the Portuguese labels the
    # Comex Stat API returns; translate at the dashboard layer if needed.
    "comexstat_pork_exports": """
        CREATE TABLE IF NOT EXISTS comexstat_pork_exports (
            report_month       TEXT NOT NULL,
            flow               TEXT NOT NULL,
            ncm_code           TEXT NOT NULL,
            ncm_category       TEXT NOT NULL,
            ncm_desc           TEXT,
            country            TEXT NOT NULL,
            value_fob_usd      REAL,
            net_kg             REAL,
            stat_qty           REAL,
            source_url         TEXT,
            fetched_at         TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (report_month, flow, ncm_code, country)
        )
    """,
    # USDA WASDE pork forecasts — production & exports (million lb) and the
    # national hog price ("Barrows and gilts", $/cwt), by forecast vintage
    # (report_month) and marketing_year. Each monthly WASDE adds a vintage row,
    # so the table also captures how a marketing year's forecast is revised.
    "wasde_forecasts": """
        CREATE TABLE IF NOT EXISTS wasde_forecasts (
            report_month       TEXT NOT NULL,
            marketing_year     INTEGER NOT NULL,
            metric             TEXT NOT NULL,
            value              REAL,
            unit               TEXT,
            vintage_kind       TEXT,
            source_url         TEXT,
            fetched_at         TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (report_month, marketing_year, metric)
        )
    """,
    # US per-capita pork availability + supply-and-use (domestic disappearance),
    # USDA ERS Food Availability (Per Capita) Data System. Annual, tidy long
    # format: one row per (commodity, year, attribute). value may be NULL where
    # the source has no figure.
    "ers_food_availability": """
        CREATE TABLE IF NOT EXISTS ers_food_availability (
            commodity          TEXT NOT NULL,
            year               INTEGER NOT NULL,
            attribute          TEXT NOT NULL,
            value              REAL,
            source_url         TEXT,
            fetched_at         TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (commodity, year, attribute)
        )
    """,
    # US pork trade in PRODUCT weight by HS code — U.S. Census International
    # Trade API, monthly, all-country totals per HS6. net_kg is product weight
    # (kilograms; qty_unit records the reported unit). Used to (a) give a US
    # export total comparable to Brazil's product-weight Comex line and (b)
    # break US imports down by cut/product. hs_category mirrors
    # comexstat_pork_exports.ncm_category so the two sources align.
    "census_pork_trade": """
        CREATE TABLE IF NOT EXISTS census_pork_trade (
            report_month       TEXT NOT NULL,
            flow               TEXT NOT NULL,
            hs_code            TEXT NOT NULL,
            hs_category        TEXT NOT NULL,
            hs_desc            TEXT,
            value_usd          REAL,
            net_kg             REAL,
            qty_unit           TEXT,
            source_url         TEXT,
            fetched_at         TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (report_month, flow, hs_code)
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
    "CREATE INDEX IF NOT EXISTS idx_retail_metrics_date ON retail_metrics(report_date)",
    "CREATE INDEX IF NOT EXISTS idx_retail_prices_date ON retail_prices(report_date)",
    "CREATE INDEX IF NOT EXISTS idx_fred_series_id_date ON fred_series(series_id, observation_date)",
    "CREATE INDEX IF NOT EXISTS idx_comex_pork_month ON comexstat_pork_exports(report_month)",
    "CREATE INDEX IF NOT EXISTS idx_comex_pork_cat ON comexstat_pork_exports(ncm_category, report_month)",
    "CREATE INDEX IF NOT EXISTS idx_comex_pork_country ON comexstat_pork_exports(country, report_month)",
    "CREATE INDEX IF NOT EXISTS idx_wasde_metric ON wasde_forecasts(metric, marketing_year, report_month)",
    "CREATE INDEX IF NOT EXISTS idx_ers_food_avail ON ers_food_availability(commodity, year)",
    "CREATE INDEX IF NOT EXISTS idx_census_pork_month ON census_pork_trade(report_month)",
    "CREATE INDEX IF NOT EXISTS idx_census_pork_flow_cat ON census_pork_trade(flow, hs_category, report_month)",
    "CREATE INDEX IF NOT EXISTS idx_etl_log_source ON etl_log(source, slug_id, data_item)",
]


def create_all(conn):
    cur = conn.cursor()
    for ddl in TABLES.values():
        cur.execute(ddl)
    for ddl in INDEXES:
        cur.execute(ddl)
    conn.commit()
