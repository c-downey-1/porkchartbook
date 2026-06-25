# Data Requests — Pork Chartbook

Data needed from the local ingestion pipeline (colleague's machine) to finish the
chartbook review. The dashboard frontend reads `docs/data.json`; each item below
needs a new/extended field there, which means editing `src/porkchartbook/ingest.py`
and/or `src/porkchartbook/build_dashboard.py`, then regenerating + pushing
`docs/data.json`.

**Workflow reminder:** after pulling these code changes, run the pipeline so the new
fields land in `docs/data.json`. The frontend already has guarded placeholders /
charts that will populate automatically once the fields exist (missing data just
hides gracefully until then).

Status key: 🔴 not started · 🟡 in progress · 🟢 delivered

---

## Status update — 2026-06-24

| # | Item | Status | Notes |
|---|------|--------|-------|
| 1 | US exports, product weight | 🟢 | **US Census** trade API at HS10 (ERS no longer publishes a product-weight pork workbook). `CENSUS_API_KEY` set; backfilled 2015–2026. → `inventory_trade.us_trade_product_weight.export_fresh_frozen` (HS 0203, comparable to Brazil) + `export_total`. |
| 2 | Forecast production | 🟢 | WASDE machine-readable TXT → `forecasts.production`. |
| 3 | Forecasted exports | 🟢 | WASDE → `forecasts.exports`. |
| 4 | Forecasted price | 🟢 | WASDE hog price ("Barrows and gilts") → `forecasts.hog_price`. |
| 5 | Per-capita & disappearance | 🟢 | ERS Food Availability CSV (annual, 1909–2021) → `retail_demand.per_capita_disappearance`. |
| 6 | Retail vs foodservice | ⛔ | **Declined** — no pork-specific foodservice source without proprietary data (Circana etc.); the ERS Food Expenditure Series is all-food only. Placeholder stays hidden. |
| 7 | Demand vs chicken & beef | 🟢 | FRED chicken/ground-beef/pork-chops retail prices → `retail_demand.fred_{chicken,beef,pork_chops}_price`. |
| 8 | Top import cuts/products | 🟢 | **US Census** by HS10 → `inventory_trade.us_trade_product_weight.import_by_cut` (category view) + `import_top_products` (specific cuts: bellies, hams, bacon, offal…). |
| 9 | Brazil SK/Canada/Colombia | 🟢 | Force-included (all have data); palette extended to keep destinations distinct. |

---

## Round 2 — follow-up requests (2026-06-25)

### 10. Quarterly forecasts (production / exports / hog price)  🟢
- **Charts:** Forecast Production / Forecasted Exports / Forecasted Price.
- **Problem:** WASDE was delivered **annual only** — `forecasts.production/exports/hog_price`
  each have just `years` (2025–2027), so the charts show only 2–3 points.
- **Need:** Quarterly granularity. WASDE's balance-sheet tables include **quarterly**
  commercial pork production and **quarterly** hog prices ("Barrows & Gilts, National Base").
  Parse those into a quarterly series (e.g. `forecasts.production.quarters` + `quarter_values`)
  so all three charts can render quarterly.

### 11. Per-capita consumption for chicken & beef  🟢
- **Chart:** Demand vs. Chicken and Beef.
- **Problem:** We only have retail **prices** (FRED) for chicken/beef. To compare
  **consumption volume** (lb/person/yr) across proteins, we need per-capita availability
  for **beef and chicken**.
- **Source:** USDA ERS Food Availability — same source already used for pork per-capita.
  Expose e.g. `retail_demand.per_capita_by_meat.{pork,beef,chicken}`.

### 12. Exports as share of production — top exporters  🟢
- **Chart:** "Exports as Share of Production — Top Exporters" placeholder (Trade, after the US export-share chart).
- **Need:** Annual pork **exports** and **production** by country for the major exporters
  (US, EU, Brazil, China, Canada, Mexico…) so we can plot exports ÷ production per country.
- **Source:** USDA FAS **PSD** (Production, Supply & Distribution Online) — provides both
  production and exports by country on a consistent CWE basis; free API / bulk download.
  Annual only. Expose e.g. `world_psd.{country}.{production,exports}` or a precomputed
  `export_share_by_country`.

### 13. Farm-to-wholesale-to-retail price spread  🟢
- **Chart:** Farm-to-Wholesale-to-Retail Price Spread placeholder (Cost, Prices & Margins).
- **Problem:** We have the three price levels (hog net price & cutout in $/cwt carcass;
  retail in $/lb) but on **incompatible bases** — a true spread needs all three on a common
  retail-weight-equivalent $/lb, which requires yield conversion factors. Not safely
  buildable from our current data.
- **Source:** USDA ERS **Meat Price Spreads** — purpose-built: monthly farm value, wholesale
  value, retail value, AND the spreads for pork, standardized to a retail-weight basis
  (USDA factors: 1.869 lb hog / lb retail, 1.04 lb wholesale / lb retail), back to 1970.
  Expose e.g. `price_spreads.{farm_value,wholesale_value,retail_value}` (and optionally the
  precomputed spreads).

---

## 1. US pork exports in PRODUCT weight  🔴
- **Chart:** Pork Exports: US vs. Brazil (`tradeFlowChart`)
- **Problem:** US exports are currently ingested in **carcass weight** (ERS carcass-wt
  workbook); Brazil (Comex Stat) is **product weight**. The two lines aren't comparable,
  and the aggregate carcass-wt figure can't be accurately reverse-converted (ERS uses
  many per-cut factors).
