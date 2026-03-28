const charts = {};
const chartRanges = {};
const chartRenderers = {};

const RANGE_LABELS = {
  '30d': '30D',
  '60d': '60D',
  '3m': '3M',
  '90d': '90D',
  '6m': '6M',
  '1y': '1Y',
  '2y': '2Y',
  '3y': '3Y',
  '5y': '5Y',
  '10y': '10Y',
  all: 'All'
};

const DASH_COLORS = {
  navy: '#013046',
  navy2: '#0a4561',
  orange: '#F6851F',
  teal: '#1F9EBC',
  gold: '#FDB714',
  sky: '#8FCAE6',
  slate: '#939598',
  red: '#991b1b',
  redSoft: '#dc2626',
  seq: ['#F6851F', '#1F9EBC', '#013046', '#FDB714', '#8FCAE6', '#939598', '#E5700A']
};

const htmlLegendPlugin = {
  id: 'htmlLegend',
  afterUpdate(chart, args, options) {
    const containerId = options && options.containerID;
    if (!containerId) return;
    const container = document.getElementById(containerId);
    if (!container) return;

    const list = container.querySelector('ul') || document.createElement('ul');
    list.className = 'chart-legend-list';
    while (list.firstChild) {
      list.firstChild.remove();
    }

    const items = chart.options.plugins.legend.labels.generateLabels(chart);
    items.forEach(item => {
      if (item.hidden) return;
      const li = document.createElement('li');
      li.className = 'chart-legend-item';

      const swatch = document.createElement('span');
      swatch.className = 'chart-legend-swatch';
      swatch.style.background = item.fillStyle || item.strokeStyle;
      swatch.style.borderColor = item.strokeStyle || item.fillStyle;

      const label = document.createElement('span');
      label.className = 'chart-legend-label';
      label.textContent = item.text;

      li.appendChild(swatch);
      li.appendChild(label);
      list.appendChild(li);
    });

    if (!container.contains(list)) {
      container.appendChild(list);
    }
  }
};

const touchTooltipPlugin = {
  id: 'touchTooltip',
  afterEvent(chart, args) {
    if (args.event.type === 'pointerup' || args.event.type === 'pointerleave') {
      if ('ontouchstart' in window) {
        clearTimeout(chart._touchTooltipTimeout);
        chart._touchTooltipTimeout = setTimeout(() => {
          chart.tooltip.setActiveElements([], { x: 0, y: 0 });
          chart.update('none');
        }, 2000);
        args.cancelable = false;
        args.changed = false;
      }
    }
  }
};

function isMobileWidth() { return window.innerWidth <= 480; }

function mobileAspectRatio(desktopRatio) {
  if (window.innerWidth <= 480) return Math.max(desktopRatio * 0.7, 1.0);
  if (window.innerWidth <= 768) return Math.max(desktopRatio * 0.85, 1.1);
  return desktopRatio;
}

if (window.Chart) {
  Chart.register(htmlLegendPlugin, touchTooltipPlugin);
  Chart.defaults.font.family = 'Lexend';
  Chart.defaults.font.size = isMobileWidth() ? 11 : 13;
  Chart.defaults.color = DASH_COLORS.navy;
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  Chart.defaults.plugins.legend.labels.pointStyle = 'rect';
  Chart.defaults.plugins.tooltip.backgroundColor = 'rgba(1,48,70,0.92)';
  Chart.defaults.plugins.tooltip.titleColor = '#fff';
  Chart.defaults.plugins.tooltip.bodyColor = '#eaf2f7';
  Chart.defaults.plugins.tooltip.cornerRadius = 12;
  Chart.defaults.plugins.tooltip.padding = isMobileWidth() ? 10 : 12;
}

const MON_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function fmtNum(value, digits = 0) {
  if (value == null || Number.isNaN(value)) return '—';
  return value.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits
  });
}

