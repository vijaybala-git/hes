document.addEventListener('DOMContentLoaded', () => {
  // --- SLIDE NAVIGATION SYSTEM ---
  const wrapper = document.querySelector('.slides-wrapper');
  const slides = document.querySelectorAll('.slide');
  const prevBtn = document.getElementById('prev-btn');
  const nextBtn = document.getElementById('next-btn');
  const dotContainer = document.querySelector('.slide-dots');
  const progressBar = document.querySelector('.progress-bar');
  const currentSlideDisplay = document.getElementById('current-slide');
  const totalSlidesDisplay = document.getElementById('total-slide-num');

  let currentSlideIndex = 0;
  const totalSlides = slides.length;

  totalSlidesDisplay.textContent = totalSlides;

  // Create indicator dots dynamically
  slides.forEach((_, index) => {
    const dot = document.createElement('button');
    dot.classList.add('dot-btn');
    if (index === 0) dot.classList.add('active');
    dot.setAttribute('aria-label', `Go to slide ${index + 1}`);
    dot.addEventListener('click', () => goToSlide(index));
    dotContainer.appendChild(dot);
  });

  const dots = document.querySelectorAll('.dot-btn');

  function updateNavigation() {
    // Slide container transform
    wrapper.style.transform = `translateX(-${currentSlideIndex * 100}vw)`;

    // Active classes for animation triggers
    slides.forEach((slide, index) => {
      if (index === currentSlideIndex) {
        slide.classList.add('active');
      } else {
        slide.classList.remove('active');
      }
    });

    // Update buttons
    prevBtn.disabled = currentSlideIndex === 0;
    nextBtn.disabled = currentSlideIndex === totalSlides - 1;

    // Update dots
    dots.forEach((dot, index) => {
      if (index === currentSlideIndex) {
        dot.classList.add('active');
      } else {
        dot.classList.remove('active');
      }
    });

    // Update footer progress display
    currentSlideDisplay.textContent = currentSlideIndex + 1;

    // Update top progress bar
    const progressPercent = ((currentSlideIndex + 1) / totalSlides) * 100;
    progressBar.style.width = `${progressPercent}%`;

    // Special trigger: render chart when slide 1 is showing
    if (currentSlideIndex === 0) {
      updateAmbientChart();
    }
  }

  function goToSlide(index) {
    if (index >= 0 && index < totalSlides) {
      currentSlideIndex = index;
      updateNavigation();
    }
  }

  function nextSlide() {
    if (currentSlideIndex < totalSlides - 1) {
      goToSlide(currentSlideIndex + 1);
    }
  }

  function prevSlide() {
    if (currentSlideIndex > 0) {
      goToSlide(currentSlideIndex - 1);
    }
  }

  prevBtn.addEventListener('click', prevSlide);
  nextBtn.addEventListener('click', nextSlide);

  // Keyboard navigation listener
  document.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowRight' || e.key === ' ' || e.key === 'Enter') {
      // Don't intercept keypress if user is focusing a slider or input
      if (document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'SELECT') {
        e.preventDefault();
        nextSlide();
      }
    } else if (e.key === 'ArrowLeft') {
      if (document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'SELECT') {
        e.preventDefault();
        prevSlide();
      }
    }
  });

  // Initialize navigation state
  updateNavigation();


  // --- SLIDE 1: DYNAMIC AMBIENT ART (COST CURVES) ---
  const horizonSlider = document.getElementById('horizon-slider');
  const horizonVal = document.getElementById('horizon-val');
  const svgChart = document.getElementById('ambient-svg-chart');

  // Math models for curves: t goes 0 to 1 representing 0 to 30 years
  // Do Nothing cumulative costs (rises quadratically due to PG&E escalations)
  const baselineCostFn = (t) => 0.05 + 0.15 * t + 0.75 * t * t;
  // Your Journey cumulative costs (higher initial cap-ex, much lower operating cost slope)
  const journeyCostFn = (t) => 0.15 + 0.10 * t + 0.20 * t * t;
  // Social/health overlays
  const baselineSocialFn = (t) => baselineCostFn(t) + 0.35 * t;
  const journeySocialFn = (t) => journeyCostFn(t) + 0.06 * t;

  function updateAmbientChart() {
    if (!horizonSlider || !svgChart) return;
    
    const maxYears = parseInt(horizonSlider.value);
    horizonVal.textContent = `${maxYears} yrs`;

    const W = 600;
    const H = 340;
    const pad = { l: 55, r: 25, t: 30, b: 45 };
    const baseY = H - pad.b;
    const plotH = H - pad.t - pad.b;
    const plotW = W - pad.l - pad.r;

    // Total Y-scale is based on $100k maximum at 30 years
    const YMAX = 100; // in $k

    // Generate grid & text elements
    let elementsHtml = '';

    // Draw Y axis ticks (0 to 100k)
    [0, 25, 50, 75, 100].forEach((v) => {
      const y = baseY - (v / YMAX) * plotH;
      elementsHtml += `
        <line class="grid-line" x1="${pad.l}" y1="${y}" x2="${W - pad.r}" y2="${y}" stroke="#EBEDF1" stroke-width="1" />
        <text x="${pad.l - 10}" y="${y + 4}" text-anchor="end" fill="#838B99" font-family="monospace" font-size="10.5">$${v}k</text>
      `;
    });

    // Draw X axis ticks (every 5 years up to maxYears)
    const tickInterval = maxYears <= 10 ? 2 : (maxYears <= 20 ? 5 : 10);
    for (let yr = 0; yr <= maxYears; yr += tickInterval) {
      const t = yr / maxYears;
      const x = pad.l + t * plotW;
      elementsHtml += `
        <text x="${x}" y="${H - pad.b + 18}" text-anchor="middle" fill="#838B99" font-family="monospace" font-size="10.5">${yr}</text>
      `;
    }

    // X Axis Label
    elementsHtml += `
      <text x="${pad.l + plotW / 2}" y="${H - 8}" text-anchor="middle" fill="#5A6273" font-size="11" font-weight="600">Timeline (Years)</text>
    `;

    // Calculate points for the active horizon
    // Standard mapping: Year maxYears corresponds to t = maxYears / 30
    const maxT = maxYears / 30;

    function getPoints(fn) {
      const pts = [];
      const steps = 40;
      for (let i = 0; i <= steps; i++) {
        const stepT = (i / steps) * maxT; // from 0 to maxT
        const x = pad.l + (i / steps) * plotW;
        
        // Cost value in thousands of dollars
        const costVal = fn(stepT) * YMAX;
        const y = baseY - (costVal / YMAX) * plotH;
        pts.push([x, y]);
      }
      return pts;
    }

    const pathD = (pts) => pts.map((pt, i) => (i === 0 ? 'M' : 'L') + pt[0].toFixed(1) + ' ' + pt[1].toFixed(1)).join(' ');

    const baselinePts = getPoints(baselineCostFn);
    const journeyPts = getPoints(journeyCostFn);
    const baselineSocialPts = getPoints(baselineSocialFn);
    const journeySocialPts = getPoints(journeySocialFn);

    // Draw paths
    elementsHtml += `
      <!-- Do Nothing + Social -->
      <path d="${pathD(baselineSocialPts)}" class="curve" fill="none" stroke="#D2785F" stroke-width="1.8" stroke-dasharray="3 4" opacity="0.6" />
      
      <!-- Your Journey + Social -->
      <path d="${pathD(journeySocialPts)}" class="curve" fill="none" stroke="#3B6FD4" stroke-width="1.8" stroke-dasharray="3 4" opacity="0.6" />

      <!-- Do Nothing (Baseline) -->
      <path d="${pathD(baselinePts)}" class="curve" fill="none" stroke="#D2785F" stroke-width="2.8" />
      
      <!-- Your Journey -->
      <path d="${pathD(journeyPts)}" class="curve" fill="none" stroke="#3B6FD4" stroke-width="3" />
    `;

    // Check if payback is achieved inside the active horizon
    // Payback is where journey cost = baseline cost
    // Let's find the intersection point in years:
    // Solve baselineCostFn(t) = journeyCostFn(t)
    // 0.05 + 0.15t + 0.75t^2 = 0.15 + 0.10t + 0.20t^2
    // 0.55t^2 + 0.05t - 0.10 = 0
    // 11t^2 + t - 2 = 0 -> (t-0.383)(11t+...) -> t = 0.383
    // Year intersection = 0.383 * 30 = 11.5 years.
    const intersectionYr = 11.5;
    const paybackBadge = document.getElementById('payback-badge');
    const paybackYearText = document.getElementById('payback-year');

    if (maxYears >= intersectionYr) {
      paybackBadge.classList.add('show');
      paybackYearText.textContent = `Year 12`;
      
      // Draw intersection point
      const intersectionT = intersectionYr / maxYears;
      const interX = pad.l + intersectionT * plotW;
      const interY = baseY - (journeyCostFn(intersectionYr / 30) * YMAX / YMAX) * plotH;

      elementsHtml += `
        <circle cx="${interX}" cy="${interY}" r="6" fill="#2E9E73" stroke="#FFFFFF" stroke-width="2" />
        <circle cx="${interX}" cy="${interY}" r="12" fill="none" stroke="#2E9E73" stroke-width="1.5" opacity="0.5">
          <animate attributeName="r" values="6;16;6" dur="2s" repeatCount="indefinite"/>
          <animate attributeName="opacity" values="0.8;0;0.8" dur="2s" repeatCount="indefinite"/>
        </circle>
        <text x="${interX + 10}" y="${interY - 10}" fill="#1F805C" font-size="10" font-weight="700">Payback Point</text>
      `;
    } else {
      paybackBadge.classList.remove('show');
    }

    svgChart.innerHTML = elementsHtml;
  }

  if (horizonSlider) {
    horizonSlider.addEventListener('input', updateAmbientChart);
    updateAmbientChart();
  }


  // --- SLIDE 2: INTERACTIVE LAYOUT OVERVIEW ---
  const legendBtns = document.querySelectorAll('.interactive-legend .legend-btn');
  const overlays = document.querySelectorAll('.mockup-wrapper .highlight-overlay');
  const layoutDetailText = document.getElementById('layout-detail-text');

  const layoutDetails = {
    'verdict': 'The Cockpit integrates real-time status updates, detailing the financial payback year (e.g. +$41,644) and evaluating whether the total peak load falls within safe electrical panel limits.',
    'chart': 'The Two-Futures charts dynamically graph the cumulative cash flow over the chosen horizon, comparing the direct savings and external social (health + climate) impacts of electrification.',
    'devices': 'The Journey Grid lists planned replacements in two rows (Major Loads vs. Other Appliances). Each card provides configuration and timing sliders, displaying live capital net costs.'
  };

  function activateLayoutSection(sectionId) {
    // Remove active class from buttons and overlays
    legendBtns.forEach(btn => {
      if (btn.dataset.section === sectionId) btn.classList.add('active');
      else btn.classList.remove('active');
    });

    overlays.forEach(overlay => {
      if (overlay.id === `overlay-${sectionId}`) overlay.classList.add('active');
      else overlay.classList.remove('active');
    });

    // Update details card text
    if (layoutDetailText && layoutDetails[sectionId]) {
      layoutDetailText.textContent = layoutDetails[sectionId];
    }
  }

  legendBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      activateLayoutSection(btn.dataset.section);
    });
    btn.addEventListener('mouseenter', () => {
      activateLayoutSection(btn.dataset.section);
    });
  });

  // Activate default first section
  if (legendBtns.length > 0) {
    activateLayoutSection('verdict');
  }


  // --- HOTSPOT SYSTEM FOR SLIDES 3 & 4 ---
  const hotspots = document.querySelectorAll('.hotspot');
  
  const hotspotDetails = {
    // Slide 3 details
    'hotspot-swap': {
      title: 'Plan-Swap Toggle',
      desc: 'Controls whether the HVAC replacement is actively included in the journey calculation. Electrification planning helps avoid emergency gas replacements upon equipment failure.',
      theme: 'journey'
    },
    'hotspot-cop': {
      title: 'Coefficient of Performance (COP)',
      desc: 'Tuning the heating/cooling efficiency of the heat pump. A higher COP slider value (e.g., 3.5) directly translates to lower operational electric bills compared to fossil alternatives.',
      theme: 'amber'
    },
    'hotspot-cost': {
      title: 'Net-Cost Calculation Row',
      desc: 'Combines the equipment installation estimate with available rebates (such as Tech Clean California or IRA credits) to display the live capital outlay ($14k - $3.5k = $10.5k net).',
      theme: 'green'
    },
    // Slide 4 details
    'hotspot-ev': {
      title: 'EV Charger Configuration',
      desc: 'Configures charger types and annual mileage (e.g., 7,000 miles/yr). Adds roughly 3,540 kWh/yr load, modeled according to customized scheduling presets.',
      theme: 'journey'
    },
    'hotspot-cooktop': {
      title: 'Induction Cooktop Upgrade',
      desc: 'Tracks fuel swapping from gas to induction. Eliminates combustion gases, increases safety, and introduces a small, fast-response peak load to the panel.',
      theme: 'journey'
    },
    'hotspot-dryer': {
      title: 'Heat Pump Dryer',
      desc: 'Calculates savings from exchanging a gas dryer for a heat pump dryer, which uses a closed-loop heat exchanger to dry clothes using minimal electricity.',
      theme: 'journey'
    },
    'hotspot-panel': {
      title: 'Panel & Baseload Sizing Split',
      desc: 'Coordinates baseload consumption with panel sizing. Solara outputs warn or display peak amperage thresholds (e.g. 86A peaks) to confirm code compliance within a 200A limit.',
      theme: 'amber'
    }
  };

  hotspots.forEach(hotspot => {
    const detailCardId = hotspot.dataset.card;
    const cardEl = document.getElementById(detailCardId);
    
    function showHotspotInfo() {
      const key = hotspot.id;
      const data = hotspotDetails[key];
      if (!data || !cardEl) return;
      
      // Update card content
      cardEl.className = 'hotspot-card'; // reset classes
      if (data.theme) cardEl.classList.add(`hotspot-${data.theme}`);
      cardEl.classList.add('active');
      
      const titleEl = cardEl.querySelector('h5');
      const descEl = cardEl.querySelector('p');
      if (titleEl) titleEl.textContent = data.title;
      if (descEl) descEl.textContent = data.desc;
    }

    hotspot.addEventListener('mouseenter', showHotspotInfo);
    hotspot.addEventListener('click', showHotspotInfo);
  });

  // Activate default hotspots on load
  const hHVAC = document.getElementById('hotspot-swap');
  if (hHVAC) {
    // Trigger HVAC default
    const card = document.getElementById('hvac-detail-card');
    if (card) {
      card.querySelector('h5').textContent = hotspotDetails['hotspot-swap'].title;
      card.querySelector('p').textContent = hotspotDetails['hotspot-swap'].desc;
      card.classList.add('active');
    }
  }

  const hEV = document.getElementById('hotspot-ev');
  if (hEV) {
    // Trigger EV default
    const card = document.getElementById('family-detail-card');
    if (card) {
      card.querySelector('h5').textContent = hotspotDetails['hotspot-ev'].title;
      card.querySelector('p').textContent = hotspotDetails['hotspot-ev'].desc;
      card.classList.add('active');
    }
  }
});
