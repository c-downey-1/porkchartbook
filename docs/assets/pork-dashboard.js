/* pork-dashboard.js - uses helpers from dashboard-common.js */

const C = DASH_COLORS;

// Shared destination → colour map so the same country reads the same colour across
// the US and Brazil export-destination charts. Every listed country gets a unique
// colour so the Brazil chart stays distinct even when its top destinations
// (Philippines, Chile, Hong Kong) appear alongside the force-included US partners
// (South Korea, Canada, Colombia). Falls back to the sequential palette otherwise.
const DEST_COLORS = {
  'Mexico': C.seq[0],
  'Japan': C.seq[1],
  'China': C.seq[2],
  'South Korea': C.seq[3],
  'Canada': C.seq[4],
  'Colombia': C.seq[6],
  'Philippines': C.seq[7],
  'Chile': C.seq[8],
  'Hong Kong': C.seq[9],
};
function destColor(country, i) {
  return DEST_COLORS[country] || C.seq[i % C.seq.length];
}

// Every card is full-width, so a single aspect ratio gives every chart the same
// height. Wrap the shared renderers to force one ratio, overriding any per-call
// value, so no chart looks more vertically smushed than its neighbours.
const PORK_CHART_ASPECT = 2.2;
const _porkRenderLine = renderLineChart;
const _porkRenderBar = renderBarChart;
renderLineChart = (id, labels, datasets, yLabel, extra = {}) =>
  _porkRenderLine(id, labels, datasets, yLabel, Object.assign({}, extra, { aspect: PORK_CHART_ASPECT }));
renderBarChart = (id, labels, datasets, yLabel, extra = {}) =>
  _porkRenderBar(id, labels, datasets, yLabel, Object.assign({}, extra, { aspect: PORK_CHART_ASPECT }));

function porkText(id, text) {
  const node = document.getElementById(id);
  if (node) node.textContent = text;
}

