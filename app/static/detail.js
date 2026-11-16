/* Building detail view: week by week charts. Data comes from window.DETAIL (built by app/detail.py). */
(function () {
  var RAW = window.DETAIL || {}, D = RAW.data || {}, ORDER = RAW.order || [];
  var navDetail = document.getElementById('nav-detail'), navCurrent = document.querySelector('header nav a[aria-current]');
  var C = { actual: '#D97706', cool: '#0E7490', expected: '#0E7490', band: 'rgba(8,145,178,0.16)', ink: '#1D2459', grid: '#E6E9F2' };
  var cur = { id: null, week: 0 };
  var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  var DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

  function startMs(b) { var p = b.start.split(' '); return Date.parse(p[0] + 'T' + p[1] + ':00Z'); }
  function stamp(ms) { return new Date(ms).toISOString().slice(0, 16).replace('T', ' '); }
  function dayLabel(ms) { var d = new Date(ms); return MONTHS[d.getUTCMonth()] + ' ' + d.getUTCDate(); }
  function weekLabel(b, k) {
    var a = startMs(b) + k * 7 * 864e5, z = a + 6 * 864e5;
    return dayLabel(a) + ' to ' + dayLabel(z) + ', ' + new Date(z).getUTCFullYear();
  }
  function fmt(n) { return n == null ? '-' : Math.round(n).toLocaleString('en-US'); }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function base(xt, yt) {
    return {
      margin: { t: 30, r: 16, b: 52, l: 64 }, paper_bgcolor: '#fff', plot_bgcolor: '#fff',
      font: { family: 'Inter, system-ui, sans-serif', color: '#1f2937', size: 13 },
      xaxis: { title: xt ? { text: xt, standoff: 10 } : undefined, automargin: true, gridcolor: C.grid },
      yaxis: { title: yt ? { text: yt, standoff: 8 } : undefined, automargin: true, gridcolor: C.grid },
      legend: { orientation: 'h', x: 1, xanchor: 'right', y: 1.14, yanchor: 'bottom' }
    };
  }

  function weekSlice(b, k) {
    var n = 168, a = k * n, out = { t: [], actual: [], expected: [], lower: [], upper: [], temp: [], aboveX: [], aboveY: [] };
    var idx = {}, i;
    for (i = 0; i < b.h.length; i++) idx[b.h[i]] = i;
    var s0 = startMs(b);
    for (var j = a; j < a + n; j++) {
      out.t.push(stamp(s0 + j * 36e5));
      i = idx[j];
      if (i === undefined) { out.actual.push(null); out.expected.push(null); out.lower.push(null); out.upper.push(null); out.temp.push(null); continue; }
      out.actual.push(b.actual[i]); out.expected.push(b.expected[i]); out.lower.push(b.lower[i]); out.upper.push(b.upper[i]); out.temp.push(b.temp_f[i]);
      if (b.above[i]) { out.aboveX.push(stamp(s0 + j * 36e5)); out.aboveY.push(b.actual[i]); }
    }
    return out;
  }
  function weekStats(b, k) {
    var a = k * 168, z = a + 168, hrs = 0, ab = 0, over = 0, act = 0;
    for (var i = 0; i < b.h.length; i++) {
      if (b.h[i] < a || b.h[i] >= z) continue;
      hrs++; act += b.actual[i];
      if (b.above[i]) { ab++; over += b.actual[i] - b.upper[i]; }
    }
    return { hrs: hrs, ab: ab, over: over, pct: act > 0 ? 100 * over / act : 0 };
  }

  function drawWeek(b) {
    var w = weekSlice(b, cur.week);
    var band = { x: w.t.concat(w.t.slice().reverse()), y: w.upper.concat(w.lower.slice().reverse()), fill: 'toself', fillcolor: C.band,
      line: { color: 'rgba(0,0,0,0)' }, name: '90% band', hoverinfo: 'skip' };
    var exp = { x: w.t, y: w.expected, name: 'Expected', mode: 'lines', line: { color: C.expected, width: 2 }, hovertemplate: '%{y:.0f} tons<extra>Expected</extra>' };
    var act = { x: w.t, y: w.actual, name: 'Actual', mode: 'lines', line: { color: C.actual, width: 2 }, hovertemplate: '%{y:.0f} tons<extra>Actual</extra>' };
    var dots = { x: w.aboveX, y: w.aboveY, name: 'Above the band', mode: 'markers', marker: { color: '#B91C1C', size: 5 }, hoverinfo: 'skip' };
    var tmp = { x: w.t, y: w.temp, name: 'Outdoor temp (F)', mode: 'lines', yaxis: 'y2', line: { color: '#9AA3B8', width: 1, dash: 'dot' }, hovertemplate: '%{y:.0f} F<extra>Outdoor</extra>' };
    var L = base(undefined, 'Cooling (tons)');
    var narrow = window.innerWidth < 700;
    L.xaxis = { type: 'date', dtick: 864e5, tickformat: narrow ? '%a %-d' : '%a %b %-d', tickangle: 0, automargin: true, ticklabelmode: 'period', gridcolor: C.grid, tickfont: { size: narrow ? 10 : 13 } };
    L.yaxis2 = { title: { text: 'Outdoor temp (F)', standoff: 6 }, overlaying: 'y', side: 'right', showgrid: false, automargin: true };
    L.margin.r = 56; L.hovermode = 'x unified';
    Plotly.newPlot('chart-week', [band, exp, act, dots, tmp], L, { displayModeBar: false, responsive: true });
    var st = weekStats(b, cur.week);
    document.getElementById('wk-stats').innerHTML = '<strong>' + esc(weekLabel(b, cur.week)) + '</strong>: ' +
      (st.hrs ? st.ab + ' of ' + st.hrs + ' hours above the band; extra cooling ' + fmt(st.over) + ' ton-hours (' + st.pct.toFixed(1) + '% of this week\'s cooling).'
              : 'no usable readings this week.');
    document.getElementById('wk').value = cur.week;
    document.getElementById('wk-prev').disabled = cur.week <= 0;
    document.getElementById('wk-next').disabled = cur.week >= b.n_weeks - 1;
    drawDaily(b);
    history.replaceState(null, '', '#b=' + encodeURIComponent(b.id) + '&w=' + cur.week);
  }

  function drawDaily(b) {
    var d = b.daily, s0 = startMs(b), shapes = [], ann = [];
    var wa = new Date(s0 + cur.week * 7 * 864e5).toISOString().slice(0, 10), wz = new Date(s0 + (cur.week * 7 + 7) * 864e5).toISOString().slice(0, 10);
    shapes.push({ type: 'rect', xref: 'x', yref: 'paper', x0: wa, x1: wz, y0: 0, y1: 1, fillcolor: 'rgba(29,36,89,0.08)', line: { width: 0 } });
    if (b.onset) {
      shapes.push({ type: 'line', xref: 'x', yref: 'paper', x0: b.onset, x1: b.onset, y0: 0, y1: 1, line: { color: '#B91C1C', width: 1.5, dash: 'dash' } });
      ann.push({ x: b.onset, y: 1, yref: 'paper', text: 'Extra cooling began around here', showarrow: false, xanchor: 'left', yanchor: 'bottom', font: { size: 12, color: '#B91C1C' } });
    }
    var L = base(undefined, 'Extra cooling (ton-hours)'); L.margin.t = 40; L.shapes = shapes; L.annotations = ann;
    L.xaxis = { type: 'date', tickformat: '%b %-d', automargin: true, gridcolor: C.grid };
    var bars = { x: d.days, y: d.over, type: 'bar', marker: { color: C.cool }, name: 'Above the band', hovertemplate: '%{x|%b %-d}: %{y:,} ton-hours above the band<extra></extra>' };
    Plotly.newPlot('chart-daily', [bars], L, { displayModeBar: false, responsive: true });
    var el = document.getElementById('chart-daily');
    el.on('plotly_click', function (ev) {
      var day = Date.parse(ev.points[0].x.slice(0, 10) + 'T00:00:00Z');
      var k = Math.floor((day - startMs(b)) / (7 * 864e5));
      if (k >= 0 && k < b.n_weeks) { cur.week = k; drawWeek(b); }
    });
  }

  function drawHeat(b) {
    var ap = function (h) { var p = h < 12 ? 'a' : 'p', r = h % 12; if (r === 0) r = 12; return r + p; };
    var tv = [0, 3, 6, 9, 12, 15, 18, 21], hours = []; for (var i = 0; i < 24; i++) hours.push(i);
    var L = base('Hour of day', undefined);
    L.xaxis = { title: { text: 'Hour of day', standoff: 14 }, tickmode: 'array', tickvals: tv, ticktext: tv.map(ap), automargin: true };
    L.margin = { t: 20, r: 16, b: 60, l: 64 }; L.yaxis = { autorange: 'reversed', automargin: true };
    Plotly.newPlot('chart-heat', [{ z: b.heat, x: hours, y: DAYS, type: 'heatmap', colorscale: [[0, '#F1F8FB'], [0.5, '#4BAEC8'], [1, '#0B2F4F']], colorbar: { title: 'ton-hours' },
      hovertemplate: '%{y} %{x}:00: %{z:,} ton-hours above the band<extra></extra>' }], L, { displayModeBar: false, responsive: true });
  }
  function drawMonth(b) {
    var m = b.monthly, L = base(undefined, 'Cooling (ton-hours)'); L.barmode = 'group';
    Plotly.newPlot('chart-month', [{ x: m.months, y: m.actual, type: 'bar', name: 'Actual', marker: { color: C.actual } },
      { x: m.months, y: m.expected, type: 'bar', name: 'Expected', marker: { color: C.expected } }], L, { displayModeBar: false, responsive: true });
  }
  function drawScatter(b) {
    var ax = [], ay = [], bx = [], by = [];
    for (var i = 0; i < b.h.length; i++) { if (b.above[i]) { ax.push(b.wb_f[i]); ay.push(b.actual[i]); } else { bx.push(b.wb_f[i]); by.push(b.actual[i]); } }
    var L = base('Outdoor wet-bulb temperature (F)', 'Cooling (tons)'); L.hovermode = 'closest';
    Plotly.newPlot('chart-scatter', [
      { x: bx, y: by, mode: 'markers', name: 'Within the band', marker: { color: '#9AA3B8', size: 4, opacity: 0.5 } },
      { x: ax, y: ay, mode: 'markers', name: 'Above the band', marker: { color: '#B91C1C', size: 5, opacity: 0.7 } }], L, { displayModeBar: false, responsive: true });
  }

  function chips(b) {
    var items = [['Verdict', b.verdict], ['Status', b.status], ['Hours above band', b.above_pct == null ? '-' : b.above_pct + '%'],
      ['Extra cooling', b.excess_th ? fmt(b.excess_th) + ' ton-hours' : '-'], ['Extra, % of its cooling', b.excess_pct ? b.excess_pct + '%' : '-'],
      ['Model error (lower is better)', b.cv == null ? '-' : b.cv + '%']];
    if (b.cost) items.push(['Potential cost', '$' + fmt(b.cost)]);
    return '<div class="stats">' + items.map(function (x) { return '<div class="stat"><b>' + esc(x[1]) + '</b><span>' + esc(x[0]) + '</span></div>'; }).join('') + '</div>';
  }

  function render(id, week) {
    var b = D[id]; if (!b) return;
    cur.id = id; cur.week = Math.max(0, Math.min(b.n_weeks - 1, week == null ? b.worst_week : week));
    var opts = ''; for (var k = 0; k < b.n_weeks; k++) opts += '<option value="' + k + '">' + esc(weekLabel(b, k)) + (k === b.worst_week && b.excess_th ? ' (most extra cooling)' : '') + '</option>';
    var warn = b.verdict === "Can't judge" ? '<div class="warn"><strong>Can\'t judge this building.</strong> ' + esc(b.note || '').replace(/\.?$/, '.') + ' The band below is not reliable, so treat these charts as raw data.</div>' : '';
    var hint = b.hint_html ? '<div class="card"><h3>Where to look first</h3><p class="hint">Hints, not a diagnosis.</p>' + b.hint_html + '</div>' : '';
    var el = document.getElementById('detail-view');
    el.innerHTML =
      '<p><button class="btn" id="back">&larr; Back to results</button></p><h1>' + esc(b.name) + '</h1><p class="hint">' + esc(b.place) + '. Cooling is shown in tons (1 ton = 12,000 BTU per hour).</p>' +
      warn + chips(b) + hint +
      '<div class="card"><h3>Week by week: actual vs expected</h3><p class="hint">Expected is what the weather says this building should use. Outside the shaded 90% band means more (or less) than expected. Red dots are hours above the band.</p>' +
      '<div class="wknav"><button class="btn-outline" id="wk-prev">&larr; Previous week</button><select id="wk" aria-label="Week">' + opts + '</select>' +
      '<button class="btn-outline" id="wk-next">Next week &rarr;</button><button class="btn-outline" id="wk-worst">Jump to most extra cooling</button></div>' +
      '<p id="wk-stats" class="notebox"></p><div id="chart-week" class="chart" role="img" aria-label="Actual vs expected cooling for the selected week"></div></div>' +
      '<div class="card"><h3>Every day, at a glance</h3><p class="hint">Extra cooling above the band, per day. Click a bar to jump to that week. The shaded strip is the week above.</p><div id="chart-daily" class="chart short"></div></div>' +
      '<div class="card"><h3>When in the week does the extra happen? (ton-hours above the band)</h3><div id="chart-heat" class="chart short"></div></div>' +
      '<div class="card"><h3>Month by month: actual vs expected</h3><div id="chart-month" class="chart short"></div></div>' +
      '<div class="card"><h3>Cooling vs outdoor weather</h3><p class="hint">Each dot is one hour. Cooling normally rises with outdoor wet-bulb temperature (heat plus humidity). Red dots are above the band. If they sit at mild temperatures too, the extra is not just a hot-weather effect.</p><div id="chart-scatter" class="chart"></div></div>';
    document.body.classList.add('detail-open'); window.scrollTo(0, 0); setNav(true);
    document.getElementById('back').onclick = close;
    document.getElementById('wk-prev').onclick = function () { cur.week--; drawWeek(b); };
    document.getElementById('wk-next').onclick = function () { cur.week++; drawWeek(b); };
    document.getElementById('wk-worst').onclick = function () { cur.week = b.worst_week; drawWeek(b); };
    document.getElementById('wk').onchange = function () { cur.week = parseInt(this.value, 10); drawWeek(b); };
    drawWeek(b); drawHeat(b); drawMonth(b); drawScatter(b);
  }
  function setNav(open) {
    if (!navDetail) return;
    if (navCurrent) { if (open) navCurrent.removeAttribute('aria-current'); else navCurrent.setAttribute('aria-current', 'page'); }
    if (open) navDetail.setAttribute('aria-current', 'page'); else navDetail.removeAttribute('aria-current');
  }
  function close() { setNav(false); document.body.classList.remove('detail-open'); history.replaceState(null, '', location.pathname + location.search); window.scrollTo(0, 0); }

  document.addEventListener('click', function (e) {
    var a = e.target.closest ? e.target.closest('[data-b]') : null;
    if (a && D[a.getAttribute('data-b')]) { e.preventDefault(); render(a.getAttribute('data-b')); }
  });
  document.addEventListener('keydown', function (e) {
    if (!document.body.classList.contains('detail-open') || !cur.id) return;
    var b = D[cur.id];
    if (e.key === 'ArrowLeft' && cur.week > 0) { cur.week--; drawWeek(b); }
    if (e.key === 'ArrowRight' && cur.week < b.n_weeks - 1) { cur.week++; drawWeek(b); }
    if (e.key === 'Escape') close();
  });
  if (navDetail) navDetail.addEventListener('click', function (e) {
    if (ORDER.length) { e.preventDefault(); render(ORDER[0]); }
  });
  if (location.hash === '#detail' && ORDER.length) { render(ORDER[0]); return; }
  var m = /#b=([^&]+)(?:&w=(\d+))?/.exec(location.hash);
  if (m && D[decodeURIComponent(m[1])]) render(decodeURIComponent(m[1]), m[2] ? parseInt(m[2], 10) : null);
})();
