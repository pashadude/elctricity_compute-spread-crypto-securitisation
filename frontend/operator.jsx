/* Power by Botozen - Operator / Research (admin-gated, backend-backed) */

const verdictColor = (l) => ({ EXECUTE: 'primary', REJECT: 'red', DEFER: 'amber', CHALLENGE: 'purple' }[l] || 'muted');

const VenueCard = ({ v }) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '13px 16px', borderRadius: '10px', background: THEME.bg.elevated, border: `1px solid ${THEME.border.subtle}`, gap: '12px' }}>
    <div style={{ minWidth: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '2px' }}>
        <span style={{ fontFamily: THEME.font.heading, fontSize: '14px', fontWeight: 700, color: THEME.text.primary }}>{v.name}</span>
        <span style={{ width: 7, height: 7, borderRadius: '50%', background: v.status === 'connected' ? THEME.primary[400] : THEME.amber[400], boxShadow: v.status === 'connected' ? `0 0 6px ${THEME.primary[400]}` : 'none' }}></span>
      </div>
      <div style={{ fontFamily: THEME.font.body, fontSize: '11.5px', color: THEME.text.muted, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{v.role}</div>
    </div>
    <MonoText style={{ fontSize: '11px', color: v.status === 'connected' ? THEME.text.secondary : THEME.amber[400] }}>{v.stat}</MonoText>
  </div>
);

const OperatorView = ({ snapshot }) => {
  const verdictRows = normalizeArray(readPath(snapshot, ['verdict_rollups', 'rows'], readPath(snapshot, ['verdicts', 'rows'], []))).slice(-12).reverse();
  const publicRows = normalizeArray(snapshot?.public_hedges);
  const directRows = normalizeArray(snapshot?.direct_inventory);
  const oracle = snapshot?.oracle || {};
  const venues = [
    { name: 'Public hedge marks', role: 'Yahoo/venue quote adapters for priced proxy legs', status: publicRows.length ? 'connected' : 'pending', stat: String(publicRows.length) },
    { name: 'Direct event refs', role: 'Polymarket, Kalshi, and IBKR forecast/watchlist references', status: directRows.length ? 'connected' : 'pending', stat: String(directRows.length) },
    { name: 'Oracle evidence', role: 'Opoint/Nebius evidence receipts for operator review only', status: oracle.latest_title ? 'connected' : 'pending', stat: oracle.latest_reason_code || 'watch' },
    { name: 'Arc/Circle gate', role: 'No settlement call unless judge.classify() returns EXECUTE', status: 'connected', stat: snapshot?.mode?.live_chain_enabled ? 'live' : 'dry' },
  ];
  const pnl = snapshot?.pnl || {};

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '6px' }}>
        <h2 style={{ fontFamily: THEME.font.heading, fontSize: '22px', fontWeight: 700, color: THEME.text.primary, margin: 0, letterSpacing: 0 }}>Operator &amp; Research</h2>
        <Badge color="purple">admin</Badge>
      </div>
      <p style={{ fontFamily: THEME.font.body, fontSize: '13.5px', color: THEME.text.muted, margin: '0 0 22px', maxWidth: '720px', lineHeight: 1.55 }}>
        This backend-only surface is hidden from normal investors. It shows why a package exists, what evidence adapters are active, and whether the judge gate has allowed any Arc action.
      </p>

      <SectionLabel>Backend venue state</SectionLabel>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '10px', marginTop: '12px', marginBottom: '24px' }}>
        {venues.map((v, i) => <VenueCard key={i} v={v} />)}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.4fr) minmax(260px, 0.8fr)', gap: '14px', alignItems: 'start' }}>
        <Card>
          <SectionLabel>Recent judge verdicts</SectionLabel>
          <p style={{ fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.muted, margin: '4px 0 10px' }}>
            Rejected rows are shown here only for operators. User and channel surfaces show grouped actionable packages instead.
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: '92px 1fr 150px 92px', gap: '12px', padding: '8px 10px', fontFamily: THEME.font.mono, fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.07em', color: THEME.text.muted }}>
            <span>Time</span><span>Leg</span><span>Reason</span><span style={{ textAlign: 'right' }}>Verdict</span>
          </div>
          {verdictRows.length === 0 ? (
            <div style={{ padding: '18px 10px', fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.muted }}>No backend verdict rows yet.</div>
          ) : verdictRows.map((v, i) => (
            <div key={i} style={{ display: 'grid', gridTemplateColumns: '92px 1fr 150px 92px', gap: '12px', padding: '9px 10px', borderRadius: '6px', alignItems: 'center', background: i % 2 === 0 ? THEME.bg.elevated + '50' : 'transparent', fontFamily: THEME.font.mono, fontSize: '11.5px' }}>
              <span style={{ color: THEME.text.muted }}>{v.last_seen ? new Date(Number(v.last_seen) * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '-'}</span>
              <span style={{ color: THEME.text.primary, fontFamily: THEME.font.body, fontSize: '12.5px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{v.leg_title || v.leg || v.instrument || v.surface || '-'}</span>
              <span style={{ color: THEME.text.muted, fontSize: '10.5px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{v.reason_code || v.reason || '-'}</span>
              <span style={{ textAlign: 'right' }}><Badge color={verdictColor(v.label || v.verdict)} style={{ fontSize: '10px', padding: '2px 7px' }}>{v.label || v.verdict || '-'}</Badge></span>
            </div>
          ))}
        </Card>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <Card>
            <SectionLabel>Runtime and PnL</SectionLabel>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', marginTop: '12px' }}>
              {[
                ['State', snapshot?.runtime?.state || 'unknown', THEME.text.primary],
                ['Live chain', snapshot?.mode?.live_chain_enabled ? 'enabled' : 'disabled', snapshot?.mode?.live_chain_enabled ? THEME.primary[400] : THEME.amber[400]],
                ['Visible jobs', pnl.wrapped_jobs || 0, THEME.text.primary],
                ['Executed verdicts', pnl.executed_verdicts || 0, THEME.primary[400]],
                ['Paper PnL', fmtSigned(pnl.paper_ticket_total_pnl_usdc || 0), Number(pnl.paper_ticket_total_pnl_usdc || 0) >= 0 ? THEME.primary[400] : THEME.red[400]],
                ['Reconciled trades', pnl.reconciled_trades || 0, THEME.text.secondary],
              ].map(([k, v, c], i) => (
                <div key={i} style={{ padding: '10px 12px', borderRadius: '6px', background: THEME.bg.elevated }}>
                  <div style={{ fontFamily: THEME.font.body, fontSize: '10.5px', color: THEME.text.muted, marginBottom: '3px' }}>{k}</div>
                  <MonoText style={{ fontSize: '14px', fontWeight: 700, color: c, overflowWrap: 'anywhere' }}>{v}</MonoText>
                </div>
              ))}
            </div>
          </Card>
          <Card>
            <SectionLabel>Guardrail</SectionLabel>
            <div style={{ fontFamily: THEME.font.body, fontSize: '12.5px', color: THEME.text.secondary, lineHeight: 1.55 }}>
              Account paper tickets never call Circle or Arc. Arc settlement remains locked until the premium scorer and <MonoText>judge.classify()</MonoText> return EXECUTE.
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
};

Object.assign(window, { OperatorView });