function slugifyText(value) {
  return String(value || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
}

function seriesHasData(series) {
  return !!(series && Array.isArray(series.dates) && series.dates.length && series.values?.some(v => v != null));
}

function seriesLatest(series) {
  return seriesHasData(series) ? latestNonNull(series.dates, series.values) : { date: null, value: null };
}

function toMillions(values) {
  return values.map(v => v != null ? v / 1e6 : null);
}

function quarterLabels(dates) {
  return dates.map(date => {
    const year = String(date || '').slice(0, 4);
    const month = parseInt(String(date || '').slice(5, 7), 10);
    if (!year || !month) return date;
    return `Q${Math.ceil(month / 3)} ${year}`;
  });
}

// Quarterly data has 4 points/year, so range windows are counted in quarters,
// not the calendar-month math used by the shared getRangeSlice helper.
const QUARTER_RANGE_POINTS = { '1y': 4, '3y': 12, '5y': 20, '10y': 40 };

function quarterRangeSlice(dates, range) {
  const points = QUARTER_RANGE_POINTS[range];
  if (!points || range === 'all') return { start: 0, end: dates.length };
  return { start: Math.max(0, dates.length - points), end: dates.length };
}

// Shared High Frequency range config. 7d/1m/3m show daily points off the daily AMS
// series; 6m and longer roll up to weekly averages so point counts stay sane and
// the y-axis magnitude stays consistent across the daily->weekly transition.
const HF_RANGES = {
  '7d':  { bucket: 'daily',  days: 7 },
  '1m':  { bucket: 'daily',  days: 31 },
  '3m':  { bucket: 'daily',  days: 92 },
  '6m':  { bucket: 'weekly', days: 183 },
  '1y':  { bucket: 'weekly', days: 366 },
  '2y':  { bucket: 'weekly', days: 731 },
  '3y':  { bucket: 'weekly', days: 1096 },
  '5y':  { bucket: 'weekly', days: 1827 },
  all:   { bucket: 'weekly', days: null }
};
const HF_OPTIONS = ['7d', '1m', '3m', '6m', '1y'];
const HF_OPTIONS_EXT = ['7d', '1m', '3m', '6m', '1y', '2y', '3y', '5y', 'all'];
const HF_DEFAULT = '1m';

// Slice a daily {dates,values} to the range window, bucketed daily or weekly.
function hfBucket(daily, range) {
  const cfg = HF_RANGES[range] || HF_RANGES[HF_DEFAULT];
  const sliced = sliceTrailingDays(daily.dates || [], daily.values || [], cfg.days);
  return cfg.bucket === 'weekly' ? weeklyAverage(sliced.dates, sliced.values) : sliced;
}

// Render a high-frequency multi-series line chart for the given range.
// seriesDefs: [{ label, series:{dates,values}, color, scale?, extra? }]
function renderHfLine(chartId, seriesDefs, yLabel, range, extra = {}) {
  // HF line charts (prices, cutout, primals) always plot daily points, even at
  // 6m+ ranges — only the trailing window changes, never the granularity.
  const cfg = HF_RANGES[range] || HF_RANGES[HF_DEFAULT];
  const bucketed = seriesDefs
    .filter(s => seriesHasData(s.series))
    .map(s => Object.assign({}, s, { b: sliceTrailingDays(s.series.dates || [], s.series.values || [], cfg.days) }));
  if (!bucketed.length) { hideEmptyCard(chartId); return; }
  const dateSet = new Set();
  bucketed.forEach(s => s.b.dates.forEach(d => dateSet.add(d)));
  const labels = [...dateSet].sort();
  const datasets = bucketed.map(s => {
    const m = Object.fromEntries(s.b.dates.map((d, i) => [d, s.b.values[i]]));
    const data = labels.map(d => {
      const v = m[d];
      if (v == null) return null;
      return s.scale ? v / s.scale : v;
    });
    return dataset(s.label, data, s.color, s.extra || {});
  });
  renderLineChart(chartId, labels, datasets, yLabel, Object.assign({ aspect: 2.6 }, extra));
}

// Render a high-frequency single-series bar chart for the given range.
// opts: { label, color, scale, anchor, subtitle:(bucket)=>string }
function renderHfBar(chartId, daily, yLabel, range, opts = {}) {
  if (!seriesHasData(daily)) { hideEmptyCard(chartId); return; }
  const cfg = HF_RANGES[range] || HF_RANGES[HF_DEFAULT];
  const out = hfBucket(daily, range);
  let values = out.values;
  if (opts.scale) values = values.map(v => v != null ? v / opts.scale : null);
  if (opts.subtitle) setChartSubtitle(chartId, opts.subtitle(cfg.bucket));
  const extra = {};
  if (opts.anchor) {
    // Narrow bands (e.g. carcass weight) read better anchored near the visible min.
    const present = values.filter(v => v != null);
    if (present.length) {
      const lo = Math.min(...present);
      const hi = Math.max(...present);
      const pad = Math.max(1, (hi - lo) * 0.15);
      extra.yMin = Math.floor(lo - pad);
      extra.yMax = Math.ceil(hi + pad);
    }
  }
  if (opts.yAxisWidth != null) extra.yAxisWidth = opts.yAxisWidth;
  renderBarChart(chartId, out.dates, [dataset(opts.label || '', values, opts.color || C.navy)], yLabel, extra);
}

function sliceTrailingDays(dates, values, days) {
  if (!days || !dates.length) return { dates: dates.slice(), values: values.slice() };
  const cutoff = new Date(dates[dates.length - 1] + 'T00:00:00Z');
  cutoff.setUTCDate(cutoff.getUTCDate() - days);
  const iso = cutoff.toISOString().slice(0, 10);
  let start = dates.findIndex(d => d >= iso);
  if (start === -1) start = dates.length;
  return { dates: dates.slice(start), values: values.slice(start) };
}

function sliceTrailingPoints(dates, values, count) {
  if (!count || dates.length <= count) return { dates: dates.slice(), values: values.slice() };
  return { dates: dates.slice(-count), values: values.slice(-count) };
}

// Average daily points into ISO weeks, labelled by the Monday of each week.
function weeklyAverage(dates, values) {
  const buckets = new Map();
  dates.forEach((d, i) => {
    const v = values[i];
    if (v == null) return;
    const dt = new Date(d + 'T00:00:00Z');
    const dow = dt.getUTCDay() || 7;
    dt.setUTCDate(dt.getUTCDate() - (dow - 1));
    const key = dt.toISOString().slice(0, 10);
    const b = buckets.get(key) || { sum: 0, n: 0 };
    b.sum += v;
    b.n += 1;
    buckets.set(key, b);
  });
  const keys = [...buckets.keys()].sort();
  return { dates: keys, values: keys.map(k => buckets.get(k).sum / buckets.get(k).n) };
}

function setChartSubtitle(chartId, text) {
  const sub = document.getElementById(chartId)?.closest('.card')?.querySelector('.sub');
  if (sub) sub.textContent = text;
}

function appendCardSource(chartId, html) {
  const canvas = document.getElementById(chartId);
  if (!canvas) return;
  const card = canvas.closest('.card');
  if (!card) return;
  let node = card.querySelector('.card-source');
  if (!node) {
    node = document.createElement('div');
    node.className = 'card-source';
    card.appendChild(node);
  }
  node.innerHTML = html;
}

function appendInsight(chartId, text) {
  if (!text) return;
  const canvas = document.getElementById(chartId);
  if (!canvas) return;
  const card = canvas.closest('.card');
  if (!card || card.querySelector('.chart-insight')) return;
  const node = document.createElement('div');
  node.className = 'chart-insight';
  node.textContent = text;
  const source = card.querySelector('.card-source');
  if (source) card.insertBefore(node, source);
  else card.appendChild(node);
}

function hideEmptyCard(chartId) {
  const node = document.getElementById(chartId);
  const card = node?.closest('.card');
  if (card) card.classList.add('is-hidden');
}

function insertChartToggle(chartId, labelText, checked, onChange) {
  const canvas = document.getElementById(chartId);
  const card = canvas?.closest('.card');
  if (!card) return null;
  if (card.querySelector(`.chart-toggle[data-chart="${chartId}"]`)) return null;
  const wrap = document.createElement('label');
  wrap.className = 'chart-toggle';
  wrap.dataset.chart = chartId;
  const input = document.createElement('input');
  input.type = 'checkbox';
  input.checked = !!checked;
  const span = document.createElement('span');
  span.textContent = labelText;
  wrap.appendChild(input);
  wrap.appendChild(span);
  input.addEventListener('change', () => onChange(input.checked));
  const toolbar = card.querySelector(`.chart-toolbar[data-chart="${chartId}"]`);
  if (toolbar) toolbar.insertAdjacentElement('beforebegin', wrap);
  else {
    const sub = card.querySelector('.sub');
    if (sub) sub.insertAdjacentElement('afterend', wrap);
    else card.insertBefore(wrap, canvas);
  }
  return wrap;
}

function appendInsights(insights) {
  if (!insights) return;
  Object.entries(insights).forEach(([chartId, text]) => appendInsight(chartId, text));
}

function setPorkChartSources() {
  const nass = '<a href="https://quickstats.nass.usda.gov/" target="_blank" rel="noreferrer">USDA NASS</a>';
  const amsHg = '<a href="https://mpr.datamart.ams.usda.gov/" target="_blank" rel="noreferrer">USDA AMS LM_HG201</a>';
  const amsPk = '<a href="https://mpr.datamart.ams.usda.gov/" target="_blank" rel="noreferrer">USDA AMS LM_PK602</a>';
  const amsRetail = '<a href="https://mymarketnews.ams.usda.gov/" target="_blank" rel="noreferrer">USDA AMS Retail</a>';
  const ers = '<a href="https://www.ers.usda.gov/data-products/livestock-and-meat-international-trade-data/" target="_blank" rel="noreferrer">USDA ERS Trade</a>';
  const fred = '<a href="https://fred.stlouisfed.org/" target="_blank" rel="noreferrer">FRED</a>';
  const comex = '<a href="https://comexstat.mdic.gov.br/" target="_blank" rel="noreferrer">Brazil MDIC/SECEX Comex Stat</a>';
  const wasde = '<a href="https://www.usda.gov/oce/commodity/wasde" target="_blank" rel="noreferrer">USDA WASDE</a>';
  const ersFood = '<a href="https://www.ers.usda.gov/data-products/food-availability-per-capita-data-system" target="_blank" rel="noreferrer">USDA ERS Food Availability</a>';
  const census = '<a href="https://www.census.gov/foreign-trade/data/" target="_blank" rel="noreferrer">US Census Trade</a>';
  const fasPsd = '<a href="https://www.fas.usda.gov/data/production" target="_blank" rel="noreferrer">USDA FAS PSD</a>';
  const ersSpreads = '<a href="https://www.ers.usda.gov/data-products/meat-price-spreads/" target="_blank" rel="noreferrer">USDA ERS Meat Price Spreads</a>';

  const srcMap = {
    herdBreedingMarketChart: `Chart: Innovate Animal Ag • Source: ${nass}`,
    marketWeightChart: `Chart: Innovate Animal Ag • Source: ${nass}`,
    sowsFarrowedChart: `Chart: Innovate Animal Ag • Source: ${nass}`,
    farrowComboTestChart: `Chart: Innovate Animal Ag • Source: ${nass}`,
    slaughterHeadChart: `Chart: Innovate Animal Ag • Source: ${amsHg} • Covered packers ≈ 95% of federally inspected barrow & gilt slaughter`,
    porkProductionChart: `Chart: Innovate Animal Ag • Source: ${amsHg} • Covered packers ≈ 95% of federally inspected barrow & gilt slaughter`,
    carcassWeightChart: `Chart: Innovate Animal Ag • Source: ${amsHg} • Covered packers ≈ 95% of federally inspected barrow & gilt slaughter`,
    commercialSlaughterChart: `Chart: Innovate Animal Ag • Source: ${nass}`,
    productionSeasonalChart: `Chart: Innovate Animal Ag • Source: ${nass}`,
    sowSlaughterChart: `Chart: Innovate Animal Ag • Source: ${nass}`,
    hogPriceChart: `Chart: Innovate Animal Ag • Source: ${amsHg}`,
    cutoutChart: `Chart: Innovate Animal Ag • Source: ${amsPk}`,
    spreadMergeTestChart: `Chart: Innovate Animal Ag • Source: ${amsHg} / ${amsPk}`,
    primalsChart: `Chart: Innovate Animal Ag • Source: ${amsPk}`,
    retailFeatureChart: `Chart: Innovate Animal Ag • Source: ${amsRetail}`,
    retailPriceChart: `Chart: Innovate Animal Ag • Source: ${amsRetail} / ${fred}`,
    coldStorageChart: `Chart: Innovate Animal Ag • Source: ${nass}`,
    tradeFlowChart: `Chart: Innovate Animal Ag • Source: ${ers} / ${comex}`,
    exportDestinationsChart: `Chart: Innovate Animal Ag • Source: ${ers}`,
    importSourcesChart: `Chart: Innovate Animal Ag • Source: ${ers}`,
    exportComparisonChart: `Chart: Innovate Animal Ag • Source: ${ers}`,
    brazilDestinationsChart: `Chart: Innovate Animal Ag • Source: ${comex}`,
    feedPriceChart: `Chart: Innovate Animal Ag • Source: <a href="https://www.cmegroup.com/markets/agriculture.html" target="_blank" rel="noreferrer">CME Group</a>`,
    forecastProductionChart: `Chart: Innovate Animal Ag • Source: ${nass} / ${wasde}`,
    forecastExportsChart: `Chart: Innovate Animal Ag • Source: ${wasde}`,
    forecastPriceChart: `Chart: Innovate Animal Ag • Source: ${amsHg} / ${wasde}`,
    perCapitaChart: `Chart: Innovate Animal Ag • Source: ${ersFood}`,
    proteinConsumptionChart: `Chart: Innovate Animal Ag • Source: ${ersFood}`,
    exportShareCountriesChart: `Chart: Innovate Animal Ag • Source: ${fasPsd}`,
    spreadDollarChart: `Chart: Innovate Animal Ag • Source: ${ersSpreads}`,
    importCutsChart: `Chart: Innovate Animal Ag • Source: ${census}`,
    inputCostChart: `Chart: Innovate Animal Ag • Sources: <a href="https://www.cmegroup.com/markets/agriculture.html" target="_blank" rel="noreferrer">CME Group</a> · <a href="https://fred.stlouisfed.org/series/GASDESW" target="_blank" rel="noreferrer">FRED GASDESW</a> · <a href="https://fred.stlouisfed.org/series/APU000072610" target="_blank" rel="noreferrer">FRED APU000072610</a>`,
  };
  Object.entries(srcMap).forEach(([id, html]) => appendCardSource(id, html));
}

function initPorkSidebarNav() {
  const nav = document.getElementById('porkSidebarNav');
  if (!nav) return;
  const sections = Array.from(document.querySelectorAll('.section[id], .overview-band[id]'));
  if (!sections.length) return;

  const usedIds = new Set(Array.from(document.querySelectorAll('[id]')).map(n => n.id));
  const makeId = base => {
    let candidate = base || 'chart';
    let suffix = 2;
    while (usedIds.has(candidate)) {
      candidate = `${base}-${suffix}`;
      suffix += 1;
    }
    usedIds.add(candidate);
    return candidate;
  };

  sections.forEach(section =>
    Array.from(section.querySelectorAll('.card:not(.is-hidden)')).forEach(card => {
      if (card.id) return;
      card.id = makeId(slugifyText(card.querySelector('h3')?.textContent?.trim() || 'chart'));
    })
  );

  nav.innerHTML = '';
  const groups = sections.map(section => {
    const group = document.createElement('div');
    group.className = 'sidebar-group';
    group.dataset.section = section.id;

    const link = document.createElement('a');
    link.className = 'sidebar-section-link';
    link.href = `#${section.id}`;
    link.textContent = section.querySelector('.section-head h2')?.textContent?.trim() || section.id;
    group.appendChild(link);

    const chartLinks = document.createElement('div');
    chartLinks.className = 'sidebar-chart-links';
    Array.from(section.querySelectorAll('.card:not(.is-hidden)')).forEach(card => {
      const title = card.querySelector('h3')?.textContent?.trim();
      if (!title || !card.id) return;
      const a = document.createElement('a');
      a.className = 'sidebar-chart-link';
      a.href = `#${card.id}`;
      a.textContent = title;
      chartLinks.appendChild(a);
    });
    group.appendChild(chartLinks);
    nav.appendChild(group);
    return group;
  });

  const mobileSelect = document.getElementById('mobileSectionSelect');
  if (mobileSelect) {
    mobileSelect.innerHTML = '<option value="">Jump to section...</option>';
    sections.forEach(section => {
      const option = document.createElement('option');
      option.value = `#${section.id}`;
      option.textContent = section.querySelector('.section-head h2')?.textContent?.trim() || section.id;
      mobileSelect.appendChild(option);
    });
    mobileSelect.addEventListener('change', () => {
      if (mobileSelect.value) {
        location.hash = mobileSelect.value;
        mobileSelect.value = '';
      }
    });
  }

  // Scroll-spy: the active section is the last one whose top has crossed a trigger
  // line near the top of the viewport. Deterministic, so it works for tall sections
  // (Supply, Cost) that an intersection-ratio observer would miss.
  function updateActiveSection() {
    const triggerY = window.innerHeight * 0.28;
    let activeId = sections[0] ? sections[0].id : null;
    sections.forEach(section => {
      if (section.getBoundingClientRect().top <= triggerY) activeId = section.id;
    });
    groups.forEach(group => group.classList.toggle('is-active', group.dataset.section === activeId));
  }
  window.addEventListener('scroll', updateActiveSection, { passive: true });
  window.addEventListener('resize', updateActiveSection);
  updateActiveSection();
}

function formatSnapshotValue(card) {
  const value = card?.value;
  if (value == null || Number.isNaN(value)) return '--';
  if (card.format === 'currency') return '$' + fmtNum(value, 2);
  if (card.format === 'percent') return fmtNum(value, 1) + '%';
  if (card.format === 'head' || card.format === 'pounds') return fmtM(value);
  return fmtNum(value, 1);
}

function populatePorkSnapshot(snapshot) {
  const row = document.getElementById('porkKpiRow');
  if (!row) return;
  row.innerHTML = '';
  (snapshot || []).forEach(card => {
    const article = document.createElement('article');
    article.className = `kpi ${card.change?.signal || ''}`;
    const change = card.change?.text ? ` • ${card.change.text}` : '';
    article.innerHTML = `
      <div class="label">${card.label}</div>
      <div class="value">${formatSnapshotValue(card)}</div>
      <div class="sub">${card.date || 'latest'}${card.unit ? ` • ${card.unit}` : ''}${change}</div>
    `;
    row.appendChild(article);
  });
}

function buildHerd(herd) {
  const breeding = herd.breeding_inventory;
  if (seriesHasData(breeding)) {
    registerRangeControl({
      chartId: 'herdBreedingMarketChart',
      options: ['1y', '5y', '10y', 'all'],
      defaultRange: '5y',
      renderer(range) {
        // Quarterly data: count range windows in quarters and use a category
        // x-axis with auto-skip so the labels aren't all crammed together.
        const { start, end } = quarterRangeSlice(breeding.dates, range);
        const dates = breeding.dates.slice(start, end);
        renderLineChart(
          'herdBreedingMarketChart',
          quarterLabels(dates),
          [dataset('Breeding stock', toMillions(breeding.values.slice(start, end)), C.navy, { fill: true, backgroundColor: 'rgba(1,48,70,0.08)' })],
          'Million head',
          {
            categoryX: true, maxTicks: 6, yAxisWidth: 56,
            tooltip: {
              callbacks: {
                label(ctx) {
                  const v = Number(ctx.parsed.y);
                  if (!Number.isFinite(v)) return ctx.dataset.label || '';
                  return `${ctx.dataset.label}: ${fmtNum(v, 2)}`;
                }
              }
            }
          }
        );
      }
    });
  } else {
    hideEmptyCard('herdBreedingMarketChart');
  }

  const groups = Object.entries(herd.weight_groups || {}).filter(([, item]) => seriesHasData(item));
  if (groups.length) {
    const hasBreeding = seriesHasData(breeding);
    const dateSet = new Set(groups.flatMap(([, item]) => item.dates));
    if (hasBreeding) breeding.dates.forEach(d => dateSet.add(d));
    const dates = [...dateSet].sort();
    const maps = Object.fromEntries(groups.map(([name, item]) => [name, Object.fromEntries(item.dates.map((d, i) => [d, item.values[i]]))]));
    const breedingMap = hasBreeding ? Object.fromEntries(breeding.dates.map((d, i) => [d, breeding.values[i]])) : {};

    // Default to including breeding stock so the hover total reflects the full hog count.
    let includeBreeding = hasBreeding;

    const renderMarketWeight = range => {
      const { start, end } = quarterRangeSlice(dates, range);
      const labels = dates.slice(start, end);
      const datasets = groups.map(([name], i) =>
        dataset(name, labels.map(d => maps[name][d] != null ? maps[name][d] / 1e6 : null), C.seq[i % C.seq.length], { stack: 'hogs' })
      );
      if (includeBreeding && hasBreeding) {
        datasets.push(dataset('Breeding stock', labels.map(d => breedingMap[d] != null ? breedingMap[d] / 1e6 : null), C.slate, { stack: 'hogs' }));
      }
      renderBarChart('marketWeightChart', quarterLabels(labels), datasets, 'Million head', {
        aspect: 2.6,
        stacked: true,
        categoryX: true,
        maxTicks: 10,
        tooltip: {
          callbacks: {
            label(ctx) {
              const v = Number(ctx.parsed.y);
              if (!Number.isFinite(v)) return ctx.dataset.label || '';
              return `${ctx.dataset.label}: ${fmtNum(v, 2)}M`;
            },
            footer(items) {
              const total = items.reduce((sum, it) => sum + (Number(it.parsed.y) || 0), 0);
              return `${includeBreeding ? 'Total hogs' : 'Market hogs'}: ${fmtNum(total, 2)}M head`;
            }
          }
        }
      });
    };

    registerRangeControl({
      chartId: 'marketWeightChart',
      options: ['1y', '3y', '5y', '10y', 'all'],
      defaultRange: '10y',
      renderer: renderMarketWeight
    });

    if (hasBreeding) {
      insertChartToggle('marketWeightChart', 'Include breeding stock', includeBreeding, checked => {
        includeBreeding = checked;
        renderMarketWeight(chartRanges['marketWeightChart']);
      });
    }
  } else {
    hideEmptyCard('marketWeightChart');
  }

  const sows = herd.sows_farrowed;
  if (seriesHasData(sows)) {
    registerRangeControl({
      chartId: 'sowsFarrowedChart',
      options: ['1y', '5y', '10y', 'all'],
      defaultRange: '5y',
      renderer(range) {
        const { start, end } = getRangeSlice(sows.dates, range);
        renderLineChart(
          'sowsFarrowedChart',
          sows.dates.slice(start, end),
          [dataset('Sows farrowed', toMillions(sows.values.slice(start, end)), C.navy, { borderWidth: 1.8 })],
          'Million head',
          {
            xRotation: 45,
            tooltip: {
              callbacks: {
                label(ctx) {
                  const v = Number(ctx.parsed.y);
                  if (!Number.isFinite(v)) return ctx.dataset.label || '';
                  return `${ctx.dataset.label}: ${fmtNum(v, 2)}`;
                }
              }
            }
          }
        );
      }
    });
  } else {
    hideEmptyCard('sowsFarrowedChart');
  }

  // Pig crop (line, left million-head axis) + pigs per litter (orange diamonds,
  // right axis). Replaces the former standalone pig-crop and pigs-per-litter cards.
  const cPig = herd.pig_crop, cLitter = herd.pigs_per_litter;
  if (seriesHasData(cPig) || seriesHasData(cLitter)) {
    const allDates = [...new Set([
      ...(cPig?.dates || []), ...(cLitter?.dates || [])
    ])].sort();
    const mapOf = s => Object.fromEntries((s?.dates || []).map((d, i) => [d, s.values[i]]));
    const pcMap = mapOf(cPig), plMap = mapOf(cLitter);
    registerRangeControl({
      chartId: 'farrowComboTestChart',
      options: ['1y', '5y', '10y', 'all'],
      defaultRange: '5y',
      renderer(range) {
        const { start, end } = getRangeSlice(allDates, range);
        const labels = allDates.slice(start, end);
        const pcVals = labels.map(d => pcMap[d] != null ? pcMap[d] / 1e6 : null);
        const plVals = labels.map(d => plMap[d] != null ? plMap[d] : null);
        // Anchor each axis to its own data band so both series show their
        // month-to-month variation instead of sitting flat.
        const band = (vals, padFloor) => {
          const present = vals.filter(v => v != null);
          if (!present.length) return {};
          const lo = Math.min(...present), hi = Math.max(...present);
          const pad = Math.max(padFloor, (hi - lo) * 0.4);
          return { min: Math.floor((lo - pad) * 10) / 10, max: Math.ceil((hi + pad) * 10) / 10 };
        };
        const yBand = band(pcVals, 0.2);
        const y2Band = band(plVals, 0.5);
        const ctx = document.getElementById('farrowComboTestChart');
        if (!ctx) return;
        destroyChart('farrowComboTestChart');
        const opts = baseOptions('Million head', {
          chartId: 'farrowComboTestChart', y2: 'Pigs per litter', aspect: PORK_CHART_ASPECT,
          yMin: yBand.min, yMax: yBand.max, y2Min: y2Band.min, y2Max: y2Band.max,
          xRotation: 45
        });
        charts['farrowComboTestChart'] = new Chart(ctx, {
          type: 'line',
          data: {
            labels,
            datasets: [
              dataset('Pig crop', pcVals, C.navy, { yAxisID: 'y', order: 2, type: 'line', borderWidth: 1.8, pointRadius: 0, pointHoverRadius: 5 }),
              dataset('Pigs per litter', plVals, C.orange, { yAxisID: 'y2', order: 1, type: 'line', borderWidth: 1.8, pointRadius: 0, pointHoverRadius: 6 })
            ]
          },
          options: opts
        });
      }
    });
  } else {
    hideEmptyCard('farrowComboTestChart');
  }
}

function buildSlaughterProduction(sp) {
  // Daily hogs processed — daily AMS head count (covered packers), bar.
  const dailyHead = sp.daily_direct_hog_count;
  if (seriesHasData(dailyHead)) {
    registerRangeControl({
      chartId: 'slaughterHeadChart',
      options: HF_OPTIONS,
      defaultRange: HF_DEFAULT,
      renderer(range) {
        renderHfBar('slaughterHeadChart', dailyHead, 'Thousand head', range, {
          label: 'Hogs processed', color: C.teal, scale: 1e3, anchor: true,
          subtitle: b => b === 'weekly'
            ? 'Weekly average of daily hogs processed, thousand head/day (AMS LM_HG201, covered packers).'
            : 'Daily hogs processed, thousand head (AMS LM_HG201, covered packers).'
        });
      }
    });
  } else {
    hideEmptyCard('slaughterHeadChart');
  }

  // Estimated pork production — daily hog count x carcass weight, bar.
  const dailyProd = sp.daily_estimated_production;
  if (seriesHasData(dailyProd)) {
    registerRangeControl({
      chartId: 'porkProductionChart',
      options: HF_OPTIONS,
      defaultRange: HF_DEFAULT,
      renderer(range) {
        renderHfBar('porkProductionChart', dailyProd, 'Million lb', range, {
          label: 'Estimated production', color: C.navy, scale: 1e6, anchor: true, yAxisWidth: 94,
          subtitle: b => b === 'weekly'
            ? 'Weekly average of daily estimated production, million lb/day (daily hogs × carcass weight).'
            : 'Daily estimated pork production, million lb (daily hogs × carcass weight).'
        });
      }
    });
  } else {
    hideEmptyCard('porkProductionChart');
  }

  // Average carcass weight — daily AMS, bar anchored to the visible band.
  const weightDaily = sp.avg_carcass_weight;
  if (seriesHasData(weightDaily)) {
    registerRangeControl({
      chartId: 'carcassWeightChart',
      options: HF_OPTIONS,
      defaultRange: HF_DEFAULT,
      renderer(range) {
        renderHfBar('carcassWeightChart', weightDaily, 'Pounds', range, {
          label: 'Average carcass weight', color: C.gold, anchor: true,
          subtitle: b => `${b === 'weekly' ? 'Weekly' : 'Daily'} average carcass weight, pounds (AMS LM_HG201).`
        });
      }
    });
  } else {
    hideEmptyCard('carcassWeightChart');
  }
}

// NASS monthly Livestock Slaughter — true commercial (~99% of industry) charts.
function buildNassSlaughter(sp) {
  // Commercial hog slaughter: total commercial (FI + non-FI) with FI overlaid.
  const commercial = sp.nass_commercial_slaughter;
  const fi = sp.nass_fi_slaughter;
  if (seriesHasData(commercial) || seriesHasData(fi)) {
    const dates = [...new Set([...(commercial?.dates || []), ...(fi?.dates || [])])].sort();
    const commercialMap = Object.fromEntries((commercial?.dates || []).map((d, i) => [d, commercial.values[i]]));
    const fiMap = Object.fromEntries((fi?.dates || []).map((d, i) => [d, fi.values[i]]));
    registerRangeControl({
      chartId: 'commercialSlaughterChart',
      options: ['1y', '2y', '5y', '10y', 'all'],
      defaultRange: '2y',
      renderer(range) {
        const { start, end } = getRangeSlice(dates, range);
        const labels = dates.slice(start, end);
        // Stack federally inspected + the non-FI remainder so the bar totals commercial.
        const fiVals = labels.map(d => fiMap[d] != null ? fiMap[d] / 1e6 : null);
        const nonFiVals = labels.map(d => {
          const c = commercialMap[d], f = fiMap[d];
          return (c != null && f != null) ? Math.max(0, (c - f) / 1e6) : null;
        });
        renderBarChart(
          'commercialSlaughterChart',
          labels,
          [
            dataset('Federally inspected', fiVals, C.teal, { stack: 'slaughter' }),
            dataset('Other commercial (non-FI)', nonFiVals, C.slate, { stack: 'slaughter' }),
          ],
          'Million head',
          {
            stacked: true,
            tooltip: {
              callbacks: {
                label(ctx) {
                  const v = Number(ctx.parsed.y);
                  if (!Number.isFinite(v)) return ctx.dataset.label || '';
                  return `${ctx.dataset.label}: ${fmtNum(v, 2)}M`;
                },
                footer(items) {
                  const total = items.reduce((sum, it) => sum + (Number(it.parsed.y) || 0), 0);
                  return `Commercial total: ${fmtNum(total, 2)}M head`;
                }
              }
            }
          }
        );
      }
    });
  } else {
    hideEmptyCard('commercialSlaughterChart');
  }

  // Monthly production comparison — same data, one line per year (last N) on a
  // Jan-Dec axis. Recent years are highlighted (2026 yellow, 2025 orange) and
  // prior years are gray, for a seasonal vs-history read.
  const prodSeasonal = sp.nass_pork_production;
  if (seriesHasData(prodSeasonal)) {
    const ymMap = buildYearMonthMap(prodSeasonal.dates, toMillions(prodSeasonal.values));
    const HILITE = { 2026: C.gold, 2025: C.orange };
    const YEARS_N = { '5y': 5, '10y': 10, all: 99 };
    registerRangeControl({
      chartId: 'productionSeasonalChart',
      options: ['5y', '10y', 'all'],
      defaultRange: '10y',
      renderer(range) {
        const years = Object.keys(ymMap).map(Number).sort((a, b) => a - b).slice(-(YEARS_N[range] || 10));
        const grayYears = years.filter(y => !HILITE[y]);
        // One collapsed legend entry for all the gray years, e.g. "2017 – 2024".
        const grayLabel = grayYears.length ? `${grayYears[0]} – ${grayYears[grayYears.length - 1]}` : 'Prior years';
        // Array order (gray first) keeps the legend chronological; the `order`
        // property forces draw z-order — lower = on top — so the highlighted
        // 2025/2026 lines always sit above the gray and nothing crosses over them.
        const ordered = [...grayYears, ...years.filter(y => HILITE[y]).sort((a, b) => a - b)];
        const datasets = ordered.map(yr => dataset(String(yr), monthsForYear(ymMap, yr), HILITE[yr] || '#c4ccd2', {
          borderWidth: HILITE[yr] ? 4.2 : 1.4,
          order: HILITE[yr] ? (yr === 2026 ? 0 : 1) : 10,
          legendKey: HILITE[yr] ? undefined : 'historical',
          legendLabel: HILITE[yr] ? undefined : grayLabel
        }));
        renderLineChart('productionSeasonalChart', MON_SHORT, datasets, 'Million lb', {
          categoryX: true,
          maxTicks: 12,
          tooltip: {
            itemSort(a, b) {
              return Number(b.dataset.label) - Number(a.dataset.label);
            },
            callbacks: {
              label(ctx) {
                const v = Number(ctx.parsed.y);
                if (!Number.isFinite(v)) return '';
                return `${ctx.dataset.label}: ${fmtNum(v, 0)}M lb`;
              }
            }
          }
        });
      }
    });
  } else {
    hideEmptyCard('productionSeasonalChart');
  }


  // Sow & boar slaughter (thousand head) — breeding-herd cull signal.
  const sows = sp.nass_sows;
  const boars = sp.nass_boars;
  if (seriesHasData(sows) || seriesHasData(boars)) {
    const dates = [...new Set([...(sows?.dates || []), ...(boars?.dates || [])])].sort();
    const sowsMap = Object.fromEntries((sows?.dates || []).map((d, i) => [d, sows.values[i]]));
    const boarsMap = Object.fromEntries((boars?.dates || []).map((d, i) => [d, boars.values[i]]));
    registerRangeControl({
      chartId: 'sowSlaughterChart',
      options: ['1y', '2y', '3y', '5y', '10y', 'all'],
      defaultRange: '1y',
      renderer(range) {
        const { start, end } = getRangeSlice(dates, range);
        const labels = dates.slice(start, end);
        renderBarChart(
          'sowSlaughterChart',
          labels,
          [
            dataset('Sows', labels.map(d => sowsMap[d] != null ? sowsMap[d] / 1e3 : null), C.orange, { stack: 'cull' }),
            dataset('Boars', labels.map(d => boarsMap[d] != null ? boarsMap[d] / 1e3 : null), C.slate, { stack: 'cull' }),
          ],
          'Thousand head',
          {
            stacked: true, yAxisWidth: 64, yTitlePad: { bottom: 8 },
            tooltip: {
              callbacks: {
                label(ctx) {
                  const v = Number(ctx.parsed.y);
                  if (!Number.isFinite(v)) return ctx.dataset.label || '';
                  return `${ctx.dataset.label}: ${fmtNum(v, 1)}k`;
                },
                footer(items) {
                  const total = items.reduce((sum, it) => sum + (Number(it.parsed.y) || 0), 0);
                  return `Total: ${fmtNum(total, 1)}k head`;
                }
              }
            }
          }
        );
      }
    });
  } else {
    hideEmptyCard('sowSlaughterChart');
  }
}

function buildPrices(prices) {
  // Barrow & gilt base/net prices — daily AMS, standard HF ranges.
  const base = prices.barrow_gilt_base_price;
  const net = prices.barrow_gilt_net_price;
  if (seriesHasData(base) || seriesHasData(net)) {
    registerRangeControl({
      chartId: 'hogPriceChart',
      options: HF_OPTIONS,
      defaultRange: '3m',
      renderer(range) {
        renderHfLine('hogPriceChart', [
          { label: 'Base price', series: base, color: C.navy },
          { label: 'Net price', series: net, color: C.teal },
        ], '$/cwt', range);
      }
    });
  } else {
    hideEmptyCard('hogPriceChart');
  }

  // Pork cutout — exception: short HF frames plus the longer ranges.
  const cutout = prices.pork_cutout_value;
  if (seriesHasData(cutout)) {
    registerRangeControl({
      chartId: 'cutoutChart',
      options: ['7d', '1m', '3m', '1y', '2y', '5y', 'all'],
      defaultRange: HF_DEFAULT,
      renderer(range) {
        renderHfLine('cutoutChart', [
          { label: 'Pork cutout', series: cutout, color: C.gold, extra: { fill: true, backgroundColor: 'rgba(253,183,20,0.10)' } },
        ], '$/cwt', range);
      }
    });
  } else {
    hideEmptyCard('cutoutChart');
  }

  // Cutout less net hog price — daily spread (light line) + a 30-day rolling average (bold).
  const spread = prices.cutout_net_spread || prices.cutout_base_spread;
  if (seriesHasData(spread)) {
    // 30-calendar-day trailing average of the daily series.
    const roll = [];
    for (let i = 0; i < spread.dates.length; i++) {
      const startMs = new Date(spread.dates[i] + 'T00:00:00Z').getTime() - 29 * 86400000;
      let s = 0, n = 0;
      for (let j = i; j >= 0; j--) {
        if (new Date(spread.dates[j] + 'T00:00:00Z').getTime() < startMs) break;
        const v = spread.values[j];
        if (v != null) { s += v; n += 1; }
      }
      roll.push(n ? s / n : null);
    }
    const rollMap = Object.fromEntries(spread.dates.map((d, i) => [d, roll[i]]));
    const DAYS = { '1m': 31, '3m': 92, '1y': 366, '2y': 731, '5y': 1827, all: null };
    registerRangeControl({
      chartId: 'spreadMergeTestChart',
      options: ['1m', '3m', '1y', '2y', '5y', 'all'],
      defaultRange: '2y',
      renderer(range) {
        const { dates, values } = sliceTrailingDays(spread.dates, spread.values, DAYS[range]);
        const overlay = dates.map(d => rollMap[d] != null ? rollMap[d] : null);
        renderLineChart('spreadMergeTestChart', dates, [
          dataset('Daily spread', values, C.orange, { borderWidth: 1.2, pointRadius: 0, order: 2, fill: false }),
          dataset('30-day average', overlay, C.navy, { borderWidth: 2.6, pointRadius: 0, order: 1, tension: 0, fill: false }),
        ], '$/cwt');
      }
    });
  } else {
    hideEmptyCard('spreadMergeTestChart');
  }

  // Primal values — exception: short HF frames plus the longer ranges.
  const primals = Object.entries(prices.primals || {}).filter(([, item]) => seriesHasData(item));
  if (primals.length) {
    registerRangeControl({
      chartId: 'primalsChart',
      options: HF_OPTIONS_EXT,
      defaultRange: '1y',
      renderer(range) {
        renderHfLine('primalsChart',
          primals.map(([name, item], i) => ({ label: name, series: item, color: C.seq[i % C.seq.length] })),
          '$/cwt', range);
      }
    });
  } else {
    hideEmptyCard('primalsChart');
  }
}

function buildRetailDemand(retail) {
  const feature = retail.feature_rate;
  const activity = retail.activity_index;
  if (seriesHasData(feature) || seriesHasData(activity)) {
    const dates = [...new Set([...(feature.dates || []), ...(activity.dates || [])])].sort();
    const featureMap = Object.fromEntries((feature.dates || []).map((d, i) => [d, feature.values[i]]));
    const activityMap = Object.fromEntries((activity.dates || []).map((d, i) => [d, activity.values[i]]));
    registerRangeControl({
      chartId: 'retailFeatureChart',
      options: ['6m', '1y', '2y', '5y', 'all'],
      defaultRange: '2y',
      renderer(range) {
        const { start, end } = getRangeSlice(dates, range);
        const labels = dates.slice(start, end);
        renderLineChart(
          'retailFeatureChart',
          labels,
          [
            dataset('Feature rate', labels.map(d => featureMap[d] != null ? featureMap[d] * 100 : null), C.teal),
            dataset('Activity index', labels.map(d => activityMap[d] ?? null), C.gold, { yAxisID: 'y2' }),
          ],
          'Feature rate (%)',
          {
            y2: 'Activity index', aspect: 2.6,
            yTickCallback: v => `${v}%`,
            tooltip: {
              callbacks: {
                label(ctx) {
                  const v = Number(ctx.parsed.y);
                  if (!Number.isFinite(v)) return ctx.dataset.label || '';
                  return ctx.dataset.label === 'Feature rate'
                    ? `Feature rate: ${fmtNum(v, 1)}%`
                    : `${ctx.dataset.label}: ${fmtNum(v, 1)}`;
                }
              }
            }
          }
        );
      }
    });
  } else {
    hideEmptyCard('retailFeatureChart');
  }

  const retailPrice = retail.featured_average_price;
  const bacon = retail.fred_bacon_price;
  if (seriesHasData(retailPrice) || seriesHasData(bacon)) {
    const dates = [...new Set([...(retailPrice.dates || []), ...(bacon.dates || [])])].sort();
    const retailMap = Object.fromEntries((retailPrice.dates || []).map((d, i) => [d, retailPrice.values[i]]));
    const baconMap = Object.fromEntries((bacon.dates || []).map((d, i) => [d, bacon.values[i]]));
    registerRangeControl({
      chartId: 'retailPriceChart',
      options: ['1y', '2y', '3y', '5y', '10y', 'all'],
      defaultRange: '3y',
      renderer(range) {
        const { start, end } = getRangeSlice(dates, range);
        const labels = dates.slice(start, end);
        renderLineChart(
          'retailPriceChart',
          labels,
          [
            dataset('Featured pork avg', labels.map(d => retailMap[d] ?? null), C.navy),
            dataset('Retail bacon proxy', labels.map(d => baconMap[d] ?? null), C.orange),
          ],
          '$/lb'
        );
      }
    });
  } else {
    hideEmptyCard('retailPriceChart');
  }

  // Per-capita pork availability (boneless, left) + total domestic disappearance
  // (right). Annual ERS series; show the modern era for readability.
  const pcd = retail.per_capita_disappearance || {};
  const boneless = (pcd.per_capita || {}).boneless;
  const disappearance = pcd.domestic_disappearance;
  if (seriesHasData(boneless) || seriesHasData(disappearance)) {
    const allDates = [...new Set([...(boneless?.dates || []), ...(disappearance?.dates || [])])]
      .filter(d => d >= '1986').sort();
    const bMap = Object.fromEntries((boneless?.dates || []).map((d, i) => [d, boneless.values[i]]));
    const dMap = Object.fromEntries((disappearance?.dates || []).map((d, i) => [d, disappearance.values[i]]));
    const N = { '5y': 5, '10y': 10, all: 9999 };
    registerRangeControl({
      chartId: 'perCapitaChart',
      options: ['5y', '10y', 'all'],
      defaultRange: 'all',
      renderer(range) {
        const dates = allDates.slice(-(N[range] || 10));
        renderLineChart(
          'perCapitaChart',
          dates,
          [
            dataset('Per-capita consumption', dates.map(d => bMap[d] ?? null), C.navy),
            dataset('Domestic disappearance', dates.map(d => dMap[d] ?? null), C.gold, { yAxisID: 'y2' }),
          ],
          'lb / person / yr',
          { y2: 'Million lb', categoryX: true, maxTicks: 12 }
        );
      }
    });
  } else {
    hideEmptyCard('perCapitaChart');
  }

  // Per-capita consumption: pork vs chicken vs beef (ERS Food Availability, annual).
  const pbm = retail.per_capita_by_meat || {};
  const pork = pbm.pork, beef = pbm.beef, chicken = pbm.chicken;
  if (seriesHasData(pork) || seriesHasData(beef) || seriesHasData(chicken)) {
    const allDates = [...new Set([...(pork?.dates || []), ...(beef?.dates || []), ...(chicken?.dates || [])])]
      .filter(d => d >= '1966').sort();
    const mk = s => Object.fromEntries((s?.dates || []).map((d, i) => [d, s.values[i]]));
    const pMap = mk(pork), bMap = mk(beef), cMap = mk(chicken);
    const N = { '5y': 5, '10y': 10, all: 9999 };
    registerRangeControl({
      chartId: 'proteinConsumptionChart',
      options: ['5y', '10y', 'all'],
      defaultRange: 'all',
      renderer(range) {
        const dates = allDates.slice(-(N[range] || 9999));
        renderLineChart('proteinConsumptionChart', dates, [
          dataset('Pork', dates.map(d => pMap[d] ?? null), C.navy),
          dataset('Chicken', dates.map(d => cMap[d] ?? null), C.teal),
          dataset('Beef', dates.map(d => bMap[d] ?? null), C.orange),
        ], 'lb / person / yr', { categoryX: true, maxTicks: 12 });
      }
    });
  } else {
    hideEmptyCard('proteinConsumptionChart');
  }
}

function buildInventoryTrade(inventoryTrade) {
  const cold = inventoryTrade.cold_storage || {};
  const coldEntries = [
    ['Total pork', cold.total],
    ['Bellies', cold.bellies],
    ['Hams', cold.hams],
    ['Loins', cold.loins],
  ].filter(([, item]) => seriesHasData(item));
  if (coldEntries.length) {
    const dates = [...new Set(coldEntries.flatMap(([, item]) => item.dates))].sort();
    const maps = Object.fromEntries(coldEntries.map(([name, item]) => [name, Object.fromEntries(item.dates.map((d, i) => [d, item.values[i]]))]));
    registerRangeControl({
      chartId: 'coldStorageChart',
      options: ['3y', '5y', '10y', 'all'],
      defaultRange: '3y',
      renderer(range) {
        const { start, end } = getRangeSlice(dates, range);
        const labels = dates.slice(start, end);
        renderLineChart(
          'coldStorageChart',
          labels,
          coldEntries.map(([name], i) => dataset(name, labels.map(d => maps[name][d] != null ? maps[name][d] / 1e6 : null), C.seq[i % C.seq.length])),
          'Million lb'
        );
      }
    });
  } else {
    hideEmptyCard('coldStorageChart');
  }

  const trade = inventoryTrade.trade || {};
  const totals = trade.trade_totals || {};
  // Brazil export total (Comex Stat) — overlaid on the trade-flow chart and reused
  // for the "Other" remainder on the Brazil destinations chart below.
  const brazil = inventoryTrade.brazil_exports || {};
  const brazilTotal = brazil.total || {};
  const brazilExportMap = {};
  (brazilTotal.dates || []).forEach((d, i) => {
    const v = brazilTotal.values[i];
    if (v != null) brazilExportMap[d] = v;
  });
  // US exports in product weight (US Census, HS 0203 fresh/frozen) — now on the
  // same basis as Brazil's fresh/frozen (Comex Stat), so the two are comparable.
  const usPw = (inventoryTrade.us_trade_product_weight || {}).export_fresh_frozen || {};
  if (usPw.dates?.length) {
    // Aggregate both series monthly → calendar quarters (sum) for a smoother read.
    const qRep = m => `${m.slice(0, 4)}-${String(Math.ceil(Number(m.slice(5, 7)) / 3) * 3).padStart(2, '0')}`;
    const usMonthMap = Object.fromEntries(usPw.dates.map((d, i) => [d, usPw.values[i]]));
    const monthlyDates = [...new Set([...(usPw.dates || []), ...(brazilTotal.dates || [])])].sort();
    const qMonthCount = {};
    monthlyDates.forEach(m => { const q = qRep(m); qMonthCount[q] = (qMonthCount[q] || 0) + 1; });
    const quarterDates = [...new Set(monthlyDates.map(qRep))].sort();
    if (quarterDates.length && qMonthCount[quarterDates[quarterDates.length - 1]] < 3) quarterDates.pop();
    const qIndex = Object.fromEntries(quarterDates.map((q, i) => [q, i]));
    const aggregate = monthMap => {
      const arr = quarterDates.map(() => null);
      Object.keys(monthMap).forEach(m => {
        const v = monthMap[m];
        if (v == null) return;
        const qi = qIndex[qRep(m)];
        if (qi != null) arr[qi] = (arr[qi] || 0) + v;
      });
      return arr;
    };
    const usQ = aggregate(usMonthMap);
    const bzQ = aggregate(brazilExportMap);
    registerRangeControl({
      chartId: 'tradeFlowChart',
      options: ['3y', '5y', '10y', 'all'],
      defaultRange: '10y',
      renderer(range) {
        const { start, end } = quarterRangeSlice(quarterDates, range);
        const labels = quarterLabels(quarterDates.slice(start, end));
        const usSlice = usQ.slice(start, end), bzSlice = bzQ.slice(start, end);
        // Period growth: 1-year (4-quarter) average at each end, so a single noisy
        // quarter doesn't distort the headline. Shown in the legend, updates per range.
        const pctGrowth = arr => {
          const v = arr.filter(x => x != null);
          if (v.length < 2) return null;
          const k = Math.min(4, Math.floor(v.length / 2));
          const avg = a => a.reduce((s, x) => s + x, 0) / a.length;
          const first = avg(v.slice(0, k));
          if (!first) return null;
          return Math.round((avg(v.slice(-k)) / first - 1) * 100);
        };
        const tag = g => g == null ? '' : (g >= 0 ? `  ▲ +${g}%` : `  ▼ ${Math.abs(g)}%`);
        renderLineChart(
          'tradeFlowChart',
          labels,
          [
            dataset(`US pork exports${tag(pctGrowth(usSlice))}`, usSlice, C.teal),
            dataset(`Brazil pork exports${tag(pctGrowth(bzSlice))}`, bzSlice, C.navy),
          ],
          'Million lb',
          {
            aspect: 2.6, categoryX: true,
            tooltip: {
              callbacks: {
                label(ctx) {
                  const v = Number(ctx.parsed.y);
                  const name = (ctx.dataset.label || '').split('  ')[0];
                  return Number.isFinite(v) ? `${name}: ${fmtNum(v, 0)}M lb` : name;
                }
              }
            }
          }
        );
      }
    });
  } else {
    hideEmptyCard('tradeFlowChart');
  }

  const exports = trade.exports_by_destination || {};
  if (exports.dates?.length && Object.keys(exports.series || {}).length) {
    const countries = Object.entries(exports.series);
    // Aggregate monthly → calendar quarters (sum), scaled to million lb.
    const qRep = m => `${m.slice(0, 4)}-${String(Math.ceil(Number(m.slice(5, 7)) / 3) * 3).padStart(2, '0')}`;
    const qMonthCount = {};
    exports.dates.forEach(m => { const q = qRep(m); qMonthCount[q] = (qMonthCount[q] || 0) + 1; });
    const quarterDates = [...new Set(exports.dates.map(qRep))].sort();
    if (quarterDates.length && qMonthCount[quarterDates[quarterDates.length - 1]] < 3) quarterDates.pop();
    const qIndex = Object.fromEntries(quarterDates.map((q, i) => [q, i]));
    const qCountries = countries.map(([country, values]) => {
      const arr = quarterDates.map(() => null);
      exports.dates.forEach((m, i) => { const v = values[i]; if (v == null) return; const qi = qIndex[qRep(m)]; if (qi != null) arr[qi] = (arr[qi] || 0) + v / 1000; });
      return [country, arr];
    });
    const qTotal = quarterDates.map(() => null);
    (totals.dates || []).forEach((m, i) => { const v = (totals.export_pork || [])[i]; if (v == null) return; const qi = qIndex[qRep(m)]; if (qi != null) qTotal[qi] = (qTotal[qi] || 0) + v / 1000; });
    registerRangeControl({
      chartId: 'exportDestinationsChart',
      options: ['5y', '10y', 'all'],
      defaultRange: '5y',
      renderer(range) {
        const { start, end } = quarterRangeSlice(quarterDates, range);
        const labels = quarterLabels(quarterDates.slice(start, end));
        const datasets = qCountries.map(([country, arr], i) =>
          dataset(country, arr.slice(start, end), destColor(country, i), { stack: 'exports' })
        );
        // "Other" = total pork exports minus the named destinations, so the stack reaches the quarter total.
        const otherData = quarterDates.slice(start, end).map((q, idx) => {
          const total = qTotal[start + idx];
          if (total == null) return null;
          const named = qCountries.reduce((sum, [, arr]) => sum + (arr[start + idx] || 0), 0);
          return Math.max(0, total - named);
        });
        if (otherData.some(v => v != null)) {
          datasets.push(dataset('Other', otherData, '#c4ccd2', { stack: 'exports' }));
        }
        renderBarChart('exportDestinationsChart', labels, datasets, 'Million lb', {
          stacked: true,
          categoryX: true,
          yAxisWidth: 94,
          tooltip: {
            callbacks: {
              label(ctx) {
                const v = Number(ctx.parsed.y);
                if (!Number.isFinite(v)) return ctx.dataset.label || '';
                return `${ctx.dataset.label}: ${fmtNum(v, 1)}M`;
              },
              footer(items) {
                const total = items.reduce((sum, it) => sum + (Number(it.parsed.y) || 0), 0);
                return `Total exports: ${fmtNum(total, 1)}M lb`;
              }
            }
          }
        });
      }
    });
  } else {
    hideEmptyCard('exportDestinationsChart');
  }

  // US pork imports by source — monthly data aggregated into calendar quarters
  // (sum). "Other" = total pork imports minus named sources, so the stack totals.
  const importSources = trade.imports_by_source || {};
  if (importSources.dates?.length && Object.keys(importSources.series || {}).length) {
    const sources = Object.entries(importSources.series);
    const qRep = m => `${m.slice(0, 4)}-${String(Math.ceil(Number(m.slice(5, 7)) / 3) * 3).padStart(2, '0')}`;
    const qMonthCount = {};
    importSources.dates.forEach(m => { const q = qRep(m); qMonthCount[q] = (qMonthCount[q] || 0) + 1; });
    const quarterDates = [...new Set(importSources.dates.map(qRep))].sort();
    // Drop a trailing partial quarter (<3 months) so the last bar isn't undercounted.
    if (quarterDates.length && qMonthCount[quarterDates[quarterDates.length - 1]] < 3) quarterDates.pop();
    const qIndex = Object.fromEntries(quarterDates.map((q, i) => [q, i]));
    const qSeries = {};
    sources.forEach(([country, values]) => {
      const arr = quarterDates.map(() => null);
      importSources.dates.forEach((m, i) => {
        const v = values[i];
        if (v == null) return;
        const qi = qIndex[qRep(m)];
        if (qi != null) arr[qi] = (arr[qi] || 0) + v / 1000;
      });
      qSeries[country] = arr;
    });
    const qTotal = quarterDates.map(() => null);
    (totals.dates || []).forEach((m, i) => {
      const v = (totals.import_pork || [])[i];
      if (v == null) return;
      const qi = qIndex[qRep(m)];
      if (qi != null) qTotal[qi] = (qTotal[qi] || 0) + v / 1000;
    });
    registerRangeControl({
      chartId: 'importSourcesChart',
      options: ['1y', '3y', '5y', '10y', 'all'],
      defaultRange: '5y',
      renderer(range) {
        const { start, end } = quarterRangeSlice(quarterDates, range);
        const labels = quarterLabels(quarterDates.slice(start, end));
        const datasets = sources.map(([country], i) =>
          dataset(country, qSeries[country].slice(start, end), C.seq[i % C.seq.length], { stack: 'imports' })
        );
        const otherData = quarterDates.slice(start, end).map((q, idx) => {
          const total = qTotal[start + idx];
          if (total == null) return null;
          const named = sources.reduce((sum, [country]) => sum + (qSeries[country][start + idx] || 0), 0);
          return Math.max(0, total - named);
        });
        if (otherData.some(v => v != null)) {
          datasets.push(dataset('Other', otherData, '#c4ccd2', { stack: 'imports' }));
        }
        renderBarChart('importSourcesChart', labels, datasets, 'Million lb', {
          stacked: true,
          categoryX: true,
          tooltip: {
            callbacks: {
              label(ctx) {
                const v = Number(ctx.parsed.y);
                if (!Number.isFinite(v)) return ctx.dataset.label || '';
                return `${ctx.dataset.label}: ${fmtNum(v, 1)}M`;
              },
              footer(items) {
                const total = items.reduce((sum, it) => sum + (Number(it.parsed.y) || 0), 0);
                return `Total imports: ${fmtNum(total, 1)}M lb`;
              }
            }
          }
        });
      }
    });
  } else {
    hideEmptyCard('importSourcesChart');
  }


  // Brazil top export destinations (Comex Stat). The total export line itself is
  // overlaid on the Pork Exports vs. Imports chart above; here the same total
  // (brazilExportMap) backs the "Other" remainder so the stack reaches the total.
  const brazilDest = brazil.by_destination || {};
  if (brazilDest.dates?.length && Object.keys(brazilDest.series || {}).length) {
    const countries = Object.entries(brazilDest.series);
    // Aggregate monthly → calendar quarters (sum); values already in million lb.
    const qRep = m => `${m.slice(0, 4)}-${String(Math.ceil(Number(m.slice(5, 7)) / 3) * 3).padStart(2, '0')}`;
    const qMonthCount = {};
    brazilDest.dates.forEach(m => { const q = qRep(m); qMonthCount[q] = (qMonthCount[q] || 0) + 1; });
    const quarterDates = [...new Set(brazilDest.dates.map(qRep))].sort();
    if (quarterDates.length && qMonthCount[quarterDates[quarterDates.length - 1]] < 3) quarterDates.pop();
    const qIndex = Object.fromEntries(quarterDates.map((q, i) => [q, i]));
    const qCountries = countries.map(([country, values]) => {
      const arr = quarterDates.map(() => null);
      brazilDest.dates.forEach((m, i) => { const v = values[i]; if (v == null) return; const qi = qIndex[qRep(m)]; if (qi != null) arr[qi] = (arr[qi] || 0) + v; });
      return [country, arr];
    });
    const qTotal = quarterDates.map(() => null);
    Object.keys(brazilExportMap).forEach(m => { const v = brazilExportMap[m]; if (v == null) return; const qi = qIndex[qRep(m)]; if (qi != null) qTotal[qi] = (qTotal[qi] || 0) + v; });
    registerRangeControl({
      chartId: 'brazilDestinationsChart',
      options: ['5y', '10y', 'all'],
      defaultRange: '5y',
      renderer(range) {
        const { start, end } = quarterRangeSlice(quarterDates, range);
        const labels = quarterLabels(quarterDates.slice(start, end));
        const datasets = qCountries.map(([country, arr], i) =>
          dataset(country, arr.slice(start, end), destColor(country, i), { stack: 'brazil' })
        );
        const otherData = quarterDates.slice(start, end).map((q, idx) => {
          const total = qTotal[start + idx];
          if (total == null) return null;
          const named = qCountries.reduce((sum, [, arr]) => sum + (arr[start + idx] || 0), 0);
          return Math.max(0, total - named);
        });
        if (otherData.some(v => v != null)) {
          datasets.push(dataset('Other', otherData, '#c4ccd2', { stack: 'brazil' }));
        }
        renderBarChart('brazilDestinationsChart', labels, datasets, 'Million lb', {
          stacked: true,
          categoryX: true,
          yAxisWidth: 94,
          tooltip: {
            callbacks: {
              label(ctx) {
                const v = Number(ctx.parsed.y);
                if (!Number.isFinite(v)) return ctx.dataset.label || '';
                return `${ctx.dataset.label}: ${fmtNum(v, 1)}M`;
              },
              footer(items) {
                const total = items.reduce((sum, it) => sum + (Number(it.parsed.y) || 0), 0);
                return `Total exports: ${fmtNum(total, 1)}M lb`;
              }
            }
          }
        });
      }
    });
  } else {
    hideEmptyCard('brazilDestinationsChart');
  }

  // Monthly export comparison — US pork exports by calendar month, one line per year
  // (last N), with 2026 (yellow) and 2025 (orange) highlighted against gray history.
  if (totals.dates?.length && (totals.export_pork || []).some(v => v != null)) {
    const exportLb = (totals.export_pork || []).map(v => v != null ? v / 1000 : null);
    const ymMap = buildYearMonthMap(totals.dates, exportLb);
    const HILITE = { 2026: C.gold, 2025: C.orange };
    const YEARS_N = { '5y': 5, '10y': 10, all: 99 };
    registerRangeControl({
      chartId: 'exportComparisonChart',
      options: ['5y', '10y', 'all'],
      defaultRange: '10y',
      renderer(range) {
        const years = Object.keys(ymMap).map(Number).sort((a, b) => a - b).slice(-(YEARS_N[range] || 10));
        const grayYears = years.filter(y => !HILITE[y]);
        const grayLabel = grayYears.length ? `${grayYears[0]} – ${grayYears[grayYears.length - 1]}` : 'Prior years';
        const ordered = [...grayYears, ...years.filter(y => HILITE[y]).sort((a, b) => a - b)];
        const datasets = ordered.map(yr => dataset(String(yr), monthsForYear(ymMap, yr), HILITE[yr] || '#c4ccd2', {
          borderWidth: HILITE[yr] ? 4.2 : 1.4,
          order: HILITE[yr] ? (yr === 2026 ? 0 : 1) : 10,
          legendKey: HILITE[yr] ? undefined : 'historical',
          legendLabel: HILITE[yr] ? undefined : grayLabel
        }));
        renderLineChart('exportComparisonChart', MON_SHORT, datasets, 'Million lb', {
          categoryX: true,
          maxTicks: 12,
          tooltip: {
            itemSort(a, b) {
              return Number(b.dataset.label) - Number(a.dataset.label);
            },
            callbacks: {
              label(ctx) {
                const v = Number(ctx.parsed.y);
                if (!Number.isFinite(v)) return '';
                return `${ctx.dataset.label}: ${fmtNum(v, 0)}M lb`;
              }
            }
          }
        });
      }
    });
  } else {
    hideEmptyCard('exportComparisonChart');
  }

  // Top import cuts/products — US pork imports by product type (US Census,
  // product weight), stacked million lb per month.
  const usTrade = inventoryTrade.us_trade_product_weight || {};
  const importCuts = usTrade.import_by_cut || {};
  if (importCuts.dates?.length && Object.keys(importCuts.series || {}).length) {
    const cuts = Object.entries(importCuts.series);
    // Aggregate monthly → calendar quarters (sum) so it lines up with US Top Import Sources.
    const qRep = m => `${m.slice(0, 4)}-${String(Math.ceil(Number(m.slice(5, 7)) / 3) * 3).padStart(2, '0')}`;
    const qMonthCount = {};
    importCuts.dates.forEach(m => { const q = qRep(m); qMonthCount[q] = (qMonthCount[q] || 0) + 1; });
    const quarterDates = [...new Set(importCuts.dates.map(qRep))].sort();
    if (quarterDates.length && qMonthCount[quarterDates[quarterDates.length - 1]] < 3) quarterDates.pop();
    const qIndex = Object.fromEntries(quarterDates.map((q, i) => [q, i]));
    const qCuts = cuts.map(([cut, values]) => {
      const arr = quarterDates.map(() => null);
      importCuts.dates.forEach((m, i) => {
        const v = values[i];
        if (v == null) return;
        const qi = qIndex[qRep(m)];
        if (qi != null) arr[qi] = (arr[qi] || 0) + v;
      });
      return [cut, arr];
    });
    registerRangeControl({
      chartId: 'importCutsChart',
      options: ['1y', '3y', '5y', '10y', 'all'],
      defaultRange: '5y',
      renderer(range) {
        const { start, end } = quarterRangeSlice(quarterDates, range);
        const labels = quarterLabels(quarterDates.slice(start, end));
        const datasets = qCuts.map(([cut, arr], i) =>
          dataset(cut.replace(/\s*\(HS[^)]*\)/i, ''), arr.slice(start, end), C.seq[i % C.seq.length], { stack: 'cuts' })
        );
        renderBarChart('importCutsChart', labels, datasets, 'Million lb', {
          stacked: true,
          categoryX: true,
          tooltip: {
            callbacks: {
              label(ctx) {
                const v = Number(ctx.parsed.y);
                if (!Number.isFinite(v)) return ctx.dataset.label || '';
                return `${ctx.dataset.label}: ${fmtNum(v, 1)}M`;
              },
              footer(items) {
                const total = items.reduce((sum, it) => sum + (Number(it.parsed.y) || 0), 0);
                return `Total: ${fmtNum(total, 1)}M lb`;
              }
            }
          }
        });
      }
    });
  } else {
    hideEmptyCard('importCutsChart');
  }
}

