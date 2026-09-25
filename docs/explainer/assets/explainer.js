/* WhyWatt? HEX explainer — shared shell, system map and chart helpers.
   Each page sets <body data-root="../" data-page="climate">; this script draws the masthead,
   side nav, locator and pager around the page's own <main> content. */
(function(){
const ROOT = document.body.dataset.root || '';
const PAGE = document.body.dataset.page || 'overview';
const ALL  = SITE.flatMap(g => g.pages.map(p => ({...p, grp:g.grp})));
const byId = id => ALL.find(p => p.id === id);
const cur  = byId(PAGE) || ALL[0];
const APPS = SITE.find(g => g.grp === 'Appliances').pages.filter(p => p.id !== 'apps');

/* ── Masthead + "Show code" switch ── */
const store = {
  get(k){ try{ return localStorage.getItem(k); }catch(e){ return null; } },
  set(k,v){ try{ localStorage.setItem(k,v); }catch(e){} },
};
function mast(){
  const tabs = [['System map','overview','Start'],['Pipelines','climate','Offline pipelines'],
                ['Engine','loop','Engine'],['Appliances','apps','Appliances'],['Charts','charts','Outputs']];
  const h = document.createElement('header'); h.className = 'mast';
  h.innerHTML = `<a class="brand" href="${ROOT}index.html"><div class="mark"></div><div><div class="brandname"><b>WhyWatt?</b> HEX</div><div class="brandsub">Home Electrification Explorer · how it works</div></div></a>
    <nav class="topnav">${tabs.map(([l,id,g]) => { const p = byId(id);
      return `<a href="${p.built ? ROOT + p.href : '#'}" class="${cur.grp === g ? 'on' : ''}" ${p.built ? '' : 'aria-disabled="true" title="coming soon"'}>${l}</a>`; }).join('')}
      <button class="codebtn" id="codebtn" aria-pressed="false" title="Show the source files behind each part">&lt;/&gt; Show code</button></nav>`;
  document.body.prepend(h);
  const btn = h.querySelector('#codebtn');
  const apply = on => { document.body.classList.toggle('show-code', on); btn.setAttribute('aria-pressed', on);
                        btn.innerHTML = on ? '&lt;/&gt; Hide code' : '&lt;/&gt; Show code'; };
  apply(store.get('ww-show-code') === '1');
  btn.onclick = () => { const on = !document.body.classList.contains('show-code'); apply(on); store.set('ww-show-code', on ? '1' : '0'); };
}

/* ── SVG helpers ── */
const C = {ink:'#16202e',slate:'#5a6b7e',mute:'#8a98a8',line:'#dfe5ec',paper:'#fbfcfe',cream:'#f4f7fb',j:'#1f5fbf',jl:'#7fa6e3',n:'#c8553d',s:'#0f8a6f',cl:'#b7791f',pr:'#6b4fb3'};
const soft = h => h + '18';
const txt = (x,y,s,cls='t-title',anchor='start') => `<text x="${x}" y="${y}" class="${cls}" text-anchor="${anchor}">${s}</text>`;
function node(id,kind,x,y,w,h,title,sub,color=C.ink,layer=''){
  let shape;
  if(kind==='input'){const k=12;shape=`<polygon points="${x+k},${y} ${x+w},${y} ${x+w-k},${y+h} ${x},${y+h}" fill="#fff" stroke="${C.ink}" stroke-width="1.5"/>`;}
  else if(kind==='store'){const r=7;shape=`<path class="body" d="M${x},${y+r} a${w/2},${r} 0 0 0 ${w},0 a${w/2},${r} 0 0 0 -${w},0 v${h-2*r} a${w/2},${r} 0 0 0 ${w},0 v-${h-2*r}" fill="${soft(color)}" stroke="${color}" stroke-width="1.5"/>`;}
  else if(kind==='source'){shape=`<path class="body" d="M${x},${y} h${w-12} l12,12 v${h-12} h-${w} z" fill="${soft(color)}" stroke="${color}" stroke-width="1.5"/><path d="M${x+w-12},${y} v12 h12" fill="none" stroke="${color}" stroke-width="1.2"/>`;}
  else if(kind==='planned'){shape=`<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="9" fill="#fff" stroke="${color}" stroke-width="1.5" stroke-dasharray="4 3"/>`;}
  else {shape=`<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="9" fill="${kind==='proc'?'#fff':soft(color)}" stroke="${color}" stroke-width="1.5"/>`;}
  const ty = h>100 ? y+22 : sub ? y+h/2-3 : y+h/2+4;
  const tx = kind==='input' ? x+18 : x+12;
  return `<g class="node" data-id="${id}" ${layer?`data-layer="${layer}"`:''}>${shape}${txt(tx,ty,title)}${sub?txt(tx,ty+15,sub,'t-sub'):''}</g>`;
}
function frame(x,y,w,h,label,color=C.slate,fill='none',id='',layer=''){
  return `<g ${id?`class="node" data-id="${id}"`:''} ${layer?`data-layer="${layer}"`:''}><rect x="${x}" y="${y}" width="${w}" height="${h}" rx="12" fill="${fill}" stroke="${color}" stroke-width="1.4"/>
   <rect x="${x+10}" y="${y-9}" width="${label.length*6.3+14}" height="18" rx="4" fill="#fff" stroke="${color}" stroke-width="1"/>${txt(x+17,y+4,label,'t-frame')}</g>`;
}
const MK = {ink:C.ink,j:C.j,n:C.n,s:C.s,cl:C.cl,pr:C.pr,slate:C.slate};
const arrowDefs = () => '<defs>'+Object.entries(MK).map(([k,v])=>`<marker id="ar-${k}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="${v}"/></marker>`).join('')+'</defs>';
const edge = (d,col,key,label,lx,ly,dash='',layer='') => `<g ${layer?`data-layer="${layer}"`:''}><path class="edge" d="${d}" stroke="${col}" ${dash?`stroke-dasharray="${dash}"`:''} marker-end="url(#ar-${key})"/>${label?`<text x="${lx}" y="${ly}" class="mono" font-size="10" style="fill:${col}">${label}</text>`:''}</g>`;
const ctrl  = (d,layer='') => `<path class="ctrl" d="${d}" marker-end="url(#ar-ink)" ${layer?`data-layer="${layer}"`:''}/>`;
const badge = (x,y,n) => `<g class="step-badge"><circle cx="${x}" cy="${y}" r="10"/><text x="${x}" y="${y+3.5}" text-anchor="middle">${n}</text></g>`;
/* Marker ids must be unique per SVG, or arrowheads vanish when the first SVG is hidden. */
let svgSeq = 0;
const uniq = svg => { const p = 'm' + (++svgSeq) + '-'; return svg.replaceAll('ar-', p + 'ar-'); };

/* ── The system map ── links:false for the small locator (it is itself a link) */
function blueprintSVG({links=true}={}){
  let s=`<svg viewBox="0 0 1200 660" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="WhyWatt? HEX system map">${arrowDefs()}`;
  [['INPUTS · you',20],['OFFLINE PIPELINES · built once, looked up by ZIP',250],['ENGINE · one step per year',620],['OUTPUTS',1000]].forEach(([l,x])=>s+=txt(x,26,l,'t-tag'));
  // inputs
  s+=node('in-home','input',20,48,190,48,'Home profile','bedrooms · sq ft · insulation',C.ink,'L1');
  s+=node('in-journey','input',20,108,190,48,'Journey plan','swap year · cost · rebate',C.ink,'L1');
  s+=node('in-zip','input',20,300,190,48,'ZIP code','→ zone · utility · sun',C.ink,'L1');
  s+=node('in-solar','input',20,436,190,48,'Solar · Battery · Panel','kW · kWh · amps',C.ink,'L1');
  s+=node('in-rate','input',20,560,190,48,'Rate plan · Projection','E-TOU-C · Moderate…',C.ink,'L1');
  // offline pipelines — each lane lines up with the engine level it feeds
  s+=node('p-proj','source',250,146,300,56,'Rate projection  S[y]/S[2025]','CEC 2025 IEPR forecasts → growth curve',C.pr,'L3');
  s+=node('p-climate','source',250,238,300,56,'Climate  HDD · CDD · water °F','TMYx typical year per CEC zone  (12,)',C.cl,'L2');
  s+=node('p-load','source',250,372,300,52,'Load profiles  (12×24)','NREL ResStock · zone × end use × month',C.s,'L5');
  s+=node('p-solar','source',250,434,300,52,'Solar yield  PVWatts','per kW · monthly + hourly shape',C.s,'L5');
  s+=node('p-rates','source',250,520,300,56,'Tariffs · current energy rate','URDB TOU → EIA utility → EIA Pacific',C.j,'L3');
  // ZIP fan-out
  s+=`<g data-layer="L2">`+edge('M210,324 C232,324 228,266 248,266',C.ink,'ink')+`</g>`;
  s+=`<g data-layer="L5">`+edge('M210,324 C232,324 228,398 248,398',C.ink,'ink')+edge('M210,324 C232,324 228,456 248,456',C.ink,'ink')+edge('M210,460 L248,462',C.ink,'ink')+`</g>`;
  s+=`<g data-layer="L3">`+edge('M210,324 C236,324 226,544 248,544',C.ink,'ink')+ctrl('M150,560 C170,540 220,560 248,556')+ctrl('M116,560 C150,300 200,180 248,176')+`</g>`;

  // engine
  s+=`<g data-layer="L4">`+frame(608,48,370,600,'Engine · runs once per home',C.ink,'#ffffffcc')+`</g>`;
  s+=`<g class="node" data-id="e-homes" data-layer="L4"><rect x="626" y="72" width="164" height="40" rx="8" fill="${soft(C.n)}" stroke="${C.n}" stroke-width="1.6"/>${txt(708,97,'Do nothing','t-title','middle')}
      <rect x="798" y="72" width="164" height="40" rx="8" fill="${soft(C.j)}" stroke="${C.j}" stroke-width="1.6"/>${txt(880,97,'Your journey','t-title','middle')}</g>`;
  s+=`<g data-layer="L4">`+txt(793,128,'same steps run for both homes ↓','t-sub','middle')+`</g>`;
  s+=frame(624,146,338,488,'for year in 1…N   (default 20)',C.pr,'none','e-year','L3');
  // the nine appliances, center stage
  s+=frame(640,196,306,160,'the 9 appliances → 12 monthly values each',C.ink,'#fff','e-slot','L4');
  const tileCol = a => a.lod===4 ? C.s : a.id==='panel' ? C.slate : C.j;
  s+=`<g data-layer="L4">`+APPS.map((a,i) => {
    const x = 652 + (i%3)*98, y = 212 + Math.floor(i/3)*38, col = tileCol(a);
    const g = `<g class="tile"><rect x="${x}" y="${y}" width="90" height="32" rx="7" fill="${soft(col)}" stroke="${col}" stroke-width="1.3"/>`+
      txt(x+45,y+15,a.t.replace(' & ',' &amp; '),'t-tile','middle')+
      `${[1,2,3,4].map(n=>`<rect x="${x+29+n*7}" y="${y+21}" width="5" height="3" rx="1" fill="${n<=a.lod?col:C.line}"/>`).join('')}</g>`;
    return links ? `<a href="${ROOT}appliances/index.html#${a.id}" aria-label="${a.t}">${g}</a>` : g;
  }).join('')+txt(793,344,'kWh or therms per month · click an appliance','t-sub','middle')+`</g>`;
  s+=node('e-hour','proc',640,372,306,118,'','',C.s,'L5');
  s+=`<g data-layer="L5" pointer-events="none">${txt(654,392,'Hourly energy balance · per month')}${txt(654,406,'electric only · representative day 12×24','t-sub')}
      ${[...Array(24)].map((_,h)=>{const v=[3,3,3,3,3,4,6,7,6,5,4,4,4,4,5,6,8,11,12,11,9,7,5,4][h];const sol=Math.max(0,Math.sin((h-6)/12*Math.PI))*11;return `<rect x="${660+h*11}" y="${482-v*5}" width="8" height="${v*5}" fill="${h>=16&&h<21?C.n:C.j}" opacity=".75"/><circle cx="${664+h*11}" cy="${482-sol*5}" r="${sol>0?2:0}" fill="${C.s}"/>`}).join('')}
      <text x="848" y="424" class="mono" font-size="9.5" style="fill:${C.n}">peak 4–9pm</text><text x="672" y="424" class="mono" font-size="9.5" style="fill:${C.s}">● solar</text></g>`;
  s+=node('e-cost','proc',640,508,306,60,'Cost  →  sum per category, once a year','− solar/battery saving · + CapEx in swap year',C.ink,'L6');
  s+=`<g data-layer="L3">`+txt(793,612,'↻ next year','t-frame','middle')+`</g>`;

  // pipeline → engine
  s+=edge('M550,174 L622,174',C.pr,'pr','× S[y]',566,168,'','L3');
  s+=edge('M550,266 L638,266',C.cl,'cl','(12,)',586,260,'','L2');
  s+=edge('M550,398 L638,398',C.s,'s','(12×24)',566,392,'','L5');
  s+=edge('M550,460 L638,460',C.s,'s','(12×24)',566,454,'','L5');
  s+=edge('M550,548 L638,538',C.j,'j','$/kWh · $/therm',556,566,'','L3');
  s+=edge('M596,548 C606,520 614,500 638,484',C.j,'j','TOU',600,512,'','L3');
  s+=edge('M210,72 L606,72',C.ink,'ink','appliance settings (UA, gallons…)',290,66,'','L1');
  s+=edge('M205,132 C400,132 420,90 606,92',C.ink,'ink','starting state · swap years',300,126,'','L1');
  s+=edge('M900,356 L900,370',C.j,'j','Σ electric kWh',822,367,'','L5');

  // outputs
  s+=node('o-collect','store',1000,250,180,70,'Year-by-year record','per year · both homes',C.ink,'L6');
  s+=node('o-charts','proc',1000,370,180,150,'Charts','',C.j,'L6');
  s+=`<g data-layer="L6" pointer-events="none">${['Cumulative cost','Annual cost','CapEx timeline','Rate curves R.1/R.2','Energy mix','Peak / off-peak R.6'].map((l,i)=>txt(1014,418+i*16,'▸ '+l,'t-sub')).join('')}</g>`;
  s+=edge('M946,538 C985,538 970,300 998,290',C.ink,'ink','',0,0,'','L6');
  s+=edge('M1090,320 L1090,368',C.ink,'ink','',0,0,'','L6');

  // control flow
  s+=`<g data-layer="L0">`+ctrl('M40,630 L60,630 C90,630 100,622 108,612')+txt(20,652,'Run ▶','t-frame')+badge(40,628,1)+txt(64,650,'resolve ZIP','t-frame')+`</g>`;
  s+=`<g data-layer="L0">`+ctrl('M230,610 C400,645 500,645 604,630')+badge(420,634,2)+txt(436,652,'build 2 homes','t-frame')+`</g>`;
  s+=`<g data-layer="L0">`+ctrl('M966,600 C990,620 1060,620 1090,528')+badge(1030,618,4)+txt(1046,640,'collect → render','t-frame')+badge(793,590,3)+`</g>`;
  return uniq(s+'</svg>');
}

/* ── Breakout drawer ── */
function drawer(el,id){
  const d = NODES[id]; if(!d) return;
  const pg = d.pg && byId(d.pg);
  el.innerHTML = `<span class="kind">${d.k}</span><h3>${d.t}</h3><p>${d.p}</p>`+
    (d.f?`<div class="sec">Formula / rule</div><div class="formula">${d.f}</div>`:'')+
    (d.s?`<div class="sec">Source</div><div class="chips">${d.s.map(x=>`<span class="chip src">${x}</span>`).join('')}</div>`:'')+
    (d.c?`<div class="sec code">Code</div><div class="chips code">${d.c.map(x=>`<span class="chip file">${x}</span>`).join('')}</div>`:'')+
    (pg ? (pg.built ? `<a class="go" href="${ROOT+pg.href}">Open: ${pg.t} →</a>` : `<span class="go soon">${pg.t} page · coming soon</span>`) : '');
}
function wireMap(canvasEl, drawerEl){
  canvasEl.innerHTML = blueprintSVG();
  canvasEl.addEventListener('click', e => {
    const g = e.target.closest('.node'); if(!g || e.target.closest('a')) return;
    canvasEl.querySelectorAll('.node.sel').forEach(n => n.classList.remove('sel'));
    g.classList.add('sel'); drawer(drawerEl, g.dataset.id);
  });
}

/* ── Detail-page chrome ── */
function side(){
  const el = document.getElementById('side'); if(!el) return;
  const loc = `<a class="locator dimmable dim" href="${ROOT}index.html" title="Back to the system map">${blueprintSVG({links:false})}<div class="loclbl">You are here ↗</div></a>`;
  const nav = SITE.filter(g => g.grp !== 'Start').map(g => `<div class="grp">${g.grp}</div>`+
    g.pages.map(p => `<a href="${p.built?ROOT+p.href:'#'}" class="${p.id===PAGE?'on':''} ${p.built?'':'soon'}">${p.t}</a>`).join('')).join('');
  el.innerHTML = loc + `<nav>${nav}</nav>`;
  const lit = cur.layers || [];
  el.querySelectorAll('[data-layer]').forEach(g => g.classList.toggle('lit', lit.includes(g.dataset.layer)));
}
function pager(){
  const el = document.getElementById('pager'); if(!el) return;
  const built = ALL.filter(p => p.built); const i = built.findIndex(p => p.id === PAGE);
  const prev = built[i-1], next = built[i+1];
  el.innerHTML = (prev?`<a href="${ROOT+prev.href}"><small>← ${prev.grp}</small>${prev.t}</a>`:'<span></span>')+
                 (next?`<a class="next" href="${ROOT+next.href}"><small>${next.grp} →</small>${next.t}</a>`:'<span></span>');
}
function meter(lod){ return `<div class="meter" title="level of detail ${lod}/4">${[1,2,3,4].map(n=>`<i class="${n<=lod?'f':''}"></i>`).join('')}</div>`; }

/* ── Chart helpers (small, dependency-free SVG) ──
   line(svg, {x:[labels], series:[{d,c,label,w,dash}], min, max, log, fmt, ticks, shade:[i0,i1,label], every}) */
function line(svg, o){
  const W=o.W||560, H=o.H||240, x0=o.x0||48, y0=16, w=W-x0-(o.right||14), h=H-y0-30, n=o.x.length;
  const vals = o.series.flatMap(s => s.d).filter(v => v!=null);
  let lo = o.min ?? Math.min(...vals), hi = o.max ?? Math.max(...vals);
  const f = o.log ? Math.log10 : (v => v); lo = f(lo); hi = f(hi);
  const X = i => x0 + (n===1?0:i*w/(n-1)), Y = v => y0 + h - (f(v)-lo)/(hi-lo)*h;
  const fmt = o.fmt || (v => v);
  let s = '';
  if(o.shade){ const [a,b,l] = o.shade; s += `<rect x="${X(a)}" y="${y0}" width="${X(b)-X(a)}" height="${h}" fill="${C.n}" opacity=".08"/>` + (l?txt((X(a)+X(b))/2,y0+12,l,'t-tag','middle'):''); }
  (o.ticks || [lo,(lo+hi)/2,hi].map(t => o.log ? 10**t : t)).forEach(t => s += `<line x1="${x0}" x2="${x0+w}" y1="${Y(t)}" y2="${Y(t)}" stroke="${C.line}"/>` + txt(x0-6,Y(t)+3,fmt(t),'t-tag','end'));
  o.series.forEach(se => {
    s += `<path d="${se.d.map((v,i) => v==null?'':(i&&se.d[i-1]!=null?'L':'M')+X(i)+','+Y(v)).join('')}" fill="none" stroke="${se.c}" stroke-width="${se.w||2.2}" ${se.dash?`stroke-dasharray="${se.dash}"`:''}/>`;
    if(se.label){ const i = se.at ?? n-1; s += `<text x="${X(i)+(se.at!=null?0:6)}" y="${Y(se.d[i])+(se.dy||4)}" class="mono" font-size="10" style="fill:${se.c}" ${se.at!=null?'text-anchor="middle"':''}>${se.label}</text>`; }
  });
  const every = o.every || 1;
  o.x.forEach((l,i) => { if(i%every===0 || i===n-1) s += txt(X(i),H-10,l,'t-tag','middle'); });
  svg.setAttribute('viewBox',`0 0 ${W} ${H}`); svg.innerHTML = s;
}
/* bars(svg, {x:[labels], series:[{d,c,label}], stacked, fmt, max}) */
function bars(svg, o){
  const W=o.W||460, H=o.H||210, x0=o.x0||44, y0=16, w=W-x0-10, h=H-y0-30, n=o.x.length, k=o.series.length;
  const tot = o.x.map((_,i) => o.stacked ? o.series.reduce((a,s)=>a+s.d[i],0) : Math.max(...o.series.map(s=>s.d[i])));
  const top = o.max || Math.max(1e-9, ...tot) * 1.08, fmt = o.fmt || (v => Math.round(v).toLocaleString('en-US'));
  const X = i => x0 + i*w/n, Y = v => y0 + h - v/top*h, slot = w/n - 6, bw = o.stacked ? slot : slot/k;
  let s = '';
  [0,.5,1].forEach(f => s += `<line x1="${x0}" x2="${x0+w}" y1="${Y(top*f)}" y2="${Y(top*f)}" stroke="${C.line}"/>` + txt(x0-6,Y(top*f)+3,fmt(top*f),'t-tag','end'));
  o.x.forEach((l,i) => {
    let base = 0;
    o.series.forEach((se,j) => { const v = se.d[i]; if(v>0){ const bx = X(i)+3+(o.stacked?0:j*bw), by = o.stacked ? Y(base+v) : Y(v);
      s += `<rect x="${bx}" y="${by}" width="${bw-(o.stacked?0:1)}" height="${(o.stacked?Y(base):Y(0))-by}" rx="1.5" fill="${se.c}"><title>${l}: ${fmt(v)}${se.label?' · '+se.label:''}</title></rect>`; }
      if(o.stacked) base += v; });
    s += txt(X(i)+w/n/2, H-10, l, 't-tag', 'middle');
  });
  if(o.series.some(se=>se.label)) o.series.forEach((se,j) => s += `<rect x="${x0+w-90*(k-j)}" y="${y0-6}" width="10" height="10" fill="${se.c}"/>` + txt(x0+w-90*(k-j)+14,y0+3,se.label,'t-frame'));
  svg.setAttribute('viewBox',`0 0 ${W} ${H}`); svg.innerHTML = s;
}
const MONTHS = ['J','F','M','A','M','J','J','A','S','O','N','D'];
const HOURS = [...Array(24).keys()].map(h => h+'h');
function zoneSelect(sel, ids, def='CZ4'){
  ids.forEach(([v,l]) => sel.insertAdjacentHTML('beforeend', `<option value="${v}" ${v.endsWith(def)&&!v.endsWith('1'+def)?'selected':''}>${l}</option>`));
}

/* Appliance-page helpers (need climate_zones.js / nrel_profiles.js loaded) */
function zoneOptions(sel, def='CZ4'){
  (window.ZONES||[]).forEach((z,i) => sel.insertAdjacentHTML('beforeend', `<option value="${i}" ${z.id===def?'selected':''}>${z.id} · ${z.city}</option>`));
}
/* NREL day shape for one end use: January and July, clock time (July +1 h daylight saving), peak shaded */
function nrelChart(svg, zoneId, eu, extra=[]){
  const p = (window.NREL||{})['CA_'+zoneId] || NREL.CA_CZ4, jan = p[eu].jan, jul = [p[eu].jul[23], ...p[eu].jul.slice(0,23)];
  const top = Math.max(...jan, ...jul, ...extra.flatMap(e=>e.d)) * 1.15;
  line(svg, {W:680, H:210, x0:44, x:HOURS, every:3, min:0, max:top, ticks:[0,top/2,top], fmt:v=>Math.round(v*100)+'%', shade:[16,21,'peak 4–9 pm'],
    series:[{d:jan, c:C.j, label:'Jan', at:jan.indexOf(Math.max(...jan)), dy:-8}, {d:jul, c:C.n, label:'Jul', at:jul.indexOf(Math.max(...jul)), dy:-8}, ...extra]});
  const pk = a => Math.round(a.slice(16,21).reduce((x,y)=>x+y,0)*100);
  return {janPeak: pk(jan), julPeak: pk(jul)};
}

window.WW = {C, soft, txt, node, frame, edge, ctrl, badge, arrowDefs, uniq, blueprintSVG, drawer, wireMap, meter, line, bars, MONTHS, HOURS, zoneSelect, zoneOptions, nrelChart, APPS, byId, ROOT};
mast(); side(); pager();
})();