function fmtM(value) {
  if (value == null || Number.isNaN(value)) return '—';
  if (Math.abs(value) >= 1e9) return (value / 1e9).toFixed(1) + 'B';
  if (Math.abs(value) >= 1e6) return (value / 1e6).toFixed(1) + 'M';
  if (Math.abs(value) >= 1e3) return (value / 1e3).toFixed(0) + 'K';
  return value.toFixed(0);
}

function fmtMillionsAxis(value) {
  if (value == null || Number.isNaN(Number(value))) return '';
  const millions = Number(value) / 1e6;
  const rounded = Math.abs(millions - Math.round(millions)) < 1e-6
    ? String(Math.round(millions))
    : millions.toFixed(1);
  return `${rounded}M`;
}

function fmtAxisNumber(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return value;
  const abs = Math.abs(numeric);
  if (Math.abs(numeric - Math.round(numeric)) < 1e-6) {
    return fmtNum(Math.round(numeric), 0);
  }
  if (abs >= 100) return fmtNum(numeric, 0);
  if (abs >= 10) return fmtNum(numeric, 1);
  if (abs >= 1) return fmtNum(numeric, 1);
  return fmtNum(numeric, 2);
}

function fmtDate(dateStr) {
  if (!dateStr) return '';
  const parts = dateStr.split('-');
  if (parts.length === 3) return `${parts[1]}/${parts[2]}/${parts[0]}`;
  return dateStr;
}

function fmtYM(dateStr) {
  if (!dateStr) return '';
  const parts = dateStr.split('-');
  if (parts.length < 2) return dateStr;
  const month = parseInt(parts[1], 10) - 1;
  if (month < 0 || month > 11) return dateStr;
  return `${MON_SHORT[month]}-${parts[0].slice(2)}`;
}

function fmtTooltipDate(dateStr) {
  if (!dateStr || typeof dateStr !== 'string') return dateStr;
  const monthly = dateStr.match(/^(\d{4})-(\d{2})$/);
  if (monthly) {
    const month = parseInt(monthly[2], 10) - 1;
    if (month >= 0 && month < 12) return `${MON_SHORT[month]} ${monthly[1]}`;
    return dateStr;
  }
  const daily = dateStr.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (daily) {
    const month = parseInt(daily[2], 10) - 1;
    if (month >= 0 && month < 12) return `${parseInt(daily[3], 10)} ${MON_SHORT[month]} ${daily[1]}`;
    return dateStr;
  }
  return dateStr;
}

function parseAxisDate(label) {
  if (typeof label !== 'string') return null;
  const match = label.match(/^(\d{4})-(\d{2})(?:-(\d{2}))?$/);
  if (!match) return null;
  const year = parseInt(match[1], 10);
  const month = parseInt(match[2], 10);
  const day = match[3] ? parseInt(match[3], 10) : 1;
  const date = new Date(Date.UTC(year, month - 1, day));
  if (Number.isNaN(date.getTime())) return null;
  return { date, year, month, day };
}

function axisWeekKey(item) {
  if (!item || !item.date) return null;
  const tmp = new Date(item.date);
  const day = tmp.getUTCDay() || 7;
  tmp.setUTCDate(tmp.getUTCDate() + 4 - day);
  const yearStart = new Date(Date.UTC(tmp.getUTCFullYear(), 0, 1));
  const week = Math.ceil((((tmp - yearStart) / 86400000) + 1) / 7);
  return `${tmp.getUTCFullYear()}-${String(week).padStart(2, '0')}`;
}

function reduceTickIndices(indices, maxTicks) {
  if (indices.length <= maxTicks) return indices;
  const out = [];
  const last = indices.length - 1;
  const step = last / Math.max(1, maxTicks - 1);
  for (let i = 0; i < maxTicks; i += 1) {
    out.push(indices[Math.round(i * step)]);
  }
  return [...new Set(out)];
}

function dedupeRenderedTickIndices(indices, labels, mode) {
  const out = [];
  let lastRendered = null;
  [...new Set(indices)].sort((a, b) => a - b).forEach(index => {
    const rendered = formatAxisDateLabel(labels[index], mode);
    if (rendered === lastRendered) return;
    out.push(index);
    lastRendered = rendered;
  });
  return out;
}