// "Input Cost Price Changes" — ported from the egg chartbook. Lines show each
// input's % change from a user-chosen index date. Corn & soybean meal come from
// the shared CME feed sheet; diesel & electricity from FRED. (Paperboard removed,
// feed index split into corn + soy per request.)
function buildInputCostChart(inputIdx) {
  const ctx = document.getElementById('inputCostChart');
  if (!ctx) return;
  const iiDates = inputIdx.dates || [];
  if (!iiDates.length || !Object.keys(inputIdx.series || {}).length) {
    hideEmptyCard('inputCostChart');
    return;
  }
  const colorByLabel = {
    Corn: C.orange,
    'Soybean meal': C.teal,
    Diesel: C.navy,
    Electricity: C.gold
  };
  // Default the index date to the start of the feed window's first full year.
  const firstYear = parseInt(iiDates[0].slice(0, 4), 10);
  const picker = { month: `${firstYear + 1}-01` };
  if (!iiDates.some(d => d >= picker.month)) picker.month = iiDates[0];

  function rebaseAsChange(values, dates, baseMonth) {
    let baseVal = null;
    for (let i = 0; i < dates.length; i++) {
      if (String(dates[i]).startsWith(baseMonth) && values[i] != null) { baseVal = values[i]; break; }
    }
    if (!baseVal) {
      for (let i = 0; i < dates.length; i++) { if (values[i] != null) { baseVal = values[i]; break; } }
    }
    if (!baseVal) return values;
    return values.map(v => v != null ? Math.round((v / baseVal - 1) * 100 * 100) / 100 : null);
  }

  const endLabelPlugin = {
    id: 'inputCostEndLabels',
    afterDatasetsDraw(chart) {
      const MIN_GAP = 13;
      const items = [];
      chart.data.datasets.forEach((ds, dsIdx) => {
        const meta = chart.getDatasetMeta(dsIdx);
        if (meta.hidden) return;
        let lastIdx = -1;
        for (let i = ds.data.length - 1; i >= 0; i--) { if (ds.data[i] != null) { lastIdx = i; break; } }
        if (lastIdx === -1) return;
        const pt = meta.data[lastIdx];
        if (!pt) return;
        const v = ds.data[lastIdx];
        items.push({ text: (v > 0 ? '+' : '') + v.toFixed(1) + '%', color: ds.borderColor || '#013046', x: pt.x, drawY: pt.y });
      });
      items.sort((a, b) => a.drawY - b.drawY);
      for (let i = 1; i < items.length; i++) {
        const overlap = items[i - 1].drawY + MIN_GAP - items[i].drawY;
        if (overlap > 0) { items[i - 1].drawY -= overlap / 2; items[i].drawY += overlap / 2; }
      }
      for (let i = 1; i < items.length; i++) {
        const overlap = items[i - 1].drawY + MIN_GAP - items[i].drawY;
        if (overlap > 0) items[i].drawY = items[i - 1].drawY + MIN_GAP;
      }
      const c = chart.ctx;
      c.save();
      c.font = 'bold 11px Lexend, sans-serif';
      c.textBaseline = 'middle';
      c.textAlign = 'left';
      c.strokeStyle = '#faf8f5';
      c.lineWidth = 4;
      c.lineJoin = 'round';
      items.forEach(item => c.strokeText(item.text, item.x + 6, item.drawY));
      items.forEach(item => { c.fillStyle = item.color; c.fillText(item.text, item.x + 6, item.drawY); });
      c.restore();
    }
  };

  function render() {
    const baseMonth = picker.month;
    let startIdx = 0;
    for (let i = 0; i < iiDates.length; i++) { if (iiDates[i] >= baseMonth) { startIdx = i; break; } }
    const slicedDates = iiDates.slice(startIdx);
    destroyChart('inputCostChart');
    const datasets = Object.keys(inputIdx.series).map(label => {
      const raw = inputIdx.series[label].slice(startIdx);
      const rebased = rebaseAsChange(raw, slicedDates, baseMonth);
      return dataset(label, rebased, colorByLabel[label] || C.slate);
    });
    const opts = baseOptions('% change vs index date', {
      chartId: 'inputCostChart',
      aspect: 2.2,
      tooltip: {
        callbacks: {
          label(context) {
            const v = context.parsed?.y;
            if (v == null || !Number.isFinite(v)) return context.dataset?.label || '';
            return `${context.dataset?.label ? context.dataset.label + ': ' : ''}${v > 0 ? '+' : ''}${v.toFixed(1)}%`;
          }
        }
      }
    });
    opts.layout.padding.right = 62;
    charts['inputCostChart'] = new Chart(ctx, {
      type: 'line',
      data: { labels: slicedDates, datasets },
      options: opts,
      plugins: [endLabelPlugin]
    });
  }

  // No range buttons — just the toolbar/legend, with an index-date picker.
  registerRangeControl({ chartId: 'inputCostChart', options: [], renderer: render });

  const toolbar = document.querySelector('.chart-toolbar[data-chart="inputCostChart"]');
  if (toolbar && !toolbar.querySelector('.base-month-control')) {
    const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const minYear = firstYear;
    const maxYear = parseInt(iiDates[iiDates.length - 1].slice(0, 4), 10);
    const wrap = document.createElement('div');
    wrap.className = 'base-month-control';
    const label = document.createElement('span');
    label.className = 'base-month-label';
    label.textContent = 'Index date:';
    const monthSel = document.createElement('select');
    monthSel.className = 'base-month-select';
    MONTH_NAMES.forEach((name, i) => {
      const opt = document.createElement('option');
      opt.value = String(i + 1).padStart(2, '0');
      opt.textContent = name;
      monthSel.appendChild(opt);
    });
    const yearSel = document.createElement('select');
    yearSel.className = 'base-month-select';
    for (let y = maxYear; y >= minYear; y--) {
      const opt = document.createElement('option');
      opt.value = String(y);
      opt.textContent = String(y);
      yearSel.appendChild(opt);
    }
    monthSel.value = picker.month.slice(5, 7);
    yearSel.value = picker.month.slice(0, 4);
    wrap.appendChild(label);
    wrap.appendChild(monthSel);
    wrap.appendChild(yearSel);
    toolbar.insertBefore(wrap, toolbar.querySelector('.chart-legend'));
    const onChange = () => { picker.month = `${yearSel.value}-${monthSel.value}`; render(); };
    monthSel.addEventListener('change', onChange);
    yearSel.addEventListener('change', onChange);
  }
}

