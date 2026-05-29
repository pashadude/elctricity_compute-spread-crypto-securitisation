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

const statusTone = (value) => {
  const text = String(value || '').toUpperCase();
  if (text.includes('BUY') || text.includes('READY') || text.includes('PROMOTABLE') || text.includes('PASSED') || text.includes('ACTIVE')) return 'primary';
  if (text.includes('SELL') || text.includes('AVOID') || text.includes('FAILED')) return 'red';
  if (text.includes('PLANNED') || text.includes('WATCH') || text.includes('NEEDS') || text.includes('WAIT')) return 'amber';
  return 'muted';
};

const IndexCoveragePanel = ({ coverage }) => {
  const oosPass = coverage?.spread_archetypes?.oos_passed ?? coverage?.spread_archetypes?.oos_pass ?? 0;
  const familyLine = (counts) => Object.entries(counts || {})
    .sort((a, b) => b[1] - a[1])
    .map(([k, v]) => `${prettyLabel(k)} ${v}`)
    .join(' · ');
  const tradeLine = (counts) => Object.entries(counts || {})
    .sort((a, b) => b[1] - a[1])
    .map(([k, v]) => `${prettyLabel(k)} ${v}`)
    .join(' · ');
  const metrics = [
    ['Power indexes', `${coverage?.electricity?.usable || 0}/${coverage?.electricity?.total || 0}`, 'EIA, power, fuel, and grid scarcity marks'],
    ['Compute indexes', `${coverage?.compute?.usable || 0}/${coverage?.compute?.total || 0}`, 'GPU-hour, rental, capex, and utilization marks'],
    ['Spread forms', `${coverage?.spread_archetypes?.replayed || 0}/${coverage?.spread_archetypes?.total || 0}`, 'Oil-style relative-value forms with replay evidence'],
    ['OOS pass', `${oosPass}`, 'Out-of-sample replay checks before promotion'],
  ];
  return (
    <Card>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: '12px', flexWrap: 'wrap', marginBottom: '14px' }}>
        <div>
          <SectionLabel style={{ marginBottom: '6px' }}>Index coverage</SectionLabel>
          <div style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.secondary, lineHeight: 1.5 }}>
            {coverage?.summary || 'Backend index coverage is pending.'}
          </div>
        </div>
        <Badge color="muted">read-only inputs</Badge>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '10px' }}>
        {metrics.map(([label, value, note]) => (
          <div key={label} style={{ padding: '12px', borderRadius: '8px', background: THEME.bg.elevated, minWidth: 0 }}>
            <div style={{ fontFamily: THEME.font.body, fontSize: '11.5px', color: THEME.text.muted, marginBottom: '5px' }}>{label}</div>
            <MonoText style={{ display: 'block', fontSize: '17px', fontWeight: 800 }}>{value}</MonoText>
            <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.faint, lineHeight: 1.35, marginTop: '5px' }}>{note}</div>
          </div>
        ))}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '10px', marginTop: '10px' }}>
        {[
          ['Power families', familyLine(coverage?.electricity?.family_counts)],
          ['Compute families', familyLine(coverage?.compute?.family_counts)],
          ['Power tradeability', tradeLine(coverage?.electricity?.tradeability_counts)],
          ['Compute tradeability', tradeLine(coverage?.compute?.tradeability_counts)],
        ].map(([label, value]) => (
          <div key={label} style={{ padding: '10px 12px', borderRadius: '8px', background: THEME.bg.surface, border: `1px solid ${THEME.border.subtle}` }}>
            <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.muted, marginBottom: '4px' }}>{label}</div>
            <div style={{ fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.secondary, lineHeight: 1.35 }}>{value || 'No family buckets yet.'}</div>
          </div>
        ))}
      </div>
    </Card>
  );
};