function buildDateTickPlan(labels, maxTicks = 6) {
  const parsed = labels.map(parseAxisDate);
  if (!parsed.length || parsed.some(item => !item)) return null;

  const spanDays = Math.max(1, Math.round((parsed[parsed.length - 1].date - parsed[0].date) / 86400000));
  const target = Math.min(Math.max(maxTicks, 4), 8);
  const monthlyStarts = parsed.reduce((out, item, index) => {
    const prev = parsed[index - 1];
    if (!prev || prev.year !== item.year || prev.month !== item.month) out.push(index);
    return out;
  }, []);
  const quarterlyStarts = monthlyStarts.filter(index => [1, 4, 7, 10].includes(parsed[index].month));
  const semiAnnualStarts = monthlyStarts.filter(index => [1, 7].includes(parsed[index].month));
  const yearlyStarts = monthlyStarts.filter(index => parsed[index].month === 1);
  const weeklyStarts = parsed.reduce((out, item, index) => {
    const currentWeek = axisWeekKey(item);
    const prevWeek = axisWeekKey(parsed[index - 1]);
    if (!prevWeek || currentWeek !== prevWeek) {
      out.push(index);
    }
    return out;
  }, []);
  const spanMonths = Math.max(
    1,
    (parsed[parsed.length - 1].year - parsed[0].year) * 12 + (parsed[parsed.length - 1].month - parsed[0].month) + 1
  );

  let mode = 'daily';
  let indices;
  let anchoredMode = false;

  if (spanMonths > 48) {
    mode = 'yearly';
    indices = yearlyStarts;
    anchoredMode = true;
  } else if (spanMonths > 18) {
    mode = 'semiannual';
    indices = semiAnnualStarts;
    anchoredMode = true;
  } else if (spanMonths > 8) {
    mode = 'quarterly';
    indices = quarterlyStarts;
    anchoredMode = true;
  } else if (spanMonths > 3) {
    mode = 'monthly';
    indices = monthlyStarts;
    anchoredMode = true;
  } else if (spanDays > 45) {
    mode = 'monthly';
    indices = monthlyStarts;
    anchoredMode = true;
  } else if (spanDays > 14) {
    mode = 'daily';
    indices = weeklyStarts;
    anchoredMode = true;
  } else {
    const stride = Math.max(1, Math.ceil(labels.length / target));
    indices = labels.reduce((out, _label, index) => {
      if (index % stride === 0 || index === labels.length - 1) out.push(index);
      return out;
    }, []);
  }

  if (!indices.length) {
    indices = [0, labels.length - 1];
  }

  if (indices.length === 1 && labels.length > 1) {
    indices = [indices[0], labels.length - 1];
  }

  if (!anchoredMode && indices[0] !== 0 && indices[0] > Math.max(2, Math.round(labels.length * 0.18))) {
    indices.unshift(0);
  }

  if (!anchoredMode && indices[indices.length - 1] !== labels.length - 1) {
    indices.push(labels.length - 1);
  }

  let finalIndices = ((mode === 'yearly' && indices.length <= 20) || (mode === 'monthly' && indices.length <= 8))
    ? [...indices]
    : reduceTickIndices(indices, target);
  finalIndices = dedupeRenderedTickIndices(finalIndices, labels, mode);

  if (anchoredMode && finalIndices.length > 1) {
    const minGapDaysByMode = {
      daily: 6,
      monthly: 0,
      quarterly: 70,
      semiannual: 150,
      yearly: 300
    };
    const minGapDays = minGapDaysByMode[mode] || 25;
    const filtered = finalIndices.filter((index, pos) => {
      if (pos === finalIndices.length - 1) return true;
      const current = parseAxisDate(labels[index]);
      const next = parseAxisDate(labels[finalIndices[pos + 1]]);
      if (!current || !next) return true;
      const gapDays = Math.round((next.date - current.date) / 86400000);
      return gapDays >= minGapDays;
    });
    if (filtered.length) finalIndices = filtered;
  }

  if (!((mode === 'yearly' && finalIndices.length <= 20) || (mode === 'monthly' && finalIndices.length <= 8)) && finalIndices.length > target) {
    finalIndices = reduceTickIndices(finalIndices, target);
    finalIndices = dedupeRenderedTickIndices(finalIndices, labels, mode);
  }

  if (mode === 'yearly' && finalIndices.length > 2) {
    const lastIndex = finalIndices[finalIndices.length - 1];
    if ((labels.length - 1) - lastIndex <= 1) {
      finalIndices.pop();
    }
  }

  return { mode, indices: finalIndices };
}