function buildCostsRisk(costs) {
  buildInputCostChart(costs.input_indices || {});

  // Cost of soybean meal and corn — daily CME prices ($/ton) from the feed sheet.
  const corn = costs.corn_price, soy = costs.soybean_meal_price;
  const feedUnit = costs.corn_soy_price_unit || '$/ton';
  if (seriesHasData(corn) || seriesHasData(soy)) {
    const dates = [...new Set([...(corn?.dates || []), ...(soy?.dates || [])])].sort();
    const cMap = Object.fromEntries((corn?.dates || []).map((d, i) => [d, corn.values[i]]));
    const sMap = Object.fromEntries((soy?.dates || []).map((d, i) => [d, soy.values[i]]));
    registerRangeControl({
      chartId: 'feedPriceChart',
      options: ['1y', '2y', '5y', '10y', 'all'],
      defaultRange: '5y',
      renderer(range) {
        const { start, end } = getRangeSlice(dates, range);
        const labels = dates.slice(start, end);
        // One shared $/ton axis: corn is always cheaper than soybean meal, so the
        // lines sit in separate bands (corn below, soy above) without overlapping.
        renderLineChart('feedPriceChart', labels, [
          dataset('Corn', labels.map(d => cMap[d] != null ? cMap[d] : null), C.gold),
          dataset('Soybean meal', labels.map(d => sMap[d] != null ? sMap[d] : null), C.teal),
        ], feedUnit);
      }
    });
  } else {
    hideEmptyCard('feedPriceChart');
  }
}