const IndexList = ({ title, rows, accent }) => (
  <Card style={{ padding: '20px' }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', alignItems: 'baseline', marginBottom: '12px' }}>
      <div style={{ fontFamily: THEME.font.heading, fontSize: '15px', fontWeight: 800, color: THEME.text.primary }}>{title}</div>
      <span style={{ fontFamily: THEME.font.mono, fontSize: '11px', color: THEME.text.muted }}>{normalizeArray(rows).length} rows</span>
    </div>
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      {normalizeArray(rows).map(row => (
        <div key={row.id} style={{ padding: '10px 12px', borderRadius: '8px', background: THEME.bg.elevated, border: `1px solid ${THEME.border.subtle}` }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '10px', alignItems: 'flex-start' }}>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.primary, fontWeight: 700, overflowWrap: 'anywhere' }}>{row.label}</div>
              <div style={{ fontFamily: THEME.font.mono, fontSize: '10.5px', color: accent, marginTop: '2px', overflowWrap: 'anywhere' }}>{row.id}</div>
            </div>
            <Badge color={statusTone(row.status)} style={{ fontSize: '9.5px', padding: '2px 7px', whiteSpace: 'nowrap' }}>{prettyLabel(row.status)}</Badge>
          </div>
          <div style={{ fontFamily: THEME.font.body, fontSize: '11.5px', color: THEME.text.muted, lineHeight: 1.4, marginTop: '6px' }}>
            {row.role || row.description || 'Index row is registered but not yet wired to a live mark.'}
          </div>
          {row.copyRole && (
            <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.faint, lineHeight: 1.35, marginTop: '5px' }}>
              {row.copyRole}
            </div>
          )}
          {(row.source || row.unit || row.venue) && (
            <div style={{ display: 'flex', gap: '5px', flexWrap: 'wrap', marginTop: '8px' }}>
              {row.tradeabilityLabel && <Badge color={row.canMarkToMarket ? 'primary' : row.canBeDirectLeg ? 'amber' : 'muted'} style={{ fontSize: '9px', borderRadius: '6px' }}>{row.tradeabilityLabel}</Badge>}
              {(row.source || row.venue) && <Badge color="muted" style={{ fontSize: '9px', borderRadius: '6px' }}>{sourceLabel(row.source || row.venue)}</Badge>}
              {row.requiresPremiumGate && <Badge color="red" style={{ fontSize: '9px', borderRadius: '6px' }}>premium gate</Badge>}
              {row.requiresJudge && <Badge color="amber" style={{ fontSize: '9px', borderRadius: '6px' }}>judge required</Badge>}
              {row.unit && <Badge color="muted" style={{ fontSize: '9px', borderRadius: '6px' }}>{row.unit}</Badge>}
            </div>
          )}
        </div>
      ))}
    </div>
  </Card>
);

const ProfitabilityLedger = ({ ledger, rows }) => {
  const items = normalizeArray(rows);
  return (
    <Card>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', alignItems: 'baseline', flexWrap: 'wrap', marginBottom: '14px' }}>
        <div>
          <SectionLabel style={{ marginBottom: '6px' }}>Profitability ledger</SectionLabel>
          <div style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.secondary, lineHeight: 1.5 }}>
            {ledger?.realized_note || 'Replay and paper marks are scaled to mock notional; settled PnL only appears after closed positions or reconciled fills.'}
          </div>
        </div>
        <Badge color="amber">{items.length} spread rows</Badge>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '10px' }}>
        {items.slice(0, 8).map(row => {
          const tone = statusTone(row.status);
          const pnlText = row.latestPnl === null ? 'entry baseline' : fmtSigned(row.latestPnl);
          return (
            <div key={row.id || row.label} style={{ padding: '13px', borderRadius: '8px', background: THEME.bg.elevated, border: `1px solid ${tone === 'primary' ? THEME.primary[400] + '35' : THEME.border.subtle}` }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '10px', alignItems: 'flex-start', marginBottom: '7px' }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontFamily: THEME.font.heading, fontSize: '14px', fontWeight: 800, color: THEME.text.primary, overflowWrap: 'anywhere' }}>#{row.rank || '-'} {row.label}</div>
                  <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.muted, lineHeight: 1.35 }}>{row.oil_analogy || formName(row.archetype_id)}</div>
                </div>
                <Badge color={tone} style={{ fontSize: '9.5px', padding: '2px 7px' }}>{prettyLabel(row.status)}</Badge>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px', marginBottom: '8px' }}>
                {[
                  ['5d', fmtPct(row.paper5d, 1), row.paper5d >= 0],
                  ['1m', fmtPct(row.paper1m, 1), row.paper1m >= 0],
                  ['ticket', row.ticketPnl === null ? 'none' : fmtSigned(row.ticketPnl), Number(row.ticketPnl || 0) >= 0],
                ].map(([label, value, up]) => (
                  <div key={label}>
                    <div style={{ fontFamily: THEME.font.body, fontSize: '10px', color: THEME.text.muted, textTransform: 'uppercase' }}>{label}</div>
                    <MonoText style={{ fontSize: '12px', color: up ? THEME.primary[400] : THEME.red[400], overflowWrap: 'anywhere' }}>{value}</MonoText>
                  </div>
                ))}
              </div>
              <div style={{ fontFamily: THEME.font.mono, fontSize: '10.5px', color: row.latestPnl === null || row.latestPnl >= 0 ? THEME.primary[400] : THEME.red[400], marginBottom: '6px' }}>
                mark PnL: {pnlText} · OOS {prettyLabel(row.oosStatus || 'not run')}
              </div>
              <div style={{ fontFamily: THEME.font.body, fontSize: '11.5px', color: THEME.text.muted, lineHeight: 1.4 }}>
                {row.reason || 'Waiting for replay, venue pricing, or direct event evidence.'}
              </div>
              {(row.pricedSymbols.length || row.missingSymbols.length) > 0 && (
                <div style={{ display: 'flex', gap: '5px', flexWrap: 'wrap', marginTop: '9px' }}>
                  {row.pricedSymbols.slice(0, 4).map(sym => <Badge key={`${row.id}-${sym}`} color="muted" style={{ borderRadius: '6px', fontSize: '9px' }}>{sym}</Badge>)}
                  {row.missingSymbols.slice(0, 3).map(sym => <Badge key={`${row.id}-missing-${sym}`} color="amber" style={{ borderRadius: '6px', fontSize: '9px' }}>needs {sym}</Badge>)}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </Card>
  );
};