function formatAxisDateLabel(label, mode) {
  const parsed = parseAxisDate(label);
  if (!parsed) return typeof label === 'string' && label.includes('-') ? fmtYM(label) : label;
  if (mode === 'yearly') return String(parsed.year);
  if (mode === 'semiannual' || mode === 'quarterly' || mode === 'monthly') return `${MON_SHORT[parsed.month - 1]} ${parsed.year}`;
  return `${MON_SHORT[parsed.month - 1]} ${parsed.day}`;
}

function latestNonNull(dates, values) {
  for (let i = values.length - 1; i >= 0; i -= 1) {
    if (values[i] != null && !Number.isNaN(values[i])) {
      return { date: dates[i], value: values[i] };
    }
  }
  return { date: null, value: null };
}

function rollingAverage(values, windowSize) {
  return values.map((_, index) => {
    if (index < windowSize - 1) return null;
    const slice = values.slice(index - windowSize + 1, index + 1).filter(v => v != null);
    if (!slice.length) return null;
    return slice.reduce((sum, value) => sum + value, 0) / slice.length;
  });
}

function rollingSum(values, windowSize) {
  return values.map((_, index) => {
    if (index < windowSize - 1) return null;
    const slice = values.slice(index - windowSize + 1, index + 1).filter(v => v != null);
    if (!slice.length) return null;
    return slice.reduce((sum, value) => sum + value, 0);
  });
}

function buildYearMonthMap(dates, values) {
  const out = {};
  dates.forEach((dateStr, index) => {
    const value = values[index];
    if (value == null || !dateStr || dateStr.length < 7) return;
    const year = parseInt(dateStr.slice(0, 4), 10);
    const month = parseInt(dateStr.slice(5, 7), 10);
    if (!out[year]) out[year] = {};
    out[year][month] = value;
  });
  return out;
}

function rangeCutoff(range, referenceDate) {
  const now = referenceDate || new Date();
  switch (range) {
    case '30d':
      return new Date(now.getFullYear(), now.getMonth(), now.getDate() - 30);
    case '60d':
      return new Date(now.getFullYear(), now.getMonth(), now.getDate() - 60);
    case '3m':
      return new Date(now.getFullYear(), now.getMonth() - 3, now.getDate());
    case '90d':
      return new Date(now.getFullYear(), now.getMonth(), now.getDate() - 90);
    case '6m':
      return new Date(now.getFullYear(), now.getMonth() - 6, now.getDate());
    case '1y':
      return new Date(now.getFullYear() - 1, now.getMonth(), now.getDate());
    case '2y':
      return new Date(now.getFullYear() - 2, now.getMonth(), now.getDate());
    case '3y':
      return new Date(now.getFullYear() - 3, now.getMonth(), now.getDate());
    case '5y':
      return new Date(now.getFullYear() - 5, now.getMonth(), now.getDate());
    case '10y':
      return new Date(now.getFullYear() - 10, now.getMonth(), now.getDate());
    default:
      return null;
  }
}

function isMonthlySeries(dates) {
  return dates.length > 0 && dates.every(date => typeof date === 'string' && /^\d{4}-\d{2}$/.test(date));
}

