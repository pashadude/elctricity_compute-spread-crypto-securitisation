/* Power by Botozen - account-backed paper portfolio */

const sinceLabel = (ts) => {
  const stamp = Number(ts || 0);
  if (!stamp) return 'unknown';
  const s = Math.floor((Date.now() - stamp) / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60); if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60); if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
};

const PortfolioSummary = ({ summary }) => {
  const openNotional = Number(summary?.openNotionalUsdc || 0);
  const unreal = Number(summary?.unrealizedPnlUsdc || 0);
  const realizedTotal = Number(summary?.realizedPnlUsdc || 0);
  const net = Number(summary?.netPnlUsdc || 0);
  const cards = [
    { label: 'Open notional', value: fmtUsd(openNotional, 0), sub: `${summary?.openCount || 0} open`, color: THEME.text.primary },
    { label: 'Unrealized P&L', value: fmtSigned(unreal), sub: 'backend marked', color: unreal >= 0 ? THEME.primary[400] : THEME.red[400], live: true },
    { label: 'Realized P&L', value: fmtSigned(realizedTotal), sub: `${summary?.realizedCount || 0} closed`, color: realizedTotal >= 0 ? THEME.primary[400] : THEME.red[400] },
    { label: 'Net P&L', value: fmtSigned(net), sub: 'paper, all-time', color: net >= 0 ? THEME.primary[400] : THEME.red[400] },
  ];
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: '12px', marginBottom: '24px' }}>
      {cards.map((c, i) => (
        <Card key={i} style={{ padding: '18px 20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px' }}>
            <span style={{ fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.muted }}>{c.label}</span>
            {c.live && <span style={{ width: 6, height: 6, borderRadius: '50%', background: THEME.primary[400], animation: 'pulse 2s infinite' }}></span>}
          </div>
          <div style={{ fontFamily: THEME.font.heading, fontSize: '24px', fontWeight: 800, color: c.color, letterSpacing: 0 }}>{c.value}</div>
          <div style={{ fontFamily: THEME.font.mono, fontSize: '11px', color: THEME.text.muted, marginTop: '4px' }}>{c.sub}</div>
        </Card>
      ))}
    </div>
  );
};