const TradingPathPanel = () => (
  <Card style={{ background: THEME.bg.surface }}>
    <SectionLabel>How a user trades it</SectionLabel>
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: '10px' }}>
      {[
        ['1. Account', 'The user creates an Operator account. The backend stores a signed HttpOnly session cookie and payer wallet; localStorage does not grant access.'],
        ['2. Paper ticket', 'Buy opens a server-side paper note against a backend instrument ID, not a real venue order. The wallet/account owns the ticket record.'],
        ['3. PnL marks', 'Open PnL is current backend NAV minus entry NAV, scaled by test-USDC notional. Closing writes realized paper PnL to the account ledger.'],
        ['4. Arc gate', 'Circle and Arc actions remain locked unless the runtime candidate is judged EXECUTE by judge.classify().'],
      ].map(([title, body]) => (
        <div key={title} style={{ padding: '12px', borderRadius: '8px', background: THEME.bg.elevated }}>
          <div style={{ fontFamily: THEME.font.heading, fontSize: '13px', color: THEME.text.primary, fontWeight: 800, marginBottom: '5px' }}>{title}</div>
          <div style={{ fontFamily: THEME.font.body, fontSize: '11.8px', color: THEME.text.muted, lineHeight: 1.45 }}>{body}</div>
        </div>
      ))}
    </div>
  </Card>
);

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