function getRangeSlice(dates, range) {
  if (range === 'all' || !dates.length) {
    return { start: 0, end: dates.length };
  }
  if (isMonthlySeries(dates)) {
    const monthlyPoints = {
      '3m': 3,
      '6m': 6,
      '1y': 12,
      '2y': 24,
      '3y': 36,
      '5y': 60,
      '10y': 120
    };
    const count = monthlyPoints[range];
    if (count) {
      return { start: Math.max(0, dates.length - count), end: dates.length };
    }
  }
  const latestParsed = parseAxisDate(dates[dates.length - 1]);
  const cutoff = rangeCutoff(range, latestParsed ? new Date(latestParsed.date.getUTCFullYear(), latestParsed.date.getUTCMonth(), latestParsed.date.getUTCDate()) : null);
  if (!cutoff) return { start: 0, end: dates.length };
  const iso = cutoff.toISOString().slice(0, 10);
  const start = Math.max(0, dates.findIndex(date => date >= iso));
  return { start: start === -1 ? 0 : start, end: dates.length };
}

function historyYearsForRange(years, range, minYear) {
  const sorted = years.filter(year => !minYear || year >= minYear).sort((a, b) => a - b);
  if (!sorted.length) return [];
  const lookbackMap = { '2y': 2, '3y': 3, '5y': 5, '10y': 10 };
  if (range === 'all') return sorted;
  const count = lookbackMap[range] || 3;
  return sorted.slice(-count);
}

function monthsForYear(map, year) {
  return Array.from({ length: 12 }, (_, idx) => map[year]?.[idx + 1] ?? null);
}

function averageMonths(map, years) {
  return Array.from({ length: 12 }, (_, idx) => {
    const month = idx + 1;
    const values = years.map(year => map[year]?.[month]).filter(v => v != null);
    if (!values.length) return null;
    return values.reduce((sum, value) => sum + value, 0) / values.length;
  });
}

function dataset(label, data, color, extra = {}) {
  return Object.assign({
    label,
    data,
    borderColor: color,
    backgroundColor: color,
    pointRadius: 0,
    pointHoverRadius: 5,
    pointHoverBorderWidth: 3,
    pointHoverBorderColor: '#fff',
    borderWidth: isMobileWidth() ? 2 : 3.4,
    tension: 0.12,
    spanGaps: true,
    fill: false
  }, extra);
}

function destroyChart(id) {
  if (charts[id]) {
    charts[id].destroy();
  }
}