// Farm-to-wholesale-to-retail price spread — "where the retail pork dollar goes".
// Stacked area on a common retail-weight $/lb basis: net farm value (producer) +
// farm-to-wholesale spread (packer/processor) + wholesale-to-retail spread
// (retailer) sum to the retail price. USDA ERS Meat Price Spreads, monthly.
function buildPriceSpread(ps) {
  const chartId = 'spreadDollarChart';
  const farm = ps && ps.net_farm_value;
  const fw = ps && ps.farm_to_wholesale_spread;
  const wr = ps && ps.wholesale_to_retail_spread;
  if (!seriesHasData(farm) || !seriesHasData(fw) || !seriesHasData(wr)) {
    hideEmptyCard(chartId);
    return;
  }
  const dates = [...new Set([...(farm.dates || []), ...(fw.dates || []), ...(wr.dates || [])])]
    .filter(d => d >= '2000').sort();
  const mk = s => Object.fromEntries((s?.dates || []).map((d, i) => [d, s.values[i]]));
  const farmMap = mk(farm), fwMap = mk(fw), wrMap = mk(wr);
  const N = { '5y': 60, '10y': 120, all: 9999 };
  // Translucent fills so the stack reads as bands; keep a thin matching border.
  const band = (color, alpha) => ({
    fill: true,
    backgroundColor: `${color}${alpha}`,
    borderColor: color,
    borderWidth: 1.6,
    tension: 0.1,
  });
  registerRangeControl({
    chartId,
    options: ['5y', '10y', 'all'],
    defaultRange: '10y',
    renderer(range) {
      const labels = dates.slice(-(N[range] || 120));
      renderLineChart(chartId, labels, [
        dataset('Net farm value (producer)', labels.map(d => farmMap[d] ?? null), C.navy,
          Object.assign({ fill: 'origin' }, band(C.navy, '66'))),
        dataset('Farm-to-wholesale spread (packer)', labels.map(d => fwMap[d] ?? null), C.teal,
          Object.assign({ fill: '-1' }, band(C.teal, '66'))),
        dataset('Wholesale-to-retail spread (retailer)', labels.map(d => wrMap[d] ?? null), C.gold,
          Object.assign({ fill: '-1' }, band(C.gold, '88'))),
      ], '$ / lb (retail weight)', {
        stacked: true,
        yMin: 0,
        tooltip: {
          callbacks: {
            label(ctx) {
              const v = Number(ctx.parsed.y);
              if (!Number.isFinite(v)) return ctx.dataset.label || '';
              return `${ctx.dataset.label}: $${fmtNum(v, 2)}`;
            },
            footer(items) {
              const total = items.reduce((sum, it) => sum + (Number(it.parsed.y) || 0), 0);
              return `Retail price: $${fmtNum(total, 2)} / lb`;
            }
          }
        }
      });
    }
  });
}