- **Need:** Monthly US pork export volume in **product weight**.
- **Source:** USDA ERS — Livestock & Meat International Trade Data (ERS publishes both
  product-weight and carcass-weight editions; we only pull carcass weight today).
- **Action:** Ingest the product-weight pork export series and expose a new field
  (e.g. `inventory_trade.trade.export_pork_product_weight` or a sibling of the existing
  total) in `data.json`. Touch points: `ers_trade_pork_client.py`, `build_dashboard.py`.

## 2. Forecast Production  🔴
- **Chart:** Forecast Production placeholder (Supply section)
- **Need:** USDA forecast of US commercial pork production (quarterly/annual projections).
- **Source:** USDA WASDE (World Agricultural Supply & Demand Estimates) and/or ERS
  Livestock, Dairy, and Poultry Outlook. (The code already notes a WASDE/ERS forecast
  parser as a planned module.)

## 3. Forecasted Exports  🔴
- **Chart:** Forecasted Exports placeholder (Trade section)
- **Need:** USDA forecast of US pork exports.
- **Source:** USDA WASDE / ERS Outlook (same feed as #2).

## 4. Forecasted Price  🔴
- **Chart:** Forecasted Price placeholder (Cost, Prices & Margins section)
- **Need:** USDA forecast of hog / lean-hog prices.
- **Source:** USDA WASDE (hog price forecast) / ERS Outlook.

## 5. Per Capita Consumption & "Disappearance"  🔴
- **Chart:** Per Capita Consumption & Disappearance placeholder (Domestic Demand)
- **Need:** US per-capita pork consumption and total domestic disappearance
  (production + imports − exports − ending stocks).
- **Source:** USDA ERS Food Availability (Per Capita) Data System; WASDE domestic
  disappearance for the balance-sheet view.

## 6. Retail vs. Foodservice / Restaurant Demand  🔴
- **Chart:** Retail & Foodservice / Restaurant Demand placeholder (Domestic Demand)
- **Need:** Split of pork demand between at-home (retail/grocery) and away-from-home
  (foodservice/restaurant).
- **Source:** USDA ERS Food Expenditure Series (at-home vs away-from-home) as a proxy;
  a true pork-specific foodservice split may require an industry source (e.g. Circana) —
  **source uncertain / may be proprietary. Needs your colleague's input on availability.**

## 7. Demand vs. Chicken and Beef  🔴
- **Chart:** Demand vs. Chicken and Beef placeholder (Domestic Demand)
- **Need:** Retail prices (and/or per-capita consumption) for chicken and beef, to compare
  against pork.
- **Source:** FRED retail price series (BLS CPI average prices) for chicken and beef —
  same keyless FRED mechanism already used for bacon/feed. **Likely low effort.**

## 8. Top Import Cuts / Products  🔴
- **Chart:** Top Import Cuts / Products placeholder (Trade section, paired with Top Import Sources)
- **Need:** US pork imports broken down by **cut/product type** (current import data is by
  country only).
- **Source:** USDA ERS / U.S. Census trade data by HS product code for pork.

## 9. Brazil exports to South Korea, Canada, Colombia  🔴
- **Chart:** Brazil Top Export Destinations (`brazilDestinationsChart`)
- **Need:** Surface Brazil's pork exports to **South Korea, Canada, Colombia** (so the
  Brazil chart can show the same destinations the US chart does, for comparison).
- **Why missing:** `build_brazil_exports(top_n=6)` keeps only Brazil's top-6 destinations
  by volume (Philippines, Japan, Chile, China, Hong Kong, Mexico); these three fall below
  that. They may have little/no Brazil volume.
- **Action:** In `build_brazil_exports`, force-include South Korea/Canada/Colombia in
  addition to the top-6 (only emit if they have data). Add Portuguese→English mappings in
  `BRAZIL_COUNTRY_EN` if missing (`Coreia do Sul`✓, check `Canadá`→Canada, `Colômbia`→Colombia).
  Then regenerate. **Also note:** the palette `C.seq` has only 7 colours — if the Brazil
  chart ends up with >7 destinations, extend the palette so each country stays distinct.

---

## NOT data requests — buildable now from existing `data.json` (no colleague needed)
These placeholders already have their underlying data; the frontend can build them anytime:
- **Cost of Soybean Meal and Corn** — `costs_risk.corn_price` and `costs_risk.soybean_meal_price` already present. (Built.)
- **Monthly Key Insights** — editorial content, not data.
