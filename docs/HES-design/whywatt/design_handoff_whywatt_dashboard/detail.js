/* Device Details editor — shares the redesign's design system.
   Opens from the ⋮ button on each device row. Sliders update their
   inline value live; Net recomputes from Install − Rebate. */
(function () {
  const DATA = {
    'HVAC': {
      icon: '<path d="M12 3v18M3 12h18M5.6 5.6l12.8 12.8M18.4 5.6 5.6 18.4"/><circle cx="12" cy="12" r="2.4" fill="currentColor" stroke="none"/>',
      title: 'HVAC — Heating &amp; Cooling',
      sub: 'Gas furnace → Heat pump',
      start: ['Gas', 'Electric resistance', 'Heat pump (existing)'],
      year: { min: 2025, max: 2044, val: 2027 },
      size: { label: 'Heat pump size', val: 3.0, min: 1.5, max: 5, step: 0.5, dec: 1, suf: ' ton' },
      elec: '240 V · 30 A · 7,200 VA',
      current: {
        head: 'Current: Gas Furnace', cls: 'baseline',
        sum: '~<b>286 therms/yr</b> heating',
        sliders: [
          { label: 'Furnace AFUE', val: 0.80, min: 0.6, max: 0.98, step: 0.01, dec: 2, suf: '' },
          { label: 'Furnace age', val: 10, min: 0, max: 30, step: 1, dec: 0, suf: ' yrs' },
        ],
      },
      replace: {
        head: 'Replacement: Heat Pump HVAC', cls: 'journey',
        sum: '~<b>1919 kWh/yr</b> heat + <b>185 kWh/yr</b> cool = <b>2105 kWh/yr</b>',
        sliders: [
          { label: 'Heating COP', val: 3.5, min: 2, max: 5, step: 0.1, dec: 1, suf: '' },
          { label: 'Cooling SEER', val: 22, min: 13, max: 30, step: 1, dec: 0, suf: '' },
        ],
      },
      extra: { label: 'Has central AC (baseline)', checked: false },
      costs: { install: '14,000', rebate: '3,500' },
    },
    'Water Heater': {
      icon: '<rect x="6" y="3" width="12" height="18" rx="3"/><path d="M9 8h6M12 13v4"/>',
      title: 'Water Heater',
      sub: 'Gas tank → Heat-pump water heater',
      start: ['Gas tank', 'Electric resistance', 'Heat pump (existing)'],
      year: { min: 2025, max: 2044, val: 2029 },
      size: { label: 'Tank size', val: 50, min: 30, max: 80, step: 5, dec: 0, suf: ' gal' },
      elec: '240 V · 15 A · 3,600 VA',
      current: {
        head: 'Current: Gas Tank', cls: 'baseline',
        sum: '~<b>178 therms/yr</b> water heating',
        sliders: [
          { label: 'Tank UEF', val: 0.62, min: 0.5, max: 0.9, step: 0.01, dec: 2, suf: '' },
          { label: 'Tank age', val: 8, min: 0, max: 20, step: 1, dec: 0, suf: ' yrs' },
        ],
      },
      replace: {
        head: 'Replacement: HPWH', cls: 'journey',
        sum: '~<b>920 kWh/yr</b> at UEF 3.7',
        sliders: [
          { label: 'HPWH UEF', val: 3.7, min: 2.5, max: 4.5, step: 0.1, dec: 1, suf: '' },
          { label: 'First-hour rating', val: 63, min: 40, max: 90, step: 1, dec: 0, suf: ' gal' },
        ],
      },
      extra: { label: 'Shares mechanical closet (needs vent)', checked: true },
      costs: { install: '2,500', rebate: '500' },
    },
    'EV Charger': {
      icon: '<path d="M3 17V8a2 2 0 012-2h7a2 2 0 012 2v9"/><path d="M2 17h13"/><circle cx="5.5" cy="17.5" r="1.6"/><circle cx="11.5" cy="17.5" r="1.6"/><path d="M14 9h2.5L19 12v5h-5"/>',
      title: 'EV Charger',
      sub: 'Gasoline → Battery EV · Level 2 charging',
      start: ['No EV', 'Plug-in hybrid', 'Battery EV'],
      year: { min: 2025, max: 2044, val: 2031 },
      size: { label: 'Charger amperage', val: 40, min: 16, max: 50, step: 2, dec: 0, suf: ' A' },
      elec: '240 V · 40 A · 9,600 VA',
      current: {
        head: 'Current: Gasoline', cls: 'baseline',
        sum: '~<b>280 gal/yr</b> · 7,000 mi',
        sliders: [
          { label: 'Vehicle MPG', val: 28, min: 15, max: 55, step: 1, dec: 0, suf: '' },
          { label: 'Miles / yr (000s)', val: 7.0, min: 2, max: 25, step: 0.5, dec: 1, suf: 'k' },
        ],
      },
      replace: {
        head: 'Replacement: Battery EV', cls: 'journey',
        sum: '~<b>2,100 kWh/yr</b> home charging',
        sliders: [
          { label: 'Efficiency mi/kWh', val: 3.3, min: 2, max: 5, step: 0.1, dec: 1, suf: '' },
          { label: 'Home-charge share', val: 85, min: 30, max: 100, step: 5, dec: 0, suf: '%' },
        ],
      },
      extra: { label: 'Add L2 charger to the plan', checked: false },
      costs: { install: '1,180', rebate: '500' },
    },
  };

  function close() { document.getElementById('modal-root').innerHTML = ''; }
  const num = (s) => Number(String(s).replace(/[^0-9.]/g, '')) || 0;
  const comma = (n) => n.toLocaleString('en-US');

  function slider(s, i, side) {
    const out = `dout-${side}-${i}`;
    return `<div class="field dslider">
      <label>${s.label} <b class="mono" id="${out}">${s.val.toFixed(s.dec)}${s.suf}</b></label>
      <input type="range" class="slider" min="${s.min}" max="${s.max}" step="${s.step}" value="${s.val}"
        data-out="${out}" data-dec="${s.dec}" data-suf="${s.suf}" />
    </div>`;
  }

  window.openDetail = function (name) {
    const d = DATA[name];
    if (!d) return;
    const yr = d.year, planLabel = `Yr ${yr.val - 2024} · ${yr.val}`;
    const startOpts = d.start.map((o, i) => `<option ${i === 0 ? 'selected' : ''}>${o}</option>`).join('');
    const net = num(d.costs.install) - num(d.costs.rebate);

    document.getElementById('modal-root').innerHTML = `
      <div class="modal-scrim" onclick="if(event.target===this)__closeDetail()">
        <div class="modal modal-lg" role="dialog" aria-modal="true" aria-label="${name} details">
          <div class="modal-hd">
            <span class="ic"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${d.icon}</svg></span>
            <div style="flex:1"><h2>${d.title}</h2><div class="sub">${d.sub}</div></div>
            <button class="btn done" onclick="__closeDetail()">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>
              Done
            </button>
            <button class="iconbtn" onclick="__closeDetail()" title="Close"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg></button>
          </div>

          <div class="modal-bd" id="detail-bd">
            <div class="detail-top">
              <div class="field" style="max-width:230px">
                <label>Starting state</label>
                <select class="selectbox">${startOpts}</select>
              </div>
              <div class="plan-swap">
                <label class="check"><input type="checkbox" checked /><span class="box"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg></span><span class="lab">Plan swap</span></label>
                <div class="slider-wrap">
                  <input type="range" class="slider" min="${yr.min}" max="${yr.max}" value="${yr.val}" data-out="dout-year" data-planyear="1" />
                  <span class="slider-cap mono" id="dout-year">${planLabel}</span>
                </div>
              </div>
            </div>

            <div class="field dslider sizing">
              <label>${d.size.label} <b class="mono" id="dout-size">${d.size.val.toFixed(d.size.dec)}${d.size.suf}</b></label>
              <input type="range" class="slider" min="${d.size.min}" max="${d.size.max}" step="${d.size.step}" value="${d.size.val}"
                data-out="dout-size" data-dec="${d.size.dec}" data-suf="${d.size.suf}" />
            </div>

            <div class="elec-line">
              <span class="eyebrow">Electrical</span>
              <span class="mono">${d.elec}</span>
            </div>

            <div class="compare">
              <div class="cmp-col">
                <div class="cmp-head ${d.current.cls}">${d.current.head}</div>
                <div class="cmp-sum">${d.current.sum}</div>
                ${d.current.sliders.map((s, i) => slider(s, i, 'cur')).join('')}
              </div>
              <div class="cmp-col">
                <div class="cmp-head ${d.replace.cls}">${d.replace.head}</div>
                <div class="cmp-sum">${d.replace.sum}</div>
                ${d.replace.sliders.map((s, i) => slider(s, i, 'rep')).join('')}
              </div>
            </div>

            <label class="check extra-check"><input type="checkbox" ${d.extra.checked ? 'checked' : ''} /><span class="box"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg></span><span class="lab">${d.extra.label}</span></label>

            <div class="costs-panel">
              <span class="eyebrow">Costs &amp; Rebates</span>
              <div class="costs-row">
                <div class="field"><label>Install cost $</label><input class="input" id="d-install" value="${d.costs.install}" /></div>
                <div class="field"><label>Rebate $</label><input class="input" id="d-rebate" value="${d.costs.rebate}" /></div>
                <div class="net">Net <span class="mono" id="d-net">$${comma(net)}</span></div>
              </div>
            </div>
          </div>
        </div>
      </div>`;

    const bd = document.getElementById('detail-bd');
    bd.addEventListener('input', (e) => {
      const t = e.target;
      if (t.matches('.slider[data-out]')) {
        const o = document.getElementById(t.dataset.out);
        if (!o) return;
        if (t.dataset.planyear) {
          const y = Number(t.value);
          o.textContent = `Yr ${y - 2024} · ${y}`;
        } else {
          o.textContent = Number(t.value).toFixed(+t.dataset.dec) + (t.dataset.suf || '');
        }
      }
      if (t.id === 'd-install' || t.id === 'd-rebate') {
        const n = num(document.getElementById('d-install').value) - num(document.getElementById('d-rebate').value);
        document.getElementById('d-net').textContent = (n < 0 ? '−$' : '$') + comma(Math.abs(n));
      }
    });
  };
  window.__closeDetail = close;
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') { close(); window.__closeHelp && window.__closeHelp(); } });
})();
