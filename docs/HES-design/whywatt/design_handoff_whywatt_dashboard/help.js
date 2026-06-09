/* Help popovers — anchored to any [data-help] trigger (the ? buttons).
   Sized to overlay the primary graphs; click-outside or Esc to close. */
(function () {
  const HELP = {
    'load': {
      title: 'Estimated electrical load',
      body: 'Current Load is your panel draw today. Journey Peak Load is the highest simultaneous draw once every planned upgrade is energized — it sets the service size you need. We flag it amber past 100&nbsp;A and red past 200&nbsp;A, where a panel upgrade is usually required.',
    },
    'chart-cumulative': {
      title: 'Cumulative energy cost',
      body: 'This adds up every year\u2019s bill from year&nbsp;1 onward. The crossover point — where the journey line dips below do-nothing — is your payback year. If the lines never cross, the plan doesn\u2019t pay back within your horizon.',
    },
    'chart-breakdown': {
      title: 'Cost by category',
      body: 'The stacked bands split each scenario\u2019s annual cost into electricity, gas, fuel, and (when enabled) social &amp; health costs. Use it to see which line item drives the gap between staying on gas and electrifying.',
    },
    'journey': {
      title: 'Your electrification journey',
      body: 'Sequence each appliance swap and set its plan year. Toggle an item off to keep it on gas. Open any device with the ⋮ menu to edit efficiency, sizing, and costs in detail.',
    },
    'home': {
      title: 'Home &amp; Solar',
      body: 'Your home\u2019s size, vintage, climate zone, and insulation set the baseline energy model. Add rooftop solar to size a system and model net metering against the journey.',
    },
    'energy': {
      title: 'Energy &amp; prices',
      body: 'Choose how electricity and gas prices escalate — a flat CAGR or California\u2019s Avoided Cost Calculator (ACC). The social &amp; health cost of gas adds the climate and air-quality price of combustion to the comparison.',
    },
    'about': {
      title: 'About WhyWatt?',
      body: 'WhyWatt? models the 20-year cost of electrifying your home versus keeping gas appliances. Every figure is an estimate — adjust the assumptions in the panels below to match your home and rates.',
    },
  };

  let open = null;
  function close() {
    if (open) { open.remove(); open = null; }
    document.removeEventListener('keydown', onKey, true);
  }
  function onKey(e) { if (e.key === 'Escape') close(); }

  function place(pop, btn) {
    const r = btn.getBoundingClientRect();
    const pw = pop.offsetWidth, ph = pop.offsetHeight;
    const m = 12;
    // prefer below-left of the trigger; clamp to viewport
    let left = r.right - pw;
    let top = r.bottom + 8;
    if (top + ph > window.innerHeight - m) top = Math.max(m, r.top - ph - 8);
    left = Math.min(Math.max(m, left), window.innerWidth - pw - m);
    pop.style.left = left + 'px';
    pop.style.top = top + 'px';
  }

  function show(btn) {
    const key = btn.getAttribute('data-help');
    const h = HELP[key];
    if (!h) return;
    close();
    const overlay = document.createElement('div');
    overlay.className = 'help-overlay';
    overlay.innerHTML = `
      <div class="help-pop" role="dialog" aria-label="${h.title}">
        <div class="hd">
          <span class="ic">?</span>
          <h4>${h.title}</h4>
          <button class="x" aria-label="Close"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg></button>
        </div>
        <div class="bd">${h.body}</div>
        <div class="ft"><a class="learn" href="#">Learn more
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg></a></div>
      </div>`;
    document.body.appendChild(overlay);
    open = overlay;
    const pop = overlay.querySelector('.help-pop');
    overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
    pop.querySelector('.x').addEventListener('click', close);
    place(pop, btn);
    document.addEventListener('keydown', onKey, true);
  }

  document.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-help]');
    if (btn) { e.preventDefault(); e.stopPropagation(); show(btn); }
  });
  window.__closeHelp = close;
})();
