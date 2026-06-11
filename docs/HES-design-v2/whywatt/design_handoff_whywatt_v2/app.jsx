/* Tweaks app — palette / tone / density exploration.
   Applies data-* attributes to the root and re-renders charts on change. */
const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "palette": "default",
  "tone": "cool",
  "density": "regular"
}/*EDITMODE-END*/;

function applyTweaks(t) {
  const root = document.documentElement;
  if (t.palette === 'default') root.removeAttribute('data-palette');
  else root.setAttribute('data-palette', t.palette);
  if (t.tone === 'cool') root.removeAttribute('data-tone');
  else root.setAttribute('data-tone', t.tone);
  if (t.density === 'regular') root.removeAttribute('data-density');
  else root.setAttribute('data-density', t.density);
  if (window.__renderCharts) requestAnimationFrame(() => window.__renderCharts());
}

function TweaksApp() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  React.useEffect(() => { applyTweaks(t); }, [t]);
  return (
    <TweaksPanel title="Tweaks">
      <TweakSection label="Series palette" />
      <TweakColor label="Journey vs Baseline" value={t.palette}
        options={['default', 'electric', 'ink']}
        onChange={(v) => setTweak('palette', v)} />
      <div style={{ fontSize: 10.5, color: 'rgba(41,38,27,.5)', marginTop: -4 }}>
        default · electric · ink
      </div>
      <TweakSection label="Surface tone" />
      <TweakRadio label="Neutrals" value={t.tone}
        options={[{ value: 'cool', label: 'Cool' }, { value: 'neutral', label: 'Grey' }, { value: 'warm', label: 'Warm' }]}
        onChange={(v) => setTweak('tone', v)} />
      <TweakSection label="Density" />
      <TweakRadio label="Spacing" value={t.density}
        options={[{ value: 'regular', label: 'Balanced' }, { value: 'compact', label: 'Compact' }]}
        onChange={(v) => setTweak('density', v)} />
    </TweaksPanel>
  );
}

// The TweakColor chips show solid swatches; map palette names to representative
// 2-color pairs so the chips read as Journey/Baseline previews.
const PALETTE_PREVIEW = {
  'default': ['#4f6fb5', '#c2685f'],
  'electric': ['#2f9aa6', '#c79a4f'],
  'ink': ['#5256b0', '#7a8290'],
};
// Override TweakColor options to pass arrays (palette previews) while storing the name.
function TweaksAppWrapped() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  React.useEffect(() => { applyTweaks(t); }, [t]);
  const names = ['default', 'electric', 'ink'];
  return (
    <TweaksPanel title="Tweaks">
      <TweakSection label="Series palette" />
      <TweakRow label="Journey vs Baseline">
        <div className="twk-chips" role="radiogroup">
          {names.map((n) => {
            const on = t.palette === n;
            const [a, b] = PALETTE_PREVIEW[n];
            return (
              <button key={n} type="button" className="twk-chip" role="radio"
                aria-checked={on} data-on={on ? '1' : '0'} title={n}
                style={{ background: a }} onClick={() => setTweak('palette', n)}>
                <span><i style={{ background: b }} /></span>
              </button>
            );
          })}
        </div>
      </TweakRow>
      <div style={{ display: 'flex', gap: 6, fontSize: 9.5, color: 'rgba(41,38,27,.5)', textAlign: 'center', marginTop: -2 }}>
        {names.map((n) => <span key={n} style={{ flex: 1, textTransform: 'capitalize' }}>{n}</span>)}
      </div>
      <TweakSection label="Surface tone" />
      <TweakRadio label="Neutrals" value={t.tone}
        options={[{ value: 'cool', label: 'Cool' }, { value: 'neutral', label: 'Grey' }, { value: 'warm', label: 'Warm' }]}
        onChange={(v) => setTweak('tone', v)} />
      <TweakSection label="Density" />
      <TweakRadio label="Spacing" value={t.density}
        options={[{ value: 'regular', label: 'Balanced' }, { value: 'compact', label: 'Compact' }]}
        onChange={(v) => setTweak('density', v)} />
    </TweaksPanel>
  );
}

applyTweaks(TWEAK_DEFAULTS);
ReactDOM.createRoot(document.getElementById('modal-root').parentElement.appendChild(
  Object.assign(document.createElement('div'), { id: 'tweaks-root' })
)).render(<TweaksAppWrapped />);
