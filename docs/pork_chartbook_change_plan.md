# Pork Chartbook Change Plan

Prepared: 2026-05-20

## Implementation Status

Implemented in the v1 build-out on 2026-05-20. The dashboard now includes the expanded executive snapshot, herd and forward supply, slaughter and production, prices/cutout/margin, retail demand, inventories and trade, costs/risk, and monthly update signup sections. New data feeds were added for AMS retail pork feature activity, FRED feed and retail proxies, and additional NASS farrowings, productivity, weight-group, and cold-storage series.

The remaining backlog is now narrower: add official forecast-revision tracking, find a reliable public source for the two NASS market-weight groups that QuickStats did not return under the expected labels, connect the signup form to the preferred backend, and decide whether to add richer state concentration or plant-capacity modules.

## Purpose

This memo reviews the existing Egg Executive Chartbook, the current Pork Chartbook mockup, and the public data landscape for pork. It began as the planning document for the broader dashboard edits and now also records what was implemented in the v1 build-out.

The core recommendation is to move the pork chartbook from a compact set of available USDA charts toward a monthly executive readout of the pork system: herd and forward supply, slaughter and weights, hog pricing and cutout value, primal-level demand signals, retail and export clearing, inventories, costs, forecasts, and disease or trade risk.

## Local Materials Reviewed

- Egg chartbook reference and dashboard:
  - `/Users/casey/Documents/Workspace/IAA_Code_Projects/eggdashboard/chartbook_figure_reference.md`
  - `/Users/casey/Documents/Workspace/IAA_Code_Projects/eggdashboard/index.html`
  - `/Users/casey/Documents/Workspace/IAA_Code_Projects/eggdashboard/build.py`
- Broiler planning pattern for comparison:
  - `/Users/casey/Documents/Workspace/IAA_Code_Projects/broilerchartbook/docs/broiler_chartbook_change_plan.md`
  - `/Users/casey/Documents/Workspace/IAA_Code_Projects/broilerchartbook/docs/roadmap.md`
- Current pork chartbook:
  - `/Users/casey/Documents/Workspace/IAA_Code_Projects/porkchartbook/docs/index.html`
  - `/Users/casey/Documents/Workspace/IAA_Code_Projects/porkchartbook/docs/assets/pork-dashboard.js`
  - `/Users/casey/Documents/Workspace/IAA_Code_Projects/porkchartbook/docs/assets/split-dashboard.css`
  - `/Users/casey/Documents/Workspace/IAA_Code_Projects/porkchartbook/src/porkchartbook/ingest.py`
  - `/Users/casey/Documents/Workspace/IAA_Code_Projects/porkchartbook/src/porkchartbook/build_dashboard.py`
  - `/Users/casey/Documents/Workspace/IAA_Code_Projects/porkchartbook/docs/data.json`

## What The Egg Chartbook Does Well

The egg chartbook works because it follows the operating logic of the industry. It is not just a USDA data dump. It is a structured executive product with a recognizable visual system, direct source attribution, and charts that map to the questions executives ask repeatedly.

Patterns to preserve for pork:

- A clear executive entry point with KPIs before detailed charts.
- Sections organized around the production system, not just source agencies.
- Simple card-level source labels and a restrained Innovate Animal Ag design language.
- A mix of long-run context, seasonal overlays, and current-year emphasis.
- A monthly updates loop so the chartbook feels like a recurring executive product.

The main weakness to avoid copying is over-reliance on charts without enough "so what." Pork executives will need fast interpretation: latest value, YoY change, recent trend, and whether the metric is tight, loose, hot, or normal versus recent history.

## Current Pork Mockup Critique

The current pork chartbook is a useful start. It already has a design system aligned with the newer split-dashboard style: IAA header, left sidebar, warm paper background, unframed chart cards, range controls, Chart.js, and direct source links. It also has the right first-order source families: USDA NASS, USDA AMS, and USDA ERS.

The current content, however, is too thin for an executive pork product.

1. The current sections feel source-led rather than decision-led.
   The live structure is Market Snapshot, Herd, Slaughter & Production, Prices, and Trade. Those are all necessary, but the story needs to become: forward supply, realized output, value capture, demand clearing, inventories, costs, forecasts, and risk.

