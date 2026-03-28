/* pork-dashboard.js — uses helpers from dashboard-common.js */

const C = DASH_COLORS;

// ── Utilities ───────────────────────────────────────────────────────────
function porkText(id, text) {
  const node = document.getElementById(id);
  if (node) node.textContent = text;
}

function slugifyText(value) {
  return String(value || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
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

function setPorkChartSources() {
  const nass  = '<a href="https://quickstats.nass.usda.gov/" target="_blank" rel="noreferrer">USDA NASS</a>';
  const amsHg = '<a href="https://mpr.datamart.ams.usda.gov/" target="_blank" rel="noreferrer">USDA AMS LM_HG201</a>';
  const amsPk = '<a href="https://mpr.datamart.ams.usda.gov/" target="_blank" rel="noreferrer">USDA AMS LM_PK602</a>';
  const ers   = '<a href="https://www.ers.usda.gov/data-products/livestock-and-meat-international-trade-data/" target="_blank" rel="noreferrer">USDA ERS Trade Data</a>';

  const srcMap = {
    herdTotalChart:          `Chart: Innovate Animal Ag • Source: ${nass}`,
    herdBreedingMarketChart: `Chart: Innovate Animal Ag • Source: ${nass}`,
    herdPigCropChart:        `Chart: Innovate Animal Ag • Source: ${nass}`,
    slaughterHeadChart:      `Chart: Innovate Animal Ag • Source: ${nass}`,
    porkProductionChart:     `Chart: Innovate Animal Ag • Source: ${nass}`,
    carcassWeightChart:      `Chart: Innovate Animal Ag • Source: ${amsHg}`,
    hogPriceChart:           `Chart: Innovate Animal Ag • Source: ${amsHg}`,
    cutoutChart:             `Chart: Innovate Animal Ag • Source: ${amsPk}`,
    primalsChart:            `Chart: Innovate Animal Ag • Source: ${amsPk}`,
    tradeFlowChart:          `Chart: Innovate Animal Ag • Source: ${ers}`,
    exportDestinationsChart: `Chart: Innovate Animal Ag • Source: ${ers}`,
    importSourcesChart:      `Chart: Innovate Animal Ag • Source: ${ers}`,
  };
  Object.entries(srcMap).forEach(([id, html]) => appendCardSource(id, html));
}

// ── Sidebar + mobile nav ────────────────────────────────────────────────
function initPorkSidebarNav() {
  const nav = document.getElementById('porkSidebarNav');
  if (!nav) return;
  const sections = Array.from(document.querySelectorAll('.section[id], .overview-band[id]'));
  if (!sections.length) return;

  const usedIds = new Set(Array.from(document.querySelectorAll('[id]')).map(n => n.id));
  const makeId = base => {
    let c = base || 'chart', s = 2;
    while (usedIds.has(c)) { c = `${base}-${s}`; s++; }
    usedIds.add(c);
    return c;
  };
  sections.forEach(section =>
    Array.from(section.querySelectorAll('.card')).forEach(card => {
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
    Array.from(section.querySelectorAll('.card')).forEach(card => {
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
    mobileSelect.innerHTML = '<option value="">Jump to section…</option>';
    sections.forEach(s => {
      const opt = document.createElement('option');
      opt.value = `#${s.id}`;
      opt.textContent = s.querySelector('.section-head h2')?.textContent?.trim() || s.id;
      mobileSelect.appendChild(opt);
    });
    mobileSelect.addEventListener('change', () => {
      if (mobileSelect.value) { location.hash = mobileSelect.value; mobileSelect.value = ''; }
    });
  }

  const observer = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const id = entry.target.id;
        groups.forEach(g => g.classList.toggle('is-active', g.dataset.section === id));
      }
    });
  }, { threshold: 0.2 });
  sections.forEach(s => observer.observe(s));
}

// ── KPI population ──────────────────────────────────────────────────────
function populatePorkKpi(kpi) {
  const inv = kpi.total_hog_inventory;
  porkText('kpiInventory', inv?.value != null ? fmtM(inv.value * 1000) : '—');
  porkText('kpiInventorySub', inv?.date || 'latest quarterly');

  const sl = kpi.weekly_slaughter_head;
  porkText('kpiSlaughter', sl?.value != null ? fmtM(sl.value) : '—');
  porkText('kpiSlaughterSub', sl?.date || 'head, weekly');

  const pr = kpi.barrow_gilt_base_price;
  porkText('kpiPrice', pr?.value != null ? '$' + fmtNum(pr.value, 2) : '—');
  porkText('kpiPriceSub', pr?.date || '$/cwt base');

  const cu = kpi.pork_cutout_value;
  porkText('kpiCutout', cu?.value != null ? '$' + fmtNum(cu.value, 2) : '—');
  porkText('kpiCutoutSub', cu?.date || '$/cwt');

  const ex = kpi.ytd_export_volume_1000lb;
  porkText('kpiExports', ex?.value != null ? fmtM(ex.value * 1000) : '—');
  porkText('kpiExportsSub', ex?.year ? 'lbs YTD ' + ex.year : 'lbs YTD');
}

// ── Section builders ────────────────────────────────────────────────────
function buildHerd(herd) {
  const total = herd.total_inventory;
  if (total.dates.length) {
    registerRangeControl({
      chartId: 'herdTotalChart',
      options: ['5y', '10y', 'all'],
      defaultRange: 'all',
      renderer(range) {
        const { start, end } = getRangeSlice(total.dates, range);
        renderLineChart(
          'herdTotalChart',
          total.dates.slice(start, end),
          [dataset('Total Inventory (mil head)', total.values.slice(start, end).map(v => v != null ? v / 1000 : null), C.teal, { fill: true, backgroundColor: 'rgba(31,158,188,0.08)' })],
          'Millions of head',
          { aspect: 2.6 }
        );
      }
    });
  }

  const brd = herd.breeding_inventory;
  const mkt = herd.market_inventory;
  if (brd.dates.length || mkt.dates.length) {
    const allDates = [...new Set([...brd.dates, ...mkt.dates])].sort();
    const brdMap = Object.fromEntries(brd.dates.map((d, i) => [d, brd.values[i]]));
    const mktMap = Object.fromEntries(mkt.dates.map((d, i) => [d, mkt.values[i]]));
    registerRangeControl({
      chartId: 'herdBreedingMarketChart',
      options: ['5y', '10y', 'all'],
      defaultRange: 'all',
      renderer(range) {
        const { start, end } = getRangeSlice(allDates, range);
        const sliced = allDates.slice(start, end);
        renderLineChart(
          'herdBreedingMarketChart',
          sliced,
          [
            dataset('Breeding (thousands)', sliced.map(d => brdMap[d] ?? null), C.navy),
            dataset('Market (thousands)',   sliced.map(d => mktMap[d] ?? null), C.teal),
          ],
          'Thousands of head'
        );
      }
    });
  }

  const pc = herd.pig_crop;
  if (pc.dates.length) {
    registerRangeControl({
      chartId: 'herdPigCropChart',
      options: ['5y', '10y', 'all'],
      defaultRange: 'all',
      renderer(range) {
        const { start, end } = getRangeSlice(pc.dates, range);
        renderLineChart(
          'herdPigCropChart',
          pc.dates.slice(start, end),
          [dataset('Pig Crop (mil head)', pc.values.slice(start, end).map(v => v != null ? v / 1000 : null), C.gold)],
          'Millions of head'
        );
      }
    });
  }
}

function buildSlaughterProduction(sp) {
  const sl = sp.slaughter_head;
  if (sl.dates.length) {
    registerRangeControl({
      chartId: 'slaughterHeadChart',
      options: ['1y', '2y', '3y', '5y', 'all'],
      defaultRange: '3y',
      renderer(range) {
        const { start, end } = getRangeSlice(sl.dates, range);
        renderLineChart(
          'slaughterHeadChart',
          sl.dates.slice(start, end),
          [dataset('Slaughter (head)', sl.values.slice(start, end), C.teal, { fill: true, backgroundColor: 'rgba(31,158,188,0.07)' })],
          'Head',
          { aspect: 2.6 }
        );
      }
    });
  }

  const pp = sp.pork_production_lb;
  if (pp.dates.length) {
    registerRangeControl({
      chartId: 'porkProductionChart',
      options: ['3y', '5y', '10y', 'all'],
      defaultRange: '5y',
      renderer(range) {
        const { start, end } = getRangeSlice(pp.dates, range);
        renderLineChart(
          'porkProductionChart',
          pp.dates.slice(start, end),
          [dataset('Pork Production (mil lbs)', pp.values.slice(start, end).map(v => v != null ? v / 1e6 : null), C.navy)],
          'Million lbs'
        );
      }
    });
  }

  const wt = sp.avg_carcass_weight;
  if (wt.dates.length) {
    registerRangeControl({
      chartId: 'carcassWeightChart',
      options: ['1y', '2y', '3y', '5y', 'all'],
      defaultRange: '3y',
      renderer(range) {
        const { start, end } = getRangeSlice(wt.dates, range);
        renderLineChart(
          'carcassWeightChart',
          wt.dates.slice(start, end),
          [dataset('Avg Carcass Weight (lb)', wt.values.slice(start, end), C.gold)],
          'Pounds'
        );
      }
    });
  }
}

function buildPrices(prices) {
  const bp = prices.barrow_gilt_base_price;
  const np = prices.barrow_gilt_net_price;
  const priceDates = [...new Set([...bp.dates, ...np.dates])].sort();
  const bpMap = Object.fromEntries(bp.dates.map((d, i) => [d, bp.values[i]]));
  const npMap = Object.fromEntries(np.dates.map((d, i) => [d, np.values[i]]));
  registerRangeControl({
    chartId: 'hogPriceChart',
    options: ['1y', '2y', '3y', '5y', 'all'],
    defaultRange: '3y',
    renderer(range) {
      const { start, end } = getRangeSlice(priceDates, range);
      const sliced = priceDates.slice(start, end);
      renderLineChart(
        'hogPriceChart',
        sliced,
        [
          dataset('Base Price ($/cwt)', sliced.map(d => bpMap[d] ?? null), C.navy),
          dataset('Net Price ($/cwt)',  sliced.map(d => npMap[d] ?? null), C.teal),
        ],
        '$/cwt',
        { aspect: 2.6 }
      );
    }
  });

  const cu = prices.pork_cutout_value;
  if (cu.dates.length) {
    registerRangeControl({
      chartId: 'cutoutChart',
      options: ['1y', '2y', '3y', '5y', 'all'],
      defaultRange: '3y',
      renderer(range) {
        const { start, end } = getRangeSlice(cu.dates, range);
        renderLineChart(
          'cutoutChart',
          cu.dates.slice(start, end),
          [dataset('Pork Cutout ($/cwt)', cu.values.slice(start, end), C.gold)],
          '$/cwt'
        );
      }
    });
  }

  if (prices.primals && Object.keys(prices.primals).length) {
    const primalEntries = Object.entries(prices.primals);
    const primalDates = [...new Set(primalEntries.flatMap(([, v]) => v.dates))].sort();
    const primalMaps = Object.fromEntries(
      primalEntries.map(([name, v]) => [name, Object.fromEntries(v.dates.map((d, i) => [d, v.values[i]]))])
    );
    registerRangeControl({
      chartId: 'primalsChart',
      options: ['1y', '2y', '3y', '5y', 'all'],
      defaultRange: '3y',
      renderer(range) {
        const { start, end } = getRangeSlice(primalDates, range);
        const sliced = primalDates.slice(start, end);
        renderLineChart(
          'primalsChart',
          sliced,
          primalEntries.map(([name], i) =>
            dataset(name, sliced.map(d => primalMaps[name][d] ?? null), C.seq[i % C.seq.length])
          ),
          '$/cwt'
        );
      }
    });
  }
}

function buildTrade(trade) {
  const td = trade.trade_totals;
  if (td.dates.length) {
    registerRangeControl({
      chartId: 'tradeFlowChart',
      options: ['3y', '5y', '10y', 'all'],
      defaultRange: '5y',
      renderer(range) {
        const { start, end } = getRangeSlice(td.dates, range);
        renderLineChart(
          'tradeFlowChart',
          td.dates.slice(start, end),
          [
            dataset('Pork Exports (mil lbs)', td.export_pork.slice(start, end).map(v => v != null ? v / 1000 : null), C.teal),
            dataset('Pork Imports (mil lbs)', td.import_pork.slice(start, end).map(v => v != null ? v / 1000 : null), C.redSoft),
          ],
          'Million lbs',
          { aspect: 2.6 }
        );
      }
    });
  }

  const exp = trade.exports_by_destination;
  if (exp.dates?.length) {
    registerRangeControl({
      chartId: 'exportDestinationsChart',
      options: ['3y', '5y', '10y', 'all'],
      defaultRange: '5y',
      renderer(range) {
        const { start, end } = getRangeSlice(exp.dates, range);
        renderLineChart(
          'exportDestinationsChart',
          exp.dates.slice(start, end),
          Object.entries(exp.series).map(([country, vals], i) =>
            dataset(country, vals.slice(start, end), C.seq[i % C.seq.length])
          ),
          '1,000 lbs'
        );
      }
    });
  }

  const imp = trade.imports_by_source;
  if (imp.dates?.length) {
    registerRangeControl({
      chartId: 'importSourcesChart',
      options: ['3y', '5y', '10y', 'all'],
      defaultRange: '5y',
      renderer(range) {
        const { start, end } = getRangeSlice(imp.dates, range);
        renderLineChart(
          'importSourcesChart',
          imp.dates.slice(start, end),
          Object.entries(imp.series).map(([country, vals], i) =>
            dataset(country, vals.slice(start, end), C.seq[i % C.seq.length])
          ),
          '1,000 lbs'
        );
      }
    });
  }
}

// ── Main load ───────────────────────────────────────────────────────────
async function loadPorkDashboard() {
  try {
    const resp = await fetch('data.json?v=' + Date.now());
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();

    if (data.meta?.updated) {
      porkText('dashFooter',
        `Pork dashboard updated ${data.meta.updated}. Sources: USDA NASS · USDA AMS · USDA ERS.`);
    }

    populatePorkKpi(data.kpi);
    buildHerd(data.herd);
    buildSlaughterProduction(data.slaughter_production);
    buildPrices(data.prices);
    buildTrade(data.trade);

    initPorkSidebarNav();
    setPorkChartSources();

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
