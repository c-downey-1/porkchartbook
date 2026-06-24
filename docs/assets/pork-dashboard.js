/* pork-dashboard.js - uses helpers from dashboard-common.js */

const C = DASH_COLORS;

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

  const srcMap = {
    herdBreedingMarketChart: `Chart: Innovate Animal Ag • Source: ${nass}`,
    marketWeightChart: `Chart: Innovate Animal Ag • Source: ${nass}`,
    sowsFarrowedChart: `Chart: Innovate Animal Ag • Source: ${nass}`,
    pigsPerLitterChart: `Chart: Innovate Animal Ag • Source: ${nass}`,
    herdPigCropChart: `Chart: Innovate Animal Ag • Source: ${nass}`,
    slaughterHeadChart: `Chart: Innovate Animal Ag • Source: ${amsHg}`,
    porkProductionChart: `Chart: Innovate Animal Ag • Source: ${amsHg}`,
    carcassWeightChart: `Chart: Innovate Animal Ag • Source: ${amsHg}`,
    commercialSlaughterChart: `Chart: Innovate Animal Ag • Source: ${nass}`,
    commercialProductionChart: `Chart: Innovate Animal Ag • Source: ${nass}`,
    productionSeasonalChart: `Chart: Innovate Animal Ag • Source: ${nass}`,
    avgWeightChart: `Chart: Innovate Animal Ag • Source: ${nass}`,
    sowSlaughterChart: `Chart: Innovate Animal Ag • Source: ${nass}`,
    hogPriceChart: `Chart: Innovate Animal Ag • Source: ${amsHg}`,
    cutoutChart: `Chart: Innovate Animal Ag • Source: ${amsPk}`,
    hogCutoutSpreadChart: `Chart: Innovate Animal Ag • Source: ${amsHg} / ${amsPk}`,
    primalsChart: `Chart: Innovate Animal Ag • Source: ${amsPk}`,
    retailFeatureChart: `Chart: Innovate Animal Ag • Source: ${amsRetail}`,
    retailPriceChart: `Chart: Innovate Animal Ag • Source: ${amsRetail} / ${fred}`,
    coldStorageChart: `Chart: Innovate Animal Ag • Source: ${nass}`,
    tradeFlowChart: `Chart: Innovate Animal Ag • Source: ${ers} / ${comex}`,
    exportDestinationsChart: `Chart: Innovate Animal Ag • Source: ${ers}`,
    importSourcesChart: `Chart: Innovate Animal Ag • Source: ${ers}`,
    exportComparisonChart: `Chart: Innovate Animal Ag • Source: ${ers}`,
    exportShareChart: `Chart: Innovate Animal Ag • Source: ${ers} / ${nass}`,
    brazilDestinationsChart: `Chart: Innovate Animal Ag • Source: ${comex}`,
    inputCostChart: `Chart: Innovate Animal Ag • Sources: <a href="https://www.cmegroup.com/markets/agriculture.html" target="_blank" rel="noreferrer">CME Group</a> · <a href="https://fred.stlouisfed.org/series/GASDESW" target="_blank" rel="noreferrer">FRED GASDESW</a> · <a href="https://fred.stlouisfed.org/series/APU000072610" target="_blank" rel="noreferrer">FRED APU000072610</a>`,
    monthlyMarginChart: `Chart: Innovate Animal Ag • Source: ${amsHg} / ${amsPk}`,
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

  const observer = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        groups.forEach(group => group.classList.toggle('is-active', group.dataset.section === entry.target.id));
      }
    });
  }, { threshold: 0.2 });
  sections.forEach(section => observer.observe(section));
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
      options: ['5y', '10y', 'all'],
      defaultRange: '10y',
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
          { categoryX: true, maxTicks: 10 }
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
      options: ['5y', '10y', 'all'],
      defaultRange: '10y',
      renderer(range) {
        const { start, end } = getRangeSlice(sows.dates, range);
        renderLineChart(
          'sowsFarrowedChart',
          sows.dates.slice(start, end),
          [dataset('Sows farrowed', toMillions(sows.values.slice(start, end)), C.navy)],
          'Million head'
        );
      }
    });
  } else {
    hideEmptyCard('sowsFarrowedChart');
  }

  const litter = herd.pigs_per_litter;
  if (seriesHasData(litter)) {
    registerRangeControl({
      chartId: 'pigsPerLitterChart',
      options: ['5y', '10y', 'all'],
      defaultRange: '10y',
      renderer(range) {
        const { start, end } = getRangeSlice(litter.dates, range);
        renderLineChart(
          'pigsPerLitterChart',
          litter.dates.slice(start, end),
          [dataset('Pigs per litter', litter.values.slice(start, end), C.gold, { fill: true, backgroundColor: 'rgba(253,183,20,0.10)' })],
          'Pigs per litter'
        );
      }
    });
  } else {
    hideEmptyCard('pigsPerLitterChart');
  }

  const pigCrop = herd.pig_crop;
  if (seriesHasData(pigCrop)) {
    registerRangeControl({
      chartId: 'herdPigCropChart',
      options: ['3y', '5y', '10y', 'all'],
      defaultRange: '5y',
      renderer(range) {
        const { start, end } = getRangeSlice(pigCrop.dates, range);
        const values = toMillions(pigCrop.values.slice(start, end));
        // Pig crop sits in a high, narrow band; anchor the axis near the visible
        // range so period-to-period changes stand out instead of looking flat.
        const present = values.filter(v => v != null);
        const lo = present.length ? Math.min(...present) : 0;
        const hi = present.length ? Math.max(...present) : 1;
        const pad = Math.max(0.2, (hi - lo) * 0.2);
        renderBarChart(
          'herdPigCropChart',
          pigCrop.dates.slice(start, end),
          [dataset('Pig crop', values, C.gold)],
          'Million head',
          { yMin: Math.floor(lo - pad), yMax: Math.ceil(hi + pad) }
        );
      }
    });
  } else {
    hideEmptyCard('herdPigCropChart');
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
      defaultRange: '5y',
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

  // Commercial pork production (carcass weight).
  const production = sp.nass_pork_production;
  if (seriesHasData(production)) {
    registerRangeControl({
      chartId: 'commercialProductionChart',
      options: ['1y', '2y', '5y', '10y', 'all'],
      defaultRange: '5y',
      renderer(range) {
        const { start, end } = getRangeSlice(production.dates, range);
        renderBarChart(
          'commercialProductionChart',
          production.dates.slice(start, end),
          [dataset('Commercial pork production', toMillions(production.values.slice(start, end)), C.navy)],
          'Million lb',
          { yAxisWidth: 94 }
        );
      }
    });
  } else {
    hideEmptyCard('commercialProductionChart');
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

  // Average live & dressed (carcass) weight.
  const live = sp.nass_live_weight;
  const dressed = sp.nass_dressed_weight;
  if (seriesHasData(live) || seriesHasData(dressed)) {
    const dates = [...new Set([...(live?.dates || []), ...(dressed?.dates || [])])].sort();
    const liveMap = Object.fromEntries((live?.dates || []).map((d, i) => [d, live.values[i]]));
    const dressedMap = Object.fromEntries((dressed?.dates || []).map((d, i) => [d, dressed.values[i]]));
    registerRangeControl({
      chartId: 'avgWeightChart',
      options: ['1y', '2y', '3y', '5y', '10y', 'all'],
      defaultRange: '5y',
      renderer(range) {
        const { start, end } = getRangeSlice(dates, range);
        const labels = dates.slice(start, end);
        // Stack dressed weight + the live-minus-dressed remainder so the bar totals
        // average live weight (i.e. dressed carcass sits "inside" live weight).
        const dressedVals = labels.map(d => dressedMap[d] ?? null);
        const diffVals = labels.map(d => {
          const l = liveMap[d], dr = dressedMap[d];
          return (l != null && dr != null) ? Math.max(0, l - dr) : null;
        });
        // Anchor the y-axis near the data band instead of zero so month-to-month
        // weight changes are legible — a 0-based stack flattens the ~210-290 lb
        // range into a near-flat block. Floor sits below the min dressed weight
        // (the bottom segment, so it never clips) and the cap above max live
        // weight (the top of the stack).
        const floorVals = dressedVals.filter(v => v != null);
        const topVals = labels.map(d => liveMap[d] ?? dressedMap[d]).filter(v => v != null);
        let yMin, yMax;
        if (floorVals.length && topVals.length) {
          const lo = Math.min(...floorVals);
          const hi = Math.max(...topVals);
          const pad = Math.max(1, (hi - lo) * 0.15);
          yMin = Math.floor(lo - pad);
          yMax = Math.ceil(hi + pad);
        }
        renderBarChart(
          'avgWeightChart',
          labels,
          [
            dataset('Avg dressed weight', dressedVals, C.navy, { stack: 'wt' }),
            dataset('Live weight', diffVals, C.sky, { stack: 'wt' }),
          ],
          'Pounds',
          {
            stacked: true,
            yMin, yMax,
            tooltip: {
              callbacks: {
                label(ctx) {
                  // The top segment is stacked as (live − dressed) so the bar height
                  // equals live weight — but on hover show the actual live weight value.
                  if (ctx.dataset.label === 'Live weight') {
                    const liveVal = liveMap[ctx.label];
                    return liveVal != null ? `Live weight: ${fmtNum(liveVal, 0)} lb` : '';
                  }
                  const v = Number(ctx.parsed.y);
                  if (!Number.isFinite(v)) return ctx.dataset.label || '';
                  return `${ctx.dataset.label}: ${fmtNum(v, 0)} lb`;
                },
                footer(items) {
                  const total = items.reduce((sum, it) => sum + (Number(it.parsed.y) || 0), 0);
                  return `Total: ${fmtNum(total, 0)} lb`;
                }
              }
            }
          }
        );
      }
    });
  } else {
    hideEmptyCard('avgWeightChart');
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
            dataset('Sows', labels.map(d => sowsMap[d] != null ? sowsMap[d] / 1e3 : null), C.orange),
            dataset('Boars', labels.map(d => boarsMap[d] != null ? boarsMap[d] / 1e3 : null), C.slate),
          ],
          'Thousand head',
          {
            tooltip: {
              callbacks: {
                label(ctx) {
                  const v = Number(ctx.parsed.y);
                  if (!Number.isFinite(v)) return ctx.dataset.label || '';
                  return `${ctx.dataset.label}: ${fmtNum(v, 1)}k`;
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
      defaultRange: HF_DEFAULT,
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
      options: HF_OPTIONS_EXT,
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

  const spread = prices.cutout_net_spread || prices.cutout_base_spread;
  if (seriesHasData(spread)) {
    registerRangeControl({
      chartId: 'hogCutoutSpreadChart',
      options: HF_OPTIONS,
      defaultRange: HF_DEFAULT,
      renderer(range) {
        renderHfLine('hogCutoutSpreadChart', [
          { label: 'Cutout less net hog price', series: spread, color: C.orange, extra: { fill: true, backgroundColor: 'rgba(246,133,31,0.10)' } },
        ], '$/cwt', range);
      }
    });
  } else {
    hideEmptyCard('hogCutoutSpreadChart');
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
      options: ['3m', '6m', '1y', '2y', '3y', '5y', 'all'],
      defaultRange: '2y',
      renderer(range) {
        const { start, end } = getRangeSlice(dates, range);
        const labels = dates.slice(start, end);
        renderLineChart(
          'retailFeatureChart',
          labels,
          [
            dataset('Feature rate', labels.map(d => featureMap[d] ?? null), C.teal),
            dataset('Activity index', labels.map(d => activityMap[d] ?? null), C.gold, { yAxisID: 'y2' }),
          ],
          'Feature rate',
          { y2: 'Activity index', aspect: 2.6 }
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
      options: ['6m', '1y', '2y', '3y', '5y', 'all'],
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
      defaultRange: '5y',
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
  if (totals.dates?.length) {
    registerRangeControl({
      chartId: 'tradeFlowChart',
      options: ['3y', '5y', '10y', 'all'],
      defaultRange: '5y',
      renderer(range) {
        const { start, end } = getRangeSlice(totals.dates, range);
        const labels = totals.dates.slice(start, end);
        renderLineChart(
          'tradeFlowChart',
          labels,
          [
            dataset('US Pork Exports (carcass weight)', (totals.export_pork || []).slice(start, end).map(v => v != null ? v / 1000 : null), C.teal),
            dataset('Brazil Exports (Product weight)', labels.map(d => brazilExportMap[d] ?? null), C.navy),
          ],
          'Million lb',
          { aspect: 2.6 }
        );
      }
    });
  } else {
    hideEmptyCard('tradeFlowChart');
  }

  const exports = trade.exports_by_destination || {};
  if (exports.dates?.length && Object.keys(exports.series || {}).length) {
    const countries = Object.entries(exports.series);
    const exportTotalMap = {};
    (totals.dates || []).forEach((d, i) => {
      const v = (totals.export_pork || [])[i];
      if (v != null) exportTotalMap[d] = v / 1000;
    });
    registerRangeControl({
      chartId: 'exportDestinationsChart',
      options: ['1y', '3y', '5y', '10y', 'all'],
      defaultRange: '5y',
      renderer(range) {
        const { start, end } = getRangeSlice(exports.dates, range);
        const labels = exports.dates.slice(start, end);
        const datasets = countries.map(([country, values], i) =>
          dataset(country, values.slice(start, end).map(v => v != null ? v / 1000 : null), C.seq[i % C.seq.length], { stack: 'exports' })
        );
        // "Other" = total pork exports minus the named destinations, so the stack reaches the monthly total.
        const otherData = labels.map((d, idx) => {
          const total = exportTotalMap[d];
          if (total == null) return null;
          const named = countries.reduce((sum, [, values]) => {
            const v = values[start + idx];
            return sum + (v != null ? v / 1000 : 0);
          }, 0);
          return Math.max(0, total - named);
        });
        if (otherData.some(v => v != null)) {
          datasets.push(dataset('Other', otherData, '#c4ccd2', { stack: 'exports' }));
        }
        renderBarChart('exportDestinationsChart', labels, datasets, 'Million lb', {
          stacked: true,
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

  // US pork imports by source — mirrors the export-destinations chart. "Other" =
  // total pork imports minus the named sources, so the stack reaches the total.
  const importSources = trade.imports_by_source || {};
  if (importSources.dates?.length && Object.keys(importSources.series || {}).length) {
    const sources = Object.entries(importSources.series);
    const importTotalMap = {};
    (totals.dates || []).forEach((d, i) => {
      const v = (totals.import_pork || [])[i];
      if (v != null) importTotalMap[d] = v / 1000;
    });
    registerRangeControl({
      chartId: 'importSourcesChart',
      options: ['1y', '3y', '5y', '10y', 'all'],
      defaultRange: '5y',
      renderer(range) {
        const { start, end } = getRangeSlice(importSources.dates, range);
        const labels = importSources.dates.slice(start, end);
        const datasets = sources.map(([country, values], i) =>
          dataset(country, values.slice(start, end).map(v => v != null ? v / 1000 : null), C.seq[i % C.seq.length], { stack: 'imports' })
        );
        const otherData = labels.map((d, idx) => {
          const total = importTotalMap[d];
          if (total == null) return null;
          const named = sources.reduce((sum, [, values]) => {
            const v = values[start + idx];
            return sum + (v != null ? v / 1000 : 0);
          }, 0);
          return Math.max(0, total - named);
        });
        if (otherData.some(v => v != null)) {
          datasets.push(dataset('Other', otherData, '#c4ccd2', { stack: 'imports' }));
        }
        renderBarChart('importSourcesChart', labels, datasets, 'Million lb', {
          stacked: true,
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

  const share = inventoryTrade.export_share_of_production;
  if (seriesHasData(share)) {
    // 12-month rolling average over the full series so each range window keeps its trailing-year context.
    const shareRolling = rollingAverage(share.values, 12);
    registerRangeControl({
      chartId: 'exportShareChart',
      options: ['3y', '5y', '10y', 'all'],
      defaultRange: 'all',
      renderer(range) {
        const { start, end } = getRangeSlice(share.dates, range);
        renderLineChart(
          'exportShareChart',
          share.dates.slice(start, end),
          [dataset('Exports as share of production (12-mo avg)', shareRolling.slice(start, end), C.orange, { fill: true, backgroundColor: 'rgba(246,133,31,0.10)' })],
          '%'
        );
      }
    });
  } else {
    hideEmptyCard('exportShareChart');
  }

  // Brazil top export destinations (Comex Stat). The total export line itself is
  // overlaid on the Pork Exports vs. Imports chart above; here the same total
  // (brazilExportMap) backs the "Other" remainder so the stack reaches the total.
  const brazilDest = brazil.by_destination || {};
  if (brazilDest.dates?.length && Object.keys(brazilDest.series || {}).length) {
    const countries = Object.entries(brazilDest.series);
    registerRangeControl({
      chartId: 'brazilDestinationsChart',
      options: ['1y', '3y', '5y', '10y', 'all'],
      defaultRange: '5y',
      renderer(range) {
        const { start, end } = getRangeSlice(brazilDest.dates, range);
        const labels = brazilDest.dates.slice(start, end);
        const datasets = countries.map(([country, values], i) =>
          dataset(country, values.slice(start, end), C.seq[i % C.seq.length], { stack: 'brazil' })
        );
        const otherData = labels.map((d, idx) => {
          const total = brazilExportMap[d];
          if (total == null) return null;
          const named = countries.reduce((sum, [, values]) => {
            const v = values[start + idx];
            return sum + (v != null ? v : 0);
          }, 0);
          return Math.max(0, total - named);
        });
        if (otherData.some(v => v != null)) {
          datasets.push(dataset('Other', otherData, '#c4ccd2', { stack: 'brazil' }));
        }
        renderBarChart('brazilDestinationsChart', labels, datasets, 'Million lb', {
          stacked: true,
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

  // Monthly export comparison — US pork exports by calendar month, one grouped bar
  // per year (last N years side by side) to read seasonality and YoY at a glance.
  if (totals.dates?.length && (totals.export_pork || []).some(v => v != null)) {
    const exportLb = (totals.export_pork || []).map(v => v != null ? v / 1000 : null);
    const ymMap = buildYearMonthMap(totals.dates, exportLb);
    const N = { '3y': 3, '5y': 5, '7y': 7 };
    registerRangeControl({
      chartId: 'exportComparisonChart',
      options: ['3y', '5y', '7y'],
      defaultRange: '5y',
      renderer(range) {
        const years = Object.keys(ymMap).map(Number).sort((a, b) => a - b).slice(-(N[range] || 5));
        const datasets = years.map((yr, i) => dataset(String(yr), monthsForYear(ymMap, yr), C.seq[i % C.seq.length]));
        renderBarChart('exportComparisonChart', MON_SHORT, datasets, 'Million lb', {
          categoryX: true,
          maxTicks: 12,
          tooltip: {
            callbacks: {
              label(ctx) {
                const v = Number(ctx.parsed.y);
                if (!Number.isFinite(v)) return ctx.dataset.label || '';
                return `${ctx.dataset.label}: ${fmtNum(v, 1)}M lb`;
              }
            }
          }
        });
      }
    });
  } else {
    hideEmptyCard('exportComparisonChart');
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

  const margin = costs.monthly_cutout_net_spread;
  if (seriesHasData(margin)) {
    registerRangeControl({
      chartId: 'monthlyMarginChart',
      options: ['1y', '2y', '3y', '5y', 'all'],
      defaultRange: '3y',
      renderer(range) {
        const { start, end } = getRangeSlice(margin.dates, range);
        renderLineChart(
          'monthlyMarginChart',
          margin.dates.slice(start, end),
          [dataset('Monthly cutout-net spread', margin.values.slice(start, end), C.navy, { fill: true, backgroundColor: 'rgba(1,48,70,0.08)' })],
          '$/cwt'
        );
      }
    });
  } else {
    hideEmptyCard('monthlyMarginChart');
  }
}

function initMonthlySignup(data) {
  const form = document.getElementById('dashboardSignupForm');
  const status = document.getElementById('dashboardSignupStatus');
  if (!form || !status) return;
  const enabled = !!data.meta?.monthly_updates?.enabled;
  form.addEventListener('submit', event => {
    event.preventDefault();
    status.textContent = enabled
      ? 'Thanks. You are on the pork chartbook update list.'
      : 'Signup capture is designed and ready to connect to the preferred backend.';
  });
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