const GoalCoveragePanel = ({ coverage }) => {
  const items = normalizeArray(coverage?.items);
  const requirements = normalizeArray(coverage?.requirements);
  const tone = statusTone(coverage?.overall_status);
  return (
    <Card glow style={{ padding: '20px', marginBottom: '14px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: '12px', flexWrap: 'wrap', marginBottom: '14px' }}>
        <div>
          <SectionLabel style={{ marginBottom: '6px' }}>Goal coverage</SectionLabel>
          <div style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.secondary, lineHeight: 1.5 }}>
            {coverage?.summary || 'Backend coverage summary is pending.'}
          </div>
        </div>
        <Badge color={tone}>{coverage?.overall_status || 'NEEDS WORK'} · {Number(coverage?.overall_score || 0).toFixed(0)}%</Badge>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(205px, 1fr))', gap: '10px' }}>
        {items.map(item => (
          <div key={item.id} style={{
            padding: '12px',
            borderRadius: '8px',
            background: THEME.bg.elevated,
            border: `1px solid ${statusTone(item.status) === 'primary' ? THEME.primary[400] + '35' : THEME.border.subtle}`,
            minWidth: 0,
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'flex-start', marginBottom: '7px' }}>
              <div style={{ fontFamily: THEME.font.heading, fontSize: '13px', color: THEME.text.primary, fontWeight: 800, overflowWrap: 'anywhere' }}>{item.label}</div>
              <Badge color={statusTone(item.status)} style={{ fontSize: '9px', padding: '2px 6px' }}>{prettyLabel(item.status)}</Badge>
            </div>
            <MonoText style={{ display: 'block', fontSize: '11px', color: THEME.primary[400], marginBottom: '6px', overflowWrap: 'anywhere' }}>
              {item.metric}
            </MonoText>
            <div style={{ fontFamily: THEME.font.body, fontSize: '11.5px', color: THEME.text.muted, lineHeight: 1.4, marginBottom: '6px' }}>
              {item.evidence}
            </div>
            <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.faint, lineHeight: 1.35 }}>
              Next: {item.next_step}
            </div>
          </div>
        ))}
      </div>
      {coverage?.guardrail && (
        <div style={{ marginTop: '12px', padding: '10px 12px', borderRadius: '8px', background: THEME.bg.surface, fontFamily: THEME.font.body, fontSize: '11.5px', color: THEME.text.muted, lineHeight: 1.45 }}>
          {coverage.guardrail}
        </div>
      )}
      {requirements.length > 0 && (
        <div style={{ marginTop: '14px' }}>
          <SectionLabel style={{ marginBottom: '10px' }}>Requirement audit</SectionLabel>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))', gap: '10px' }}>
            {requirements.map(req => (
              <div key={req.id} style={{ padding: '12px', borderRadius: '8px', background: THEME.bg.surface, border: `1px solid ${THEME.border.subtle}` }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'flex-start', marginBottom: '7px' }}>
                  <div style={{ fontFamily: THEME.font.heading, fontSize: '12.5px', color: THEME.text.primary, fontWeight: 800, overflowWrap: 'anywhere' }}>{req.label}</div>
                  <Badge color={statusTone(req.status)} style={{ fontSize: '9px', padding: '2px 6px' }}>{prettyLabel(req.status)}</Badge>
                </div>
                <MonoText style={{ display: 'block', fontSize: '11px', color: THEME.primary[400], marginBottom: '6px' }}>{Number(req.score || 0).toFixed(0)}% proven</MonoText>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  {normalizeArray(req.evidence).slice(0, 3).map((line, i) => (
                    <div key={`${req.id}-e-${i}`} style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.muted, lineHeight: 1.35 }}>{line}</div>
                  ))}
                </div>
                {normalizeArray(req.gaps).length > 0 && (
                  <div style={{ fontFamily: THEME.font.body, fontSize: '10.5px', color: THEME.amber[400], lineHeight: 1.35, marginTop: '6px' }}>
                    Gap: {req.gaps[0]}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
};

const SignalView = ({ spread, stats, indexCatalog, goalCoverage }) => (
  <div>
    <h2 style={{ fontFamily: THEME.font.heading, fontSize: '22px', fontWeight: 700, color: THEME.text.primary, margin: '0 0 6px', letterSpacing: 0 }}>Market Signal</h2>
    <p style={{ fontFamily: THEME.font.body, fontSize: '13.5px', color: THEME.text.muted, margin: '0 0 22px', maxWidth: '780px', lineHeight: 1.55 }}>
      This page explains what the backend is trading or paper-tracking: a compute/energy spread mapped into syndicated instruments, priced proxy legs, and direct event or forecast references.
    </p>

    <GoalCoveragePanel coverage={goalCoverage} />
    <div style={{ marginBottom: '14px' }}><HeadlineSpread spread={spread} stats={stats} /></div>
    <div style={{ marginBottom: '14px' }}><TradingPathPanel /></div>
    <div style={{ marginBottom: '14px' }}><IndexCoveragePanel coverage={indexCatalog?.coverage} /></div>
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(290px, 1fr))', gap: '14px', marginBottom: '14px' }}>
      <IndexList title="Electricity indexes" rows={indexCatalog?.electricityIndexes} accent={THEME.amber[400]} />
      <IndexList title="Compute indexes" rows={indexCatalog?.computeIndexes} accent={THEME.blue[400]} />
    </div>
    <div style={{ marginBottom: '14px' }}><ProfitabilityLedger ledger={indexCatalog?.profitabilityLedger} rows={indexCatalog?.profitabilityRows} /></div>
    <div style={{ marginBottom: '14px' }}><SpreadFormCatalog rows={indexCatalog?.spreadForms} /></div>

    <SectionLabel>Venue-visible evidence</SectionLabel>
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(290px, 1fr))', gap: '14px', marginTop: '12px' }}>
      <VenueColumn title="Priced public hedge legs" sub={`${normalizeArray(indexCatalog?.publicHedges).length} symbols from backend marks`} color={THEME.primary[400]} rows={indexCatalog?.publicHedges || []} />
      <VenueColumn title="Direct event / forecast refs" sub={`${normalizeArray(indexCatalog?.direct).length} slugs and contracts`} color={THEME.amber[400]} rows={indexCatalog?.direct || []} />
    </div>
  </div>
);

Object.assign(window, { SignalView, HeadlineSpread, GoalCoveragePanel, IndexCoveragePanel, IndexList, ProfitabilityLedger });
