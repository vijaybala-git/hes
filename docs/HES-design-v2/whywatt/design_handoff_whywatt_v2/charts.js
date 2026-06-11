/* Lightweight SVG charts for the WhyWatt redesign reference.
   These mirror the real Plotly charts' intent with clean, on-brand styling. */
(function () {
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

  function pts(fn, n, w, h, pad) {
    const arr = [];
    for (let i = 0; i <= n; i++) {
      const x = pad.l + (i / n) * (w - pad.l - pad.r);
      const y = h - pad.b - fn(i / n) * (h - pad.t - pad.b);
      arr.push([x, y]);
    }
    return arr;
  }
  const path = (p) => p.map((q, i) => (i ? 'L' : 'M') + q[0].toFixed(1) + ' ' + q[1].toFixed(1)).join(' ');
  const area = (p, baseY) => path(p) + ' L' + p[p.length - 1][0].toFixed(1) + ' ' + baseY + ' L' + p[0][0].toFixed(1) + ' ' + baseY + ' Z';

  function lineChart(el) {
    const W = 560, H = 340, pad = { l: 52, r: 16, t: 16, b: 40 };
    const journey = (t) => 0.06 + 0.82 * t * t;
    const baseline = (t) => 0.06 + 0.78 * t * t;
    const jSocial = (t) => 0.06 + 0.95 * t * t;
    const bSocial = (t) => 0.06 + 1.18 * t * t;
    const clampTop = (fn) => (t) => Math.min(0.96, fn(t));
    const baseY = H - pad.b;

    const yTicks = [0, 30, 60, 90, 120];
    const grid = yTicks.map((v, i) => {
      const y = baseY - (v / 120) * (H - pad.t - pad.b);
      return `<line class="grid-line" x1="${pad.l}" y1="${y}" x2="${W - pad.r}" y2="${y}"/>
              <text x="${pad.l - 8}" y="${y + 3}" text-anchor="end" font-size="10">$${v}k</text>`;
    }).join('');
    const xTicks = [0, 5, 10, 15, 20];
    const xg = xTicks.map((v) => {
      const x = pad.l + (v / 20) * (W - pad.l - pad.r);
      return `<text x="${x}" y="${H - pad.b + 18}" text-anchor="middle" font-size="10">${v}</text>`;
    }).join('');

    el.innerHTML = `
      <svg class="svg-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Cumulative energy cost over 20 years">
        ${grid}${xg}
        <text class="axis-label" x="${pad.l + (W - pad.l - pad.r) / 2}" y="${H - 4}" text-anchor="middle" font-size="11">Year</text>
        <path d="${path(pts(clampTop(jSocial), 40, W, H, pad))}" fill="none" stroke="${css('--journey-line')}" stroke-width="1.6" stroke-dasharray="2 4" opacity="0.7"/>
        <path d="${path(pts(clampTop(bSocial), 40, W, H, pad))}" fill="none" stroke="${css('--baseline-line')}" stroke-width="1.6" stroke-dasharray="2 4" opacity="0.7"/>
        <path d="${path(pts(baseline, 40, W, H, pad))}" fill="none" stroke="${css('--baseline')}" stroke-width="2.6"/>
        <path d="${path(pts(journey, 40, W, H, pad))}" fill="none" stroke="${css('--journey')}" stroke-width="2.6"/>
      </svg>
      <div class="legend">
        <span class="li"><span class="sw" style="background:${css('--baseline')}"></span>Do nothing</span>
        <span class="li"><span class="sw" style="background:${css('--journey')}"></span>Your journey</span>
        <span class="li" style="color:${css('--baseline-line')}"><span class="sw dash"></span>Do nothing + social</span>
        <span class="li" style="color:${css('--journey-line')}"><span class="sw dash"></span>Your journey + social</span>
      </div>`;
  }

  function stackChart(el) {
    const W = 560, H = 340, pad = { l: 50, r: 14, t: 26, b: 40 };
    const plotTop = pad.t, plotBot = H - pad.b;
    const plotH = plotBot - plotTop;
    const YMAX = 120; // $k axis, shared
    const N = 40;

    // Build one stacked-area panel inside an explicit [x0, x0+w] box.
    function panel(x0, w, title, bands) {
      // cumulative stacked totals at each sample ($k). SCALE lifts the unit
      // band weights so the stack fills the 0–120 axis.
      const SCALE = 48;
      const cum = [];
      for (let b = 0; b < bands.length; b++) {
        const prev = b === 0 ? () => 0 : cum[b - 1];
        cum.push((t) => prev(t) + bands[b].w * SCALE * (0.05 + 0.95 * t * t));
      }
      // map a value v ($k) -> y, and sample index -> x within this panel
      const xAt = (i) => x0 + (i / N) * w;
      const yAt = (v) => plotBot - (v / YMAX) * plotH;

      let out = `<text x="${x0 + w / 2}" y="16" text-anchor="middle" font-size="10.5" class="axis-label" font-weight="600">${title}</text>`;
      // draw top band first (furthest back) down to baseline overdraw
      for (let b = bands.length - 1; b >= 0; b--) {
        let d = `M ${xAt(0).toFixed(1)} ${yAt(cum[b](0)).toFixed(1)}`;
        for (let i = 1; i <= N; i++) d += ` L ${xAt(i).toFixed(1)} ${yAt(cum[b](i / N)).toFixed(1)}`;
        d += ` L ${xAt(N).toFixed(1)} ${plotBot} L ${xAt(0).toFixed(1)} ${plotBot} Z`;
        out += `<path d="${d}" fill="${css(bands[b].c)}" opacity="0.92"/>`;
      }
      // year axis ticks
      [0, 10, 20].forEach((yr) => {
        out += `<text x="${xAt((yr / 20) * N).toFixed(1)}" y="${plotBot + 16}" text-anchor="middle" font-size="9">${yr}</text>`;
      });
      return out;
    }

    const doNothing = [
      { c: '--surface-3', w: 0.55 }, { c: '--ink-4', w: 0.4 },
      { c: '--warn', w: 0.55 }, { c: '--baseline', w: 0.75 },
    ];
    const journeyS = [
      { c: '--journey-soft', w: 0.5 }, { c: '--journey', w: 0.62 },
      { c: '--warn', w: 0.28 }, { c: '--baseline', w: 0.32 },
    ];

    const grid = [0, 40, 80, 120].map((v) => {
      const y = plotBot - (v / YMAX) * plotH;
      return `<line class="grid-line" x1="${pad.l}" y1="${y}" x2="${W - pad.r}" y2="${y}"/>
              <text x="${pad.l - 8}" y="${y + 3}" text-anchor="end" font-size="10">$${v}k</text>`;
    }).join('');

    const gap = 22;
    const halfW = (W - pad.l - pad.r - gap) / 2;
    el.innerHTML = `
      <svg class="svg-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Cost breakdown by category">
        ${grid}
        ${panel(pad.l, halfW, 'Do Nothing', doNothing)}
        ${panel(pad.l + halfW + gap, halfW, 'Your Journey', journeyS)}
      </svg>
      <div class="legend">
        <span class="li"><span class="sw" style="background:${css('--surface-3')}"></span>Baseload</span>
        <span class="li"><span class="sw" style="background:${css('--journey')}"></span>Water &amp; heating</span>
        <span class="li"><span class="sw" style="background:${css('--warn')}"></span>Climate cost</span>
        <span class="li"><span class="sw" style="background:${css('--baseline')}"></span>Health cost</span>
      </div>`;
  }

  function render() {
    const c1 = document.getElementById('chart1');
    const c2 = document.getElementById('chart2');
    if (c1) lineChart(c1);
    if (c2) stackChart(c2);
  }
  window.__renderCharts = render;
  if (document.readyState !== 'loading') render();
  else document.addEventListener('DOMContentLoaded', render);
})();