2. Slaughter and production are not actually populated.
   In `docs/data.json`, `slaughter_production.slaughter_head`, `slaughter_live_lb`, and `pork_production_lb` have zero dates. The database has annual NASS rows for hog slaughter and pork production, while the dashboard expects monthly or weekly chart series. This should be fixed before any production launch.

3. Herd coverage is missing the most useful forward-supply details.
   Total, breeding, market inventory, and pig crop are useful. But pork executives will also care about sows farrowing, farrowing intentions, pigs per litter, market hog weight groups, breeding herd productivity, and state concentration.

4. The price section is the current strength but needs more interpretation.
   AMS hog base/net prices, cutout, and primals are live and rich. The chartbook should add hog-cutout spread, primal contribution to cutout change, belly/ham/loin seasonal behavior, and a margin proxy rather than showing only raw price lines.

5. Trade should be reframed around current exposure.
   The current partner-country logic selects all-time top destinations and sources. For executives, the better default is top destinations by trailing 12 months or current YTD, with YoY change and share of production. Pork exports are large enough that this belongs high in the product.

6. Retail and domestic demand are missing.
   The egg chartbook includes retail feature activity and retail price context. Pork has public analogs through AMS retail pork feature activity and ERS/BLS retail price series. These should be added to show consumer-facing demand and price transmission.

7. Cold storage is missing.
   Pork freezer stocks are a core clearing signal, especially for bellies, hams, ribs, loins, and total pork. This should be one of the first second-wave additions.

8. Costs and profitability are missing.
   Pork executives will want feed pressure and margin context. Public data can support a conservative hog-corn/feed proxy, annual ERS commodity cost-and-return context, and possibly an Iowa State estimated returns view if we accept a non-USDA public university source.

9. Forecast revisions are missing.
   ERS Livestock, Dairy, and Poultry Outlook and WASDE updates can show whether official production, price, and export expectations are moving up or down. That is valuable monthly context.

10. Risk is too absent.
    The pork risk module should not mimic egg HPAI charts. For pork, risk should be ASF/foreign animal disease preparedness, trade policy/exposure, regulatory constraints, and possibly plant-capacity or labor disruptions where public data exist.

11. Data freshness needs attention.
    The local dashboard was last built March 28, 2026. Local AMS data run through March 27, 2026, while the current date is May 20, 2026. ERS pork trade public downloads were updated May 6, 2026 when checked, but local trade data only run through January 2026. The v1 release should refresh sources and expose latest data dates in a quiet footer/detail area.

## Executive Data Priorities

### Tier 1: Must-Have Monthly Product

