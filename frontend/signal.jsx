/* Power by Botozen - Market Signal from backend snapshot */

const HeadlineSpread = ({ spread, stats }) => {
  const rm = REGIME_META[stats.regime] || REGIME_META.NEUTRAL;
  const history = normalizeArray(spread.history).length >= 2 ? spread.history : [1, 1];
  const min = Math.min(...history), max = Math.max(...history), range = max - min || 1;
  const yFor = (v) => 100 - ((v - min) / range) * 100;
  const meanY = yFor(stats.mean);
  const upY = yFor(stats.mean + stats.std), dnY = yFor(stats.mean - stats.std);

  return (
    <Card glow style={{ padding: '24px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '20px', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <SectionLabel style={{ marginBottom: '8px' }}>Backend spread signal</SectionLabel>
          <div style={{ fontFamily: THEME.font.mono, fontSize: '13px', color: THEME.text.secondary, overflowWrap: 'anywhere' }}>
            S_t = compute - k * (electricity / 1000) * kWh
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <Badge color={rm.color} style={{ fontSize: '12px', padding: '5px 12px' }}>{rm.label}</Badge>
          <div style={{ fontFamily: THEME.font.mono, fontSize: '11px', color: THEME.text.muted, marginTop: '6px' }}>k={spread.k} · kWh={spread.kwh}</div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '16px', marginBottom: '20px' }}>
        {[
          ['Electricity', stats.electricity ? fmtUsd(stats.electricity, 2) : 'pending', '$/MWh', THEME.amber[400]],
          ['Compute', stats.compute ? fmtUsd(stats.compute, 4) : 'pending', '$/GPU-hr', THEME.blue[400]],
          ['Spread mark', fmtNav(stats.cur), 'normalized NAV', THEME.primary[400]],
          ['Z-score', Number(stats.z || 0).toFixed(2), `std ${Number(stats.std || 0).toFixed(4)}`, Math.abs(stats.z) > 1.5 ? THEME.red[400] : Math.abs(stats.z) > 0.5 ? THEME.amber[400] : THEME.primary[400]],
        ].map(([k, v, u, c]) => (
          <div key={k}>
            <div style={{ fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.muted, marginBottom: '4px' }}>{k}</div>
            <MonoText style={{ fontSize: '18px', fontWeight: 700, color: c, overflowWrap: 'anywhere' }}>{v}</MonoText>
            <div style={{ fontFamily: THEME.font.mono, fontSize: '10px', color: THEME.text.faint, marginTop: '2px' }}>{u}</div>
          </div>
        ))}
      </div>

      <div style={{ position: 'relative', height: '118px', marginBottom: '8px', overflow: 'hidden' }}>
        <div style={{ position: 'absolute', left: 0, right: 0, top: `${upY}%`, borderTop: `1px dashed ${THEME.red[400]}40` }}>
          <span style={{ position: 'absolute', right: 0, top: '-13px', fontFamily: THEME.font.mono, fontSize: '9px', color: THEME.red[400] }}>+1s</span>
        </div>
        <div style={{ position: 'absolute', left: 0, right: 0, top: `${meanY}%`, borderTop: `1px dashed ${THEME.text.faint}` }}>
          <span style={{ position: 'absolute', right: 0, top: '-13px', fontFamily: THEME.font.mono, fontSize: '9px', color: THEME.text.muted }}>mean</span>
        </div>
        <div style={{ position: 'absolute', left: 0, right: 0, top: `${dnY}%`, borderTop: `1px dashed ${THEME.primary[400]}40` }}>
          <span style={{ position: 'absolute', right: 0, top: '-13px', fontFamily: THEME.font.mono, fontSize: '9px', color: THEME.primary[400] }}>-1s</span>
        </div>
        <Sparkline data={history} width={900} height={118} color={THEME.primary[400]} style={{ width: '100%', height: '118px' }} />
      </div>
      <div style={{ padding: '12px 14px', borderRadius: '8px', background: THEME.bg.elevated }}>
        <span style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.secondary, lineHeight: 1.5 }}>
          <strong style={{ color: THEME.text.primary }}>Current read:</strong> {rm.note}
        </span>
      </div>
    </Card>
  );
};