// Google Apps Script web-app endpoint backing the signup form. The body is sent
// as a JSON string with NO Content-Type header so it stays a "simple" CORS
// request (no preflight) — Apps Script reads it via e.postData.contents.
const SIGNUP_ENDPOINT = 'https://script.google.com/macros/s/AKfycbyNVCUxSU6np6gCp9OgQPst3uxhSyvuC1dzUEEj3iVC1oz4yjB7ZOfvA2KlPsHMJ3U/exec';

function initMonthlySignup(data) {
  const form = document.getElementById('dashboardSignupForm');
  const status = document.getElementById('dashboardSignupStatus');
  if (!form || !status) return;

  const setStatus = text => { status.textContent = text || ''; };
  Array.from(form.querySelectorAll('input')).forEach(input =>
    input.addEventListener('input', () => setStatus('')));

  form.addEventListener('submit', event => {
    event.preventDefault();
    if (!form.reportValidity()) return;

    const payload = {
      firstName: form.elements.first_name?.value?.trim() || '',
      lastName: form.elements.last_name?.value?.trim() || '',
      email: form.elements.email?.value?.trim() || '',
      company: form.elements.company?.value?.trim() || '',
      role: form.elements.role?.value?.trim() || '',
    };

    const submitBtn = form.querySelector('button[type="submit"]');
    if (submitBtn) submitBtn.disabled = true;
    setStatus('Submitting…');

    fetch(SIGNUP_ENDPOINT, { method: 'POST', body: JSON.stringify(payload) })
      .then(response => {
        if (!response.ok) throw new Error('Network error');
        setStatus('Thank you! You are on the pork chartbook update list.');
        form.reset();
      })
      .catch(() => setStatus('Something went wrong. Please try again.'))
      .finally(() => { if (submitBtn) submitBtn.disabled = false; });
  });
}