| Theme | Public source | Why executives care | Preferred presentation |
|---|---|---|---|
| Total, breeding, and market hog inventory | [USDA NASS Hogs and Pigs](https://www.nass.usda.gov/Surveys/Guide_to_NASS_Surveys/Hog_Inventory/) / Quick Stats | Sets medium-term supply and shows expansion or contraction | Quarterly line with YoY, 5-year percentile band, and current-cycle callout |
| Market hog weight groups | USDA NASS Hogs and Pigs / Quick Stats | Indicates the timing of slaughter-ready supplies over the next few months | Stacked or grouped bars for under 50, 50-119, 120-179, and 180+ lb groups; YoY by bucket |
| Farrowings, farrowing intentions, pigs per litter, pig crop | USDA NASS Hogs and Pigs / Quick Stats | Best public read on biological productivity and forward hog supply | Supply bridge: breeding herd -> farrowings -> pigs per litter -> pig crop -> slaughter window |
| Weekly and monthly hog slaughter | [USDA NASS Livestock Slaughter](https://www.nass.usda.gov/Surveys/Guide_to_NASS_Surveys/Livestock_Slaughter/) and AMS FI slaughter reports | Actual supply hitting plants; day-count effects matter | Weekly FI line plus monthly commercial bars; weekday-adjusted YoY where possible |
| Pork production and average weights | USDA NASS Livestock Slaughter, AMS reports | Converts head count into pounds and reveals weight-driven supply changes | Head slaughter, pork pounds, average live/dressed weight, and contribution of head vs weight |
| Hog prices and procurement value | [USDA AMS MPR Datamart](https://mpr.datamart.ams.usda.gov/), LM_HG201 and related swine reports | Core producer revenue and packer input cost | Base/net price with volume/liquidity context; 5-day and 4-week averages |
| Pork cutout and primals | AMS LM_PK602 / pork FOB plant reports | Shows wholesale value and which cuts are driving the carcass | Cutout line, primal small multiples, and contribution-to-change waterfall |
| Primal spreads | Derived from AMS cutout/primal values | Belly, ham, loin, rib, butt, and picnic cycles matter more than a single cutout value | Spread dashboard with percentile bands and seasonality |
| Cold storage | [USDA NASS Cold Storage](https://www.nass.usda.gov/Surveys/Guide_to_NASS_Surveys/Cold_Storage/) / Quick Stats | Inventory overhang or tightness explains price action and holiday positioning | Total pork plus bellies, hams, ribs, loins; month-end stocks, YoY, and 5-year range |
| Retail feature activity | [AMS Weekly Retail Pork Feature Activity](https://mymarketnews.ams.usda.gov/viewReport/2868) | Near-real-time read on grocery promotion, consumer demand, and featured cuts | Feature rate, activity index, and featured-cut mix by section |
| Retail prices and price spreads | [ERS Meat Price Spreads](https://www.ers.usda.gov/data-products/meat-price-spreads/) and BLS/FRED retail series | Consumer affordability and farm-to-retail transmission | Pork retail value, bacon/chop/ham retail prices, wholesale-retail spread |
| Domestic supply and disappearance | [ERS Livestock and Meat Domestic Data](https://www.ers.usda.gov/data-products/livestock-and-meat-domestic-data/) | Clears the bridge between production, stocks, trade, and domestic use | Monthly/quarterly supply-use panel with disappearance per capita where available |
| Exports and imports by partner | [ERS Livestock and Meat International Trade Data](https://www.ers.usda.gov/data-products/livestock-and-meat-international-trade-data/) | Exports are a major pork demand outlet and destination mix matters | Trailing 12-month top destinations, YTD YoY, share of production, Mexico/Japan/Korea/China focus |
| Feed and cost pressure | ERS commodity costs and returns, NASS/FRED/CME commodity proxies, Iowa State estimated livestock returns | Feed is the largest cost exposure and margin cycles drive production decisions | Transparent feed index and hog-feed margin proxy; annual cost context as secondary |
| Forecast revisions | ERS Livestock, Dairy, and Poultry Outlook / WASDE | Captures changing official expectations for production, prices, exports, and imports | Month-to-month revision bars and latest forecast table |
| Disease and trade risk | [USDA APHIS African Swine Fever](https://direct.aphis.usda.gov/livestock-poultry-disease/swine/african-swine-fever), APHIS surveillance resources, ERS/FAS trade context | ASF, trade access, and policy disruptions can dominate economics quickly | Risk status panel and trade exposure chart; avoid false precision where public data are qualitative |

### Tier 2: Strong Second-Wave Additions

| Theme | Public source | Why it matters | Recommended treatment |
|---|---|---|---|
| Sow and boar slaughter | AMS/NASS slaughter detail where available | Early herd liquidation or expansion signal | Sow slaughter YoY and sow share of total slaughter |
| Hog-corn ratio or feed-price ratio | NASS Agricultural Prices, FRED, CME proxies | Simple profitability pressure indicator | Ratio line with long-run bands |
| Retail cut-level ad mix | AMS retail pork feature report | Shows what is being pushed to consumers by cut | Stacked share of ad activity by ham, loin, belly, rib, shoulder, ground, processed |
| Plant capacity / slaughter-day effect | NASS/AMS slaughter calendars and weekly FI data | Prevents misleading month-length interpretation | Day-adjusted slaughter and production deltas |
| Export concentration and policy exposure | ERS trade data plus public tariff/policy notes | Destination risk can change demand quickly | Top market share, Herfindahl-like concentration, market notes |
| Cross-protein price context | ERS Meat Price Spreads, BLS/FRED | Pork demand competes with beef and chicken | Relative retail price index for pork vs beef/chicken |
| State and regional footprint | NASS Hogs and Pigs, Census of Agriculture | Strategic context for where supply is concentrated | Annual/state map or lower-page reference section |
| Quarterly pasture-raised or niche pork | AMS retail/direct-to-consumer reports | Useful for a niche view, not core executive flow | Backlog or separate specialty section only |

### Lower Priority Or Not Recommended

- Do not port egg-specific HPAI, cage-free, pullet, molt, breaker, or layer-turnover concepts.
- Do not make annual state maps a top-of-page feature. They are context, not monthly signal.
- Do not show every AMS pork report by default. Curate the basket executives actually watch.
- Do not publish empty chart cards. Hide them or mark as "coming soon" only if the page explains the roadmap.
- Do not rely on qualitative disease or policy notes as if they were a numerical index unless the scoring method is transparent and auditable.

## Public Source Notes

The following public sources look most important for pork:

- [USDA NASS Hogs and Pigs](https://www.nass.usda.gov/Surveys/Guide_to_NASS_Surveys/Hog_Inventory/) - quarterly inventory, breeding herd, market hogs, and forward supply data. NASS notes the report covers the 16 largest hog states, accounting for nearly 95 percent of U.S. inventory, plus U.S. totals.
- [USDA NASS Livestock Slaughter](https://www.nass.usda.gov/Surveys/Guide_to_NASS_Surveys/Livestock_Slaughter/) - monthly commercial slaughter, pork production, live and dressed weights, and related slaughter data. NASS says preliminary weekly totals are published online by AMS, while monthly and annual totals are published by NASS.
- [USDA NASS Cold Storage](https://www.nass.usda.gov/Surveys/Guide_to_NASS_Surveys/Cold_Storage/) - month-end stocks in commercial and public warehouses, including pork and major pork items.
- [USDA NASS Quick Stats](https://www.nass.usda.gov/Quick_Stats/) - API and bulk backbone for NASS survey series.
- [USDA AMS MPR Datamart](https://mpr.datamart.ams.usda.gov/) - historical mandatory livestock reporting data after April 1, 2001, including hog and pork reports.
- [USDA AMS Swine Reports](https://www.ams.usda.gov/market-news/swine-reports) - current swine summary reports, national daily hog and pork summary, actual slaughter under FI, and direct swine reports.
- [USDA AMS Pork Carcass Cutout guide](https://www.ams.usda.gov/publications/content/lmr-pork-carcass-cutout) - useful methodology source for explaining cutout value as the sum-of-parts wholesale demand signal.
- [AMS Weekly Retail Pork Feature Activity](https://mymarketnews.ams.usda.gov/viewReport/2868) - weekly retail ad feature rate, activity index, and featured pork item prices.
- [ERS Livestock and Meat International Trade Data](https://www.ers.usda.gov/data-products/livestock-and-meat-international-trade-data/) - monthly and annual pork and live hog trade by partner country, with history back to 1989; updated May 6, 2026 when checked.
- [ERS Livestock and Meat Domestic Data](https://www.ers.usda.gov/data-products/livestock-and-meat-domestic-data/) - monthly meat statistics, supply/disappearance, and livestock prices; updated April 28, 2026 when checked.
- [ERS Meat Price Spreads](https://www.ers.usda.gov/data-products/meat-price-spreads/) - farm, wholesale, retail, and retail-cut price series for pork; updated May 12, 2026 when checked.
- [ERS Commodity Costs and Returns](https://www.ers.usda.gov/data-products/commodity-costs-and-returns/) - annual hog cost-and-return context, including hog production categories; updated May 1, 2026 when checked.
- [Iowa State Estimated Livestock Returns](https://estimatedreturns.econ.iastate.edu/) - public monthly profitability estimates for swine systems. This is not USDA, but it is a credible public university source if we want an executive margin benchmark.
- [USDA APHIS African Swine Fever](https://direct.aphis.usda.gov/livestock-poultry-disease/swine/african-swine-fever) and related APHIS surveillance resources - risk context, not a routine monthly chart unless we can access stable surveillance data.
- FRED/BLS retail pork series - useful for direct retail series such as bacon, pork chops, and ham when ERS retail files are not enough.

## Proposed Section Architecture

### 1. Executive Snapshot

Purpose: one-screen readout of what changed this month.

Recommended cards:

- Forward supply: breeding herd, farrowing intentions, pig crop, market hogs 180+ lb
- Realized output: weekly FI hog slaughter, monthly commercial slaughter, pork production, average weight
- Value: hog base/net price, pork cutout, belly/ham/loin/rib signals, hog-cutout spread
- Demand clearing: retail feature rate, cold storage, export volume and share of production
- Cost and risk: feed index or hog-corn ratio, margin proxy, ASF/trade risk note

Each card should include latest value, date, YoY change, recent trend, and signal label.

### 2. Herd And Forward Supply

This should become the pork equivalent of the egg flock and supply pipeline sections.

Recommended charts:

- Total, breeding, and market hog inventory
- Market hog weight group composition
- Sows farrowed and farrowing intentions
- Pigs per litter and pig crop
- Pig crop shifted forward against slaughter or production, with an explicit lag assumption
- State concentration map or table as lower-priority context

### 3. Slaughter And Production

This section needs a source fix before design work.

Recommended charts:

- Weekly FI hog slaughter from AMS
- Monthly commercial hog slaughter from NASS
- Pork production in pounds
- Average live weight and/or dressed weight
- Head vs weight contribution to production growth
- Sow slaughter if available
- Production calendar/day-count adjustment

### 4. Prices, Cutout, And Margin

This should be one of the highest-value sections because the current AMS feedstock is already strong.

Recommended charts:

- National base and net hog price
- Pork cutout value
- Primal values: loin, butt, picnic, rib, ham, belly
- Primal contribution to cutout movement over the last month
- Hog-cutout spread or gross packer margin proxy
- Belly/ham seasonality and holiday positioning
- CME/lean hog futures context only if we can access and cite a stable public data feed

### 5. Retail And Domestic Demand

This is currently absent and should be added before the product feels executive-grade.

Recommended charts:

- Weekly retail pork feature rate and activity index
- Featured cut mix by pork section
- Retail prices for bacon, pork chops, ham, and aggregate pork retail value
- Farm-wholesale-retail price spreads from ERS
- Domestic disappearance or per-capita availability from ERS domestic data
- Cross-protein retail affordability versus beef and chicken

### 6. Inventories And Trade

Recommended charts:

- Total pork cold storage
- Bellies, hams, loins, ribs, and other key pork stocks
- Exports vs imports
- Top export destinations by trailing 12 months, not all-time total
- YTD export change by destination
- Export share of pork production
- Live hog trade where it is meaningful

### 7. Costs, Forecasts, And Risk

Recommended charts or modules:

- Feed index using corn and soybean meal proxies
- Hog-corn ratio or hog-feed margin proxy
- ERS annual hog cost-and-return context
- Monthly WASDE/ERS forecast revisions for pork production, prices, imports, exports, and per-capita disappearance
- ASF status and preparedness note
- Trade and regulatory watchlist, with source links and exact date stamps

### 8. Monthly Updates

Add a monthly updates signup section parallel to the egg chartbook. The CSS already contains signup styles, but the pork `index.html` does not include the section.

## Presentation Changes

1. Keep the visual language aligned with the egg chartbook family.
   Continue using Lexend, IAA brand header, navy/orange/teal/gold palette, direct source labels, and the split-dashboard sidebar.

2. Add deterministic chart summaries.
   Each chart should render one concise line: "Latest: 11.2M head, -2.0% YoY, 4-week avg below 5-year median." These can be generated from the same data used for the chart.

3. Add YoY and percentile context by default.
   Executives need "tight/loose/normal" framing. Add 5-year or 10-year percentile bands for inventory, slaughter, production, cutout, primals, retail feature rates, cold storage, exports, and margins.

4. Use seasonal overlays where the business is seasonal.
   Hog slaughter, pork production, belly values, ham values, retail features, and cold storage all benefit from gray historical traces with the current year highlighted in orange or navy.

5. Add toggles only where they clarify.
   Good toggles: absolute vs YoY, current year vs 5-year range, volume vs share, total vs by cut. Avoid cluttering every chart with too many controls.

6. Hide empty modules.
   The current slaughter and production cards should not ship empty. Either fix the ingestion or hide the cards until populated.

7. Keep source labels visible but compact.
   Every card should retain "Chart: Innovate Animal Ag" and a direct source link. Longer methodology can live in a source detail accordion or footer.

8. Make freshness quiet but auditable.
   Put latest fetch and latest data dates in a footer or source detail area. Avoid a large freshness table in the main executive flow.

9. Use the same product loop as egg.
   Add "Pork Executive Monthly Updates" signup language and keep the form visually aligned with the egg chartbook family.

## Implementation Backlog

### High Priority

1. Refresh all sources before launch.
   Local data are stale relative to the May 20, 2026 working date. Run/update NASS, AMS, and ERS ingestion after confirming credentials and source stability.

2. Fix NASS slaughter and pork production ingestion.
   Current `NASS_SERIES` pulls annual hog slaughter and production rows, but the dashboard expects monthly/weekly series. Query Quick Stats by commodity/statistic/frequency and add the appropriate monthly commercial slaughter, pork production, live weight, and dressed weight series.

3. Add farrowings, farrowing intentions, pigs per litter, and market hog weight groups.
   These are foundational to pork forward supply and should be v1, not backlog.

4. Add NASS cold storage for total pork and key cuts.
   This is the largest missing demand-clearing signal.

5. Add AMS weekly retail pork feature activity.
   Build a parser for slug 2868 or stable archived files; start with feature rate, activity index, and national cut-section mix.

6. Add ERS Meat Price Spreads and retail pork cuts.
   Include aggregate pork retail value and key cuts such as bacon, pork chops, and ham. Use FRED/BLS direct series as backup if easier.

7. Rework trade partner selection.
   Use trailing 12-month or YTD top destinations instead of all-time top countries. Add export share of production.

8. Add chart summary text and YoY calculations.
   This should be shared helper logic in `dashboard-common.js` or build-time JSON so the page has consistent executive annotations.

9. Add a pork monthly updates signup section.
   Reuse the existing CSS pattern already present in `split-dashboard.css`.

### Medium Priority

1. Build hog-cutout spread and a transparent margin proxy.
2. Add primal contribution-to-change charts.
3. Add forecast revision tracker from ERS/WASDE.
4. Add feed cost or hog-corn ratio module.
5. Add cross-protein retail affordability context.
6. Add sow slaughter or breeding-herd liquidation signals if source coverage is reliable.
7. Add state concentration map/table as lower-page context.
8. Add a risk/watchlist module for ASF, trade access, and regulatory issues.

### Design/UX Priority

1. Avoid adding a large hero or marketing-style opener.
   The first screen should be the executive product, not a landing page.

2. Keep card count curated.
   Pork has many possible public data series. The page should answer the executive questions before it exposes optional detail.

3. Preserve the egg chartbook's credibility cues.
   Source labels, stable brand treatment, restrained palette, and month-by-month update framing matter more than decorative design.

4. Make empty, lagged, or revised data obvious.
   Trade and NASS series lag. Charts should show latest data dates and not imply data are current through today.

## Recommended V1 Approval Scope

For a clean first production release, I recommend approving this v1 scope:

1. Executive Snapshot with deterministic latest/YoY/trend labels.
2. Herd and Forward Supply with breeding herd, market hogs, weight groups, farrowings, intentions, pigs per litter, and pig crop.
3. Slaughter and Production with fixed monthly/weekly slaughter and pork production series.
4. Prices and Cutout with hog base/net price, cutout, primals, primal spreads, and hog-cutout spread.
5. Inventories and Trade with cold storage and trailing-12-month export destinations.
6. Retail and Domestic Demand with AMS retail feature activity and ERS/BLS retail price context.
7. A compact Costs, Forecasts, and Risk section with feed/margin proxy, forecast revisions, and ASF/trade risk notes.
8. Monthly updates signup, visually aligned with egg chartbook.

That v1 would feel like a real pork executive chartbook rather than a lightly adapted livestock dashboard.