function baseOptions(yLabel, extra = {}) {
  const hasY2 = !!extra.y2;
  const tooltipConfig = extra.tooltip || {};
  const tooltipCallbacks = tooltipConfig.callbacks || {};
  const defaultGenerateLabels = window.Chart && Chart.defaults.plugins.legend.labels.generateLabels
    ? Chart.defaults.plugins.legend.labels.generateLabels
    : null;
  const options = {
    responsive: true,
    maintainAspectRatio: true,
    aspectRatio: mobileAspectRatio(extra.aspect || 1.7),
    interaction: { mode: 'index', intersect: false },
    layout: { padding: isMobileWidth() ? { top: 2, right: 2, bottom: 8, left: 2 } : { top: 4, right: 8, bottom: 14, left: 8 } },
    plugins: {
      legend: {
        display: false,
        position: 'bottom',
        align: 'start',
        labels: {
          boxWidth: 10,
          boxHeight: 10,
          padding: 14,
          font: { size: isMobileWidth() ? 11 : 13, weight: '600' },
          generateLabels: defaultGenerateLabels ? chart => {
            const seenLegendKeys = new Set();
            return defaultGenerateLabels(chart).reduce((items, item) => {
              const ds = chart.data.datasets?.[item.datasetIndex];
              const legendKey = ds?.legendKey;
              if (legendKey && seenLegendKeys.has(legendKey)) {
                return items;
              }
              if (legendKey) {
                seenLegendKeys.add(legendKey);
              }
              const legendText = ds?.legendLabel || item.text;
              const axisSuffix = hasY2 ? ` (${ds?.yAxisID === 'y2' ? 'RHS' : 'LHS'})` : '';
              return items.concat(Object.assign({}, item, {
                text: `${legendText}${axisSuffix}`,
                legendKey
              }));
            }, []);
          } : undefined
        }
      },
      htmlLegend: extra.legend === false ? undefined : { containerID: `legend-${extra.chartId}` },
      tooltip: Object.assign({ filter: function (item) { return item.raw != null; } }, tooltipConfig, {
        callbacks: Object.assign({
          title(items) {
            const item = items && items[0];
            if (!item) return '';
            return fmtTooltipDate(item.label);
          },
          label(context) {
            const numeric = Number(
              context.parsed?.y != null ? context.parsed.y
                : context.parsed?.x != null ? context.parsed.x
                  : context.raw
            );
            if (!Number.isFinite(numeric)) {
              return context.dataset?.label || '';
            }
            const label = context.dataset?.label ? `${context.dataset.label}: ` : '';
            return `${label}${fmtNum(numeric, 1)}`;
          }
        }, tooltipCallbacks)
      })
    },
    scales: {
      x: {
        afterBuildTicks(scale) {
          const mobileTicks = isMobileWidth() ? Math.min(extra.maxTicks || 12, 4) : (extra.maxTicks || 12);
          const plan = buildDateTickPlan(scale.getLabels(), mobileTicks);
          if (!plan) return;
          scale.$dateTickPlan = plan;
          scale.ticks = plan.indices.map(index => ({ value: index }));
        },
        ticks: {
          maxTicksLimit: isMobileWidth() ? Math.min(extra.maxTicks || 12, 4) : (extra.maxTicks || 12),
          autoSkip: false,
          color: '#627684',
          padding: isMobileWidth() ? 6 : 10,
          maxRotation: 0,
          minRotation: 0,
          font: { size: isMobileWidth() ? 10 : 13 },
          callback(value) {
            const label = this.getLabelForValue(value);
            return formatAxisDateLabel(label, this.$dateTickPlan?.mode);
          }
        },
        border: { display: true, color: 'rgba(1,48,70,0.12)' },
        grid: { drawOnChartArea: false, drawTicks: true, tickLength: 6 }
      },
      y: {
        title: { display: !!yLabel, text: yLabel, color: '#5f7180', font: { size: isMobileWidth() ? 10 : 13, weight: '600' } },
        ticks: {
          color: '#627684',
          padding: isMobileWidth() ? 6 : 10,
          font: { size: isMobileWidth() ? 10 : 13 },
          callback: extra.yTickCallback || fmtAxisNumber
        },
        border: { display: false },
        grid: { color: 'rgba(1,48,70,0.045)' }
      }
    }
  };
  if (hasY2) {
    options.scales.y2 = {
      position: 'right',
      title: { display: true, text: extra.y2, color: '#5f7180', font: { size: isMobileWidth() ? 10 : 13, weight: '600' } },
      ticks: {
        color: '#627684',
        padding: isMobileWidth() ? 6 : 10,
        font: { size: isMobileWidth() ? 10 : 13 },
        callback: extra.y2TickCallback || fmtAxisNumber
      },
      border: { display: false },
      grid: { drawOnChartArea: false }
    };
  }
  if (extra.stacked) {
    options.scales.x.stacked = true;
    options.scales.y.stacked = true;
  }
  if (extra.yMin != null) options.scales.y.min = extra.yMin;
  if (extra.yMax != null) options.scales.y.max = extra.yMax;
  if (hasY2 && extra.y2Min != null) options.scales.y2.min = extra.y2Min;
  if (hasY2 && extra.y2Max != null) options.scales.y2.max = extra.y2Max;
  return options;
}

function renderLineChart(id, labels, datasets, yLabel, extra = {}) {
  const ctx = document.getElementById(id);
  if (!ctx) return;
  destroyChart(id);
  charts[id] = new Chart(ctx, {
    type: 'line',
    data: { labels, datasets },
    options: baseOptions(yLabel, Object.assign({ chartId: id }, extra))
  });
}