// WASDE forecast bars — production, exports, hog price. Each marketing year is
// a single bar; the most recent actual (estimate) is grey and the projections
// are coloured, split into two datasets so the legend reads Estimate / Forecast.
function buildExportShareByCountry(world) {
  const chartId = 'exportShareCountriesChart';
  if (!world || !world.export_share || !(world.years || []).length) { hideEmptyCard(chartId); return; }
  const years = world.years.map(String);
  // US and Brazil keep the same colors as the "Pork Exports: US vs. Brazil"
  // chart (US teal, Brazil navy); other regions use distinct colors.
  const picks = [
    ['United States', C.teal],
    ['European Union', C.orange],
    ['Brazil', C.navy],
    ['Canada', C.gold],
  ].filter(([c]) => world.export_share[c]);
  const N = { '10y': 10, all: 9999 };
  registerRangeControl({
    chartId,
    options: ['10y', 'all'],
    defaultRange: 'all',
    renderer(range) {
      const idx0 = Math.max(0, years.length - (N[range] || 9999));
      const labels = years.slice(idx0);
      const datasets = picks.map(([c, color]) =>
        dataset(c, world.export_share[c].slice(idx0), color, { pointRadius: 0 })
      );
      renderLineChart(chartId, labels, datasets, '% of production exported', {
        categoryX: true, maxTicks: 12,
        tooltip: {
          callbacks: {
            label(ctx) {
              const v = Number(ctx.parsed.y);
              if (!Number.isFinite(v)) return '';
              return `${ctx.dataset.label}: ${fmtNum(v, 1)}%`;
            }
          }
        }
      });
    }
  });
}