const SpreadFormCatalog = ({ rows }) => {
  const forms = normalizeArray(rows).length ? rows : DEFAULT_SPREAD_FORMS;
  return (
    <Card>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: '14px', gap: '12px' }}>
        <SectionLabel style={{ margin: 0 }}>Instrument map</SectionLabel>
        <span style={{ fontFamily: THEME.font.mono, fontSize: '11px', color: THEME.text.muted }}>{forms.length} backend spread forms</span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: '10px' }}>
        {forms.map((f, i) => (
          <div key={`${f.id}-${i}`} style={{ padding: '12px 14px', borderRadius: '8px', background: THEME.bg.elevated, border: `1px solid ${f.headline ? THEME.primary[400] + '40' : THEME.border.subtle}` }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '3px', flexWrap: 'wrap' }}>
              <span style={{ fontFamily: THEME.font.heading, fontSize: '13.5px', fontWeight: 700, color: THEME.text.primary }}>{f.name}</span>
              {f.headline && <Badge color="primary" style={{ fontSize: '9px', padding: '1px 6px' }}>active</Badge>}
            </div>
            <div style={{ fontFamily: THEME.font.body, fontSize: '11.5px', color: THEME.text.muted, lineHeight: 1.4 }}>{f.desc || f.status || 'Awaiting replay evidence.'}</div>
          </div>
        ))}
      </div>
    </Card>
  );
};

const VenueColumn = ({ title, sub, color, rows }) => (
  <Card style={{ padding: '20px' }}>
    <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: '14px', gap: '12px' }}>
      <div>
        <div style={{ fontFamily: THEME.font.heading, fontSize: '15px', fontWeight: 700, color: THEME.text.primary }}>{title}</div>
        <div style={{ fontFamily: THEME.font.mono, fontSize: '11px', color: THEME.text.muted }}>{sub}</div>
      </div>
      <span style={{ width: 9, height: 9, borderRadius: '50%', background: color }}></span>
    </div>
    <div>
      {normalizeArray(rows).length === 0 ? (
        <div style={{ padding: '18px 0', fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.muted }}>No backend rows available.</div>
      ) : rows.map((r, i) => {
        const change = Number(r.changePct || 0);
        const up = change >= 0;
        return (
          <div key={`${r.sym}-${i}`} style={{ display: 'grid', gridTemplateColumns: '1fr auto auto', gap: '12px', alignItems: 'center', padding: '8px 0', borderTop: i === 0 ? 'none' : `1px solid ${THEME.border.subtle}` }}>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontFamily: THEME.font.mono, fontSize: '11.5px', fontWeight: 600, color: THEME.text.primary, overflowWrap: 'anywhere' }}>{r.sym}</div>
              <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.muted, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.name}</div>
            </div>
            <MonoText style={{ fontSize: '12px', color: THEME.text.secondary, textAlign: 'right' }}>{typeof r.value === 'number' ? fmtUsd(r.value, r.value < 10 ? 4 : 2) : r.value}</MonoText>
            <span style={{ fontFamily: THEME.font.mono, fontSize: '11px', minWidth: '52px', textAlign: 'right', color: change === 0 ? THEME.text.muted : up ? THEME.primary[400] : THEME.red[400] }}>
              {change ? fmtPct(change, 1) : r.unit || '-'}
            </span>
          </div>
        );
      })}
    </div>
  </Card>
);

const SignalView = ({ spread, stats, indexCatalog }) => (
  <div>
    <h2 style={{ fontFamily: THEME.font.heading, fontSize: '22px', fontWeight: 700, color: THEME.text.primary, margin: '0 0 6px', letterSpacing: 0 }}>Market Signal</h2>
    <p style={{ fontFamily: THEME.font.body, fontSize: '13.5px', color: THEME.text.muted, margin: '0 0 22px', maxWidth: '780px', lineHeight: 1.55 }}>
      This page explains what the backend is trading or paper-tracking: a compute/energy spread mapped into syndicated instruments, priced proxy legs, and direct event or forecast references.
    </p>

    <div style={{ marginBottom: '14px' }}><HeadlineSpread spread={spread} stats={stats} /></div>
    <div style={{ marginBottom: '14px' }}><SpreadFormCatalog rows={indexCatalog?.spreadForms} /></div>

    <SectionLabel>Venue-visible evidence</SectionLabel>
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(290px, 1fr))', gap: '14px', marginTop: '12px' }}>
      <VenueColumn title="Priced public hedge legs" sub={`${normalizeArray(indexCatalog?.publicHedges).length} symbols from backend marks`} color={THEME.primary[400]} rows={indexCatalog?.publicHedges || []} />
      <VenueColumn title="Direct event / forecast refs" sub={`${normalizeArray(indexCatalog?.direct).length} slugs and contracts`} color={THEME.amber[400]} rows={indexCatalog?.direct || []} />
    </div>
  </div>
);

Object.assign(window, { SignalView, HeadlineSpread });