function renderBarChart(id, labels, datasets, yLabel, extra = {}) {
  const ctx = document.getElementById(id);
  if (!ctx) return;
  destroyChart(id);
  const options = baseOptions(yLabel, Object.assign({ chartId: id }, extra));
  if (extra.stacked) {
    options.scales.x.stacked = true;
    options.scales.y.stacked = true;
  }
  if (extra.horizontal) {
    options.indexAxis = 'y';
  }
  const cleanDatasets = datasets.map(ds => Object.assign({}, ds, {
    borderWidth: 0, borderColor: 'transparent',
    hoverBorderWidth: 0, hoverBorderColor: 'transparent'
  }));
  charts[id] = new Chart(ctx, {
    type: 'bar',
    data: { labels, datasets: cleanDatasets },
    options
  });
}

function renderStackedAreaChart(id, labels, datasets, yLabel, y2Label, extra = {}) {
  const ctx = document.getElementById(id);
  if (!ctx) return;
  destroyChart(id);
  charts[id] = new Chart(ctx, {
    type: 'line',
    data: { labels, datasets },
    options: baseOptions(yLabel, Object.assign({ chartId: id, y2: y2Label, maxTicks: 12, stacked: true }, extra))
  });
}

function showPlaceholder(id, message) {
  const node = document.getElementById(id);
  if (!node) return;
  node.innerHTML = `<div class="placeholder-note">${message}</div>`;
}

function insertRangeControls(chartId, options) {
  const canvas = document.getElementById(chartId);
  if (!canvas) return;
  const card = canvas.closest('.card');
  if (!card) return;
  let toolbar = card.querySelector(`.chart-toolbar[data-chart="${chartId}"]`);
  if (!toolbar) {
    toolbar = document.createElement('div');
    toolbar.className = 'chart-toolbar';
    toolbar.dataset.chart = chartId;

    const controls = document.createElement('div');
    controls.className = 'range-controls';
    controls.dataset.chart = chartId;

    const legend = document.createElement('div');
    legend.className = 'chart-legend';
    legend.id = `legend-${chartId}`;

    toolbar.appendChild(controls);
    toolbar.appendChild(legend);

    const sub = card.querySelector('.sub');
    if (sub) {
      sub.insertAdjacentElement('afterend', toolbar);
    } else {
      card.insertBefore(toolbar, canvas);
    }
  }
  const host = toolbar.querySelector(`.range-controls[data-chart="${chartId}"]`);
  const safeOptions = options || [];
  host.innerHTML = safeOptions.map(option => {
    const active = chartRanges[chartId] === option ? ' active' : '';
    return `<button class="range-btn${active}" type="button" data-chart="${chartId}" data-range="${option}">${RANGE_LABELS[option] || option}</button>`;
  }).join('');
  host.style.display = safeOptions.length ? '' : 'none';
}

function registerRangeControl({ chartId, options, defaultRange, renderer }) {
  chartRanges[chartId] = defaultRange || options[0];
  chartRenderers[chartId] = renderer;
  insertRangeControls(chartId, options);
  renderer(chartRanges[chartId]);
}

document.addEventListener('click', event => {
  const button = event.target.closest('.range-btn');
  if (!button) return;
  const chartId = button.dataset.chart;
  const range = button.dataset.range;
  if (!chartRenderers[chartId]) return;
  chartRanges[chartId] = range;
  insertRangeControls(chartId, button.parentElement ? Array.from(button.parentElement.querySelectorAll('.range-btn')).map(node => node.dataset.range) : [range]);
  chartRenderers[chartId](range);
});

/* Re-render charts on resize/orientation change for mobile aspect ratios */
(function () {
  let resizeTimer;
  window.addEventListener('resize', function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      Object.keys(chartRenderers).forEach(function (chartId) {
        if (chartRenderers[chartId] && chartRanges[chartId]) {
          chartRenderers[chartId](chartRanges[chartId]);
        }
      });
    }, 250);
  });
})();

/* Show sidebar logo when header brand scrolls out of view */
(function () {
  const headerBrand = document.getElementById('topHeaderBrand');
  const sidebarBrand = document.getElementById('sidebarBrand');
  if (!headerBrand || !sidebarBrand) return;
  const observer = new IntersectionObserver(function (entries) {
    sidebarBrand.classList.toggle('is-visible', !entries[0].isIntersecting);
  }, { threshold: 0 });
  observer.observe(headerBrand);
})();