const OpenPosition = ({ pos, onClose, closing }) => {
  const unreal = Number(pos.unrealizedPnlUsdc || 0);
  const up = unreal >= 0;
  return (
    <Card style={{ padding: '18px 20px' }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(220px, 1fr) auto', gap: '16px', alignItems: 'center' }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '9px', marginBottom: '5px', flexWrap: 'wrap' }}>
            <h4 style={{ fontFamily: THEME.font.heading, fontSize: '16px', fontWeight: 700, color: THEME.text.primary, margin: 0 }}>{pos.noteName}</h4>
            <SignalChip signal={pos.signal} style={{ fontSize: '10px', padding: '2px 8px' }} />
            <Badge color={pos.collateralStatus === 'asset_backed' ? 'primary' : 'amber'} style={{ fontSize: '10px' }}>{pos.collateralStatus || 'not asset backed'}</Badge>
          </div>
          <div style={{ fontFamily: THEME.font.mono, fontSize: '11px', color: THEME.text.muted, overflowWrap: 'anywhere' }}>
            {pos.positionId} · {formName(pos.form)} · opened {sinceLabel(pos.entryTs)}
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, auto)', gap: '22px', alignItems: 'center' }}>
          <div>
            <div style={{ fontFamily: THEME.font.body, fontSize: '10px', color: THEME.text.muted, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Size</div>
            <MonoText style={{ fontSize: '14px', color: THEME.text.primary }}>{fmtUsd(pos.notionalUsdc, 0)}</MonoText>
          </div>
          <div>
            <div style={{ fontFamily: THEME.font.body, fontSize: '10px', color: THEME.text.muted, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Entry / mark</div>
            <MonoText style={{ fontSize: '14px', color: THEME.text.secondary }}>{fmtNav(pos.entryMark)} / {fmtNav(pos.currentMark)}</MonoText>
          </div>
          <div style={{ textAlign: 'right', minWidth: '112px' }}>
            <div style={{ fontFamily: THEME.font.body, fontSize: '10px', color: THEME.text.muted, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Unrealized</div>
            <div style={{ fontFamily: THEME.font.mono, fontSize: '17px', fontWeight: 700, color: up ? THEME.primary[400] : THEME.red[400] }}>{fmtSigned(unreal)}</div>
            <div style={{ fontFamily: THEME.font.mono, fontSize: '11px', color: up ? THEME.primary[400] : THEME.red[400] }}>{fmtPct(pos.returnPct || 0)}</div>
          </div>
          <GlowButton size="sm" variant="secondary" onClick={() => onClose(pos.positionId)} disabled={closing === pos.positionId}>{closing === pos.positionId ? 'Closing...' : 'Close'}</GlowButton>
        </div>
      </div>
    </Card>
  );
};

const RealizedRow = ({ r }) => {
  const pnl = Number(r.pnlUsdc || 0);
  const up = pnl >= 0;
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr 0.8fr 0.8fr 0.9fr', gap: '12px', padding: '12px 14px', alignItems: 'center', borderTop: `1px solid ${THEME.border.subtle}`, fontFamily: THEME.font.mono, fontSize: '12px' }}>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.primary, fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.noteName}</div>
        <span style={{ fontSize: '10px', color: THEME.text.muted }}>{r.positionId}</span>
      </div>
      <span style={{ color: THEME.text.secondary }}>{fmtNav(r.entryMark)} / {fmtNav(r.exitMark)}</span>
      <span style={{ color: THEME.text.secondary }}>{fmtUsd(r.notionalUsdc, 0)}</span>
      <span style={{ color: up ? THEME.primary[400] : THEME.red[400] }}>{fmtPct(r.retPct || 0)}</span>
      <span style={{ textAlign: 'right', fontWeight: 700, color: up ? THEME.primary[400] : THEME.red[400] }}>{fmtSigned(pnl)}</span>
    </div>
  );
};

const EmptyState = ({ title, body, action }) => (
  <Card style={{ padding: '40px', textAlign: 'center', borderStyle: 'dashed', borderColor: THEME.border.default }}>
    <div style={{ width: 44, height: 44, margin: '0 auto 14px', borderRadius: '12px', background: THEME.bg.elevated, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none"><path d="M3 17l5-5 4 4 7-8" stroke={THEME.text.muted} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
    </div>
    <h4 style={{ fontFamily: THEME.font.heading, fontSize: '17px', fontWeight: 700, color: THEME.text.primary, margin: '0 0 6px' }}>{title}</h4>
    <p style={{ fontFamily: THEME.font.body, fontSize: '13.5px', color: THEME.text.muted, margin: '0 auto', maxWidth: '390px', lineHeight: 1.55 }}>{body}</p>
    {action}
  </Card>
);

const PortfolioView = ({ portfolio, account, goInvest, goAccount, onClosePosition }) => {
  const [closing, setClosing] = React.useState('');
  const positions = normalizeArray(portfolio?.positions);
  const realized = normalizeArray(portfolio?.realized);

  const close = async (positionId) => {
    setClosing(positionId);
    try {
      await onClosePosition(positionId);
    } finally {
      setClosing('');
    }
  };

  if (!account) {
    return (
      <div>
        <h2 style={{ fontFamily: THEME.font.heading, fontSize: '22px', fontWeight: 700, color: THEME.text.primary, margin: '0 0 6px', letterSpacing: 0 }}>My Portfolio</h2>
        <p style={{ fontFamily: THEME.font.body, fontSize: '13.5px', color: THEME.text.muted, margin: '0 0 22px' }}>
          Portfolio state is server-side. Create an Operator account so paper tickets, wallet, and PnL survive browser refreshes.
        </p>
        <EmptyState
          title="Account required"
          body="The old browser-only portfolio has been removed. A signed backend account is required to store positions and PnL."
          action={<div style={{ marginTop: '18px' }}><GlowButton size="md" onClick={goAccount}>Create account</GlowButton></div>}
        />
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '6px', flexWrap: 'wrap', gap: '8px' }}>
        <h2 style={{ fontFamily: THEME.font.heading, fontSize: '22px', fontWeight: 700, color: THEME.text.primary, margin: 0, letterSpacing: 0 }}>My Portfolio</h2>
        <MonoText style={{ fontSize: '11px', color: THEME.text.muted }}>{account.id}</MonoText>
      </div>
      <p style={{ fontFamily: THEME.font.body, fontSize: '13.5px', color: THEME.text.muted, margin: '0 0 22px', maxWidth: '760px', lineHeight: 1.55 }}>
        Open tickets are saved by the backend under your signed account and payer wallet. PnL is paper PnL: current note mark minus your entry mark, scaled by your test-USDC notional.
      </p>

      <PortfolioSummary summary={portfolio?.summary || {}} />

      <SectionLabel>Open positions</SectionLabel>
      <div style={{ marginTop: '12px', marginBottom: '28px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {positions.length === 0 ? (
          <EmptyState
            title="No open positions"
            body="Buy a backend-generated spread note to open an account-backed paper position."
            action={<div style={{ marginTop: '18px' }}><GlowButton size="md" onClick={goInvest}>Browse notes</GlowButton></div>}
          />
        ) : positions.map(p => (
          <OpenPosition key={p.positionId} pos={p} onClose={close} closing={closing} />
        ))}
      </div>

      <SectionLabel>Realized ledger</SectionLabel>
      <Card style={{ padding: '8px 6px', marginTop: '12px' }}>
        {realized.length === 0 ? (
          <div style={{ padding: '24px', textAlign: 'center', fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.muted }}>
            No closed positions yet.
          </div>
        ) : (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr 0.8fr 0.8fr 0.9fr', gap: '12px', padding: '8px 14px', fontFamily: THEME.font.mono, fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.08em', color: THEME.text.muted }}>
              <span>Note</span><span>Entry / Exit</span><span>Size</span><span>Return</span><span style={{ textAlign: 'right' }}>Realized</span>
            </div>
            {realized.map((r, i) => <RealizedRow key={`${r.positionId}-${i}`} r={r} />)}
          </>
        )}
      </Card>
    </div>
  );
};

Object.assign(window, { PortfolioView });