function buildForecasts(data) {
  const forecasts = data.forecasts || {};
  // Quarterly line: long actuals history spliced with the WASDE quarterly forecast.
  // Solid through Q2 2026 (actual/estimate), dotted from Q3 2026 (forecast), same colour.
  const CUT = '2026-Q2';
  const qOf = ym => `${ym.slice(0, 4)}-Q${Math.ceil(Number(ym.slice(5, 7)) / 3)}`;
  const qLabel = q => { const p = q.split('-'); return `${p[1]} ${p[0]}`; };
  const quarterlyActuals = (series, scale, agg) => {
    const b = {};
    ((series && series.dates) || []).forEach((d, i) => {
      const v = series.values[i];
      if (v == null) return;
      const q = qOf(d);
      (b[q] = b[q] || { s: 0, n: 0, m: new Set() });
      b[q].s += v; b[q].n += 1; b[q].m.add(d.slice(0, 7));
    });
    const out = {};
    Object.keys(b).forEach(q => { if (b[q].m.size >= 3) out[q] = (agg === 'avg' ? b[q].s / b[q].n : b[q].s) / scale; });
    return out;
  };
  const Q_PER_RANGE = { '3y': 12, '5y': 20, '10y': 40 };
  const renderForecast = (chartId, actualsQ, wasde, yLabel, name, color, digits, opts) => {
    opts = opts || {};
    const fcLabel = opts.fcLabel || 'Forecast';
    const wq = (wasde && wasde.quarters) || [], wv = (wasde && wasde.quarter_values) || [];
    const wMap = {}; wq.forEach((q, i) => { wMap[q] = wv[i]; });
    let allQ = [...new Set([...Object.keys(actualsQ), ...wq])].sort();
    if (opts.minYear) allQ = allQ.filter(q => Number(q.slice(0, 4)) >= opts.minYear);
    if (!allQ.length) { hideEmptyCard(chartId); return; }
    const val = q => actualsQ[q] != null ? actualsQ[q] : (wMap[q] != null ? wMap[q] : null);
    const solidF = allQ.map(q => q <= CUT ? val(q) : null);
    const dottedF = allQ.map(q => q >= CUT ? val(q) : null);
    const labelsF = allQ.map(qLabel);
    registerRangeControl({
      chartId,
      options: opts.ranges || [],
      defaultRange: opts.defaultRange,
      renderer(range) {
        const n = (range && Q_PER_RANGE[range]) ? Math.min(Q_PER_RANGE[range], labelsF.length) : labelsF.length;
        const sl = a => a.slice(-n);
        renderLineChart(chartId, sl(labelsF), [
          dataset(name, sl(solidF), color, { pointRadius: 0, legendKey: 'fc', legendLabel: name }),
          dataset(fcLabel, sl(dottedF), color, { pointRadius: 0, borderDash: [5, 4], legendKey: 'fc', legendLabel: name }),
        ], yLabel, {
          categoryX: true, maxTicks: 12, xRotation: 45,
          tooltip: {
            callbacks: {
              label(ctx) {
                const v = Number(ctx.parsed.y);
                if (!Number.isFinite(v)) return '';
                return `${ctx.dataset.label}: ${fmtNum(v, digits)} ${yLabel}`;
              }
            }
          }
        });
      }
    });
  };
  const FC_RANGES = { ranges: ['3y', '5y', '10y', 'all'], defaultRange: '5y' };

  renderForecast('forecastProductionChart',
    quarterlyActuals((data.slaughter_production || {}).nass_pork_production, 1e6, 'sum'),
    forecasts.production, 'Million lb', 'Commercial pork production', C.navy, 0, FC_RANGES);
  renderForecast('forecastPriceChart',
    quarterlyActuals((data.prices || {}).barrow_gilt_net_price, 1, 'avg'),
    forecasts.hog_price, '$/cwt', 'Hog price (barrows & gilts)', C.navy, 1,
    Object.assign({ minYear: 2006 }, FC_RANGES));

  // Exports — WASDE forecasts exports annually only, so build quarterly actuals and
  // split the WASDE annual forecast across quarters by the recent seasonal pattern
  // (an estimate, labelled as such).
  const ex = forecasts.exports;
  const tt = ((data.inventory_trade || {}).trade || {}).trade_totals;
  const exActualsQ = quarterlyActuals(tt ? { dates: tt.dates, values: tt.export_pork } : null, 1000, 'sum');
  if (ex && (ex.values || []).some(v => v != null) && Object.keys(exActualsQ).length) {
    // Recent-5-year average seasonal shares (each calendar quarter's share of its year).
    const byYear = {};
    Object.keys(exActualsQ).forEach(q => { const p = q.split('-'); (byYear[p[0]] = byYear[p[0]] || {})[p[1]] = exActualsQ[q]; });
    const complete = Object.keys(byYear).filter(y => Object.keys(byYear[y]).length === 4).sort().slice(-5);
    const sum = { Q1: 0, Q2: 0, Q3: 0, Q4: 0 }; let nY = 0;
    complete.forEach(y => {
      const yr = byYear[y], tot = yr.Q1 + yr.Q2 + yr.Q3 + yr.Q4;
      if (tot > 0) { ['Q1', 'Q2', 'Q3', 'Q4'].forEach(qq => { sum[qq] += yr[qq] / tot; }); nY++; }
    });
    const share = nY ? { Q1: sum.Q1 / nY, Q2: sum.Q2 / nY, Q3: sum.Q3 / nY, Q4: sum.Q4 / nY } : { Q1: .25, Q2: .25, Q3: .25, Q4: .25 };
    const annual = {}; (ex.years || []).forEach((y, i) => { annual[y] = ex.values[i]; });
    const synthQ = [], synthV = [];
    ['2026', '2027'].forEach(y => {
      if (annual[y] == null) return;
      ['Q1', 'Q2', 'Q3', 'Q4'].forEach(qq => { synthQ.push(`${y}-${qq}`); synthV.push(annual[y] * share[qq]); });
    });
    renderForecast('forecastExportsChart', exActualsQ, { quarters: synthQ, quarter_values: synthV },
      'Million lb', 'Pork exports', C.teal, 0,
      Object.assign({ fcLabel: 'Forecast (est.)', minYear: 2006 }, FC_RANGES));
  } else {
    hideEmptyCard('forecastExportsChart');
  }
}

async function loadPorkDashboard() {
  try {
    const resp = await fetch('data.json?v=' + Date.now());
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();

    if (data.meta?.updated) {
      porkText('dashFooter', `Pork chartbook updated ${data.meta.updated}. Sources: USDA NASS · USDA AMS · USDA ERS · FRED · Brazil Comex Stat.`);
    }

    buildHerd(data.herd_supply || data.herd || {});
    buildSlaughterProduction(data.slaughter_production || {});
    buildNassSlaughter(data.slaughter_production || {});
    buildPrices(data.prices || {});
    buildRetailDemand(data.retail_demand || {});
    buildInventoryTrade(data.inventory_trade || { trade: data.trade || {} });
    buildCostsRisk(data.costs_risk || {});
    buildPriceSpread(data.price_spreads || {});
    buildForecasts(data);
    buildExportShareByCountry(data.world_psd || {});
    initMonthlySignup(data);

    setPorkChartSources();
    initPorkSidebarNav();
  } catch (err) {
    const shell = document.querySelector('.dashboard-content');
    if (shell) {
      const banner = document.createElement('div');
      banner.style.cssText = 'padding:2rem;color:#c53030;font-size:.9rem';
      banner.textContent = 'Could not load dashboard data: ' + err.message +
        '. If running locally, serve with: python3 -m http.server 8000';
      shell.prepend(banner);
    }
  }
}

loadPorkDashboard();
