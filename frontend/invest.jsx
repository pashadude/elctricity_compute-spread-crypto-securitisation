/* Power by Botozen - Invest: backend syndicated instruments */

const SignalChip = ({ signal, style }) => {
  const m = SIGNAL_META[signal] || SIGNAL_META.HOLD;
  return <Badge color={m.color} style={style}>{m.label}</Badge>;
};

const sideColor = (side) => {
  const low = String(side || '').toLowerCase();
  if (low === 'long') return THEME.primary[400];
  if (low === 'short') return THEME.red[400];
  return THEME.text.secondary;
};

const LegsTable = ({ legs, directLegs, size }) => {
  const rows = [
    ...normalizeArray(legs).map(leg => ({ type: 'priced', ...leg })),
    ...normalizeArray(directLegs).slice(0, 3).map(leg => ({
      type: 'direct',
      side: leg.direction || 'watch',
      sym: leg.slug,
      name: leg.title,
      role: leg.role || leg.surface,
      source: leg.surface,
    })),
  ];
  if (!rows.length) {
    return (
      <div style={{ padding: '12px', borderRadius: '8px', background: THEME.bg.elevated, fontFamily: THEME.font.body, color: THEME.text.muted, fontSize: '12.5px' }}>
        No priced venue legs are currently attached. The note remains a research candidate until discovery fills this gap.
      </div>
    );
  }
  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: '76px 1fr 110px 84px', gap: '12px', padding: '0 0 8px', fontFamily: THEME.font.mono, fontSize: '10px', letterSpacing: '0.08em', textTransform: 'uppercase', color: THEME.text.muted }}>
        <span>Role</span><span>Leg</span><span>Source</span><span style={{ textAlign: 'right' }}>{size ? 'Notional' : 'Mark'}</span>
      </div>
      {rows.map((l, i) => (
        <div key={`${l.type}-${l.sym}-${i}`} style={{ display: 'grid', gridTemplateColumns: '76px 1fr 110px 84px', gap: '12px', padding: '9px 0', alignItems: 'center', borderTop: `1px solid ${THEME.border.subtle}` }}>
          <span style={{ fontFamily: THEME.font.mono, fontSize: '10.5px', fontWeight: 700, textTransform: 'uppercase', color: sideColor(l.side) }}>{l.type}</span>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.primary, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{l.name || l.sym}</div>
            <div style={{ fontFamily: THEME.font.mono, fontSize: '10px', color: THEME.text.muted, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{l.sym || l.role || '-'}</div>
          </div>
          <MonoText style={{ fontSize: '11px', color: THEME.text.secondary, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{l.source || l.role || '-'}</MonoText>
          <MonoText style={{ fontSize: '12px', textAlign: 'right', color: THEME.text.primary }}>
            {size ? fmtUsd(size / Math.max(rows.length, 1), 0) : (l.last_price ? fmtUsd(l.last_price, 2) : '-')}
          </MonoText>
        </div>
      ))}
    </div>
  );
};

const ReplayRecord = ({ note }) => {
  const replay = note.replay || {};
  const stats = [
    { k: 'Total return', v: fmtPct(note.totalReturnPct || replay.yield || 0), c: Number(note.totalReturnPct || 0) >= 0 ? THEME.primary[400] : THEME.red[400] },
    { k: '5d return', v: fmtPct(note.return5dPct || 0), c: Number(note.return5dPct || 0) >= 0 ? THEME.primary[400] : THEME.red[400] },
    { k: '1m return', v: fmtPct(note.return1mPct || 0), c: Number(note.return1mPct || 0) >= 0 ? THEME.primary[400] : THEME.red[400] },
    { k: 'Win rate', v: `${Number(note.winRate || 0).toFixed(1)}%`, c: THEME.text.primary },
    { k: 'Max drawdown', v: fmtPct(note.maxDrawdownPct || 0), c: THEME.red[400] },
    { k: 'Replay status', v: replay.status || note.replayStatus || 'backend', c: THEME.text.secondary },
  ];
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px', flexWrap: 'wrap' }}>
        <SectionLabel style={{ margin: 0 }}>Backtest and paper replay</SectionLabel>
        <Badge color="muted" style={{ fontSize: '10px' }}>{note.profitabilityStatus || note.status || 'MONITOR'}</Badge>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: '10px' }}>
        {stats.map((s, i) => (
          <div key={i} style={{ padding: '10px 12px', borderRadius: '8px', background: THEME.bg.elevated }}>
            <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.muted, marginBottom: '4px' }}>{s.k}</div>
            <MonoText style={{ fontSize: '14px', fontWeight: 700, color: s.c, overflowWrap: 'anywhere' }}>{s.v}</MonoText>
          </div>
        ))}
      </div>
    </div>
  );
};

const CollateralChecklist = ({ note }) => {
  const missing = normalizeArray(note.collateralNeeded);
  return (
    <div style={{ display: 'grid', gap: '8px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '10px', alignItems: 'center' }}>
        <span style={{ fontFamily: THEME.font.body, fontSize: '12.5px', color: THEME.text.secondary }}>Asset-backed status</span>
        <Badge color={note.assetBacked ? 'primary' : 'amber'}>{note.assetBacked ? 'asset backed' : 'needs collateral'}</Badge>
      </div>
      {missing.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
          {missing.map(item => <Badge key={item} color="muted" style={{ borderRadius: '6px' }}>{item}</Badge>)}
        </div>
      )}
    </div>
  );
};

const NoteCard = ({ note, mark, account, onBuy, setPage }) => {
  const [open, setOpen] = React.useState(false);
  const nav = mark ? mark.nav : Number(note.markNav || 1);
  const hist = mark?.hist || note.hist || [1, nav];
  const navDelta = hist.length > 1 ? hist[hist.length - 1] - hist[0] : 0;
  const m = SIGNAL_META[note.signal] || SIGNAL_META.HOLD;
  const accent = THEME[m.color === 'primary' ? 'primary' : m.color === 'amber' ? 'amber' : 'red'][400];
  const buyDisabled = !account;

  return (
    <Card hoverable style={{ padding: 0, overflow: 'hidden' }}>
      <div style={{ display: 'flex' }}>
        <div style={{ width: '3px', background: accent, flexShrink: 0 }}></div>
        <div style={{ flex: 1, padding: '20px 22px', minWidth: 0 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '16px', flexWrap: 'wrap' }}>
            <div style={{ minWidth: 0, flex: '1 1 260px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '7px', flexWrap: 'wrap' }}>
                <SignalChip signal={note.signal} />
                <Badge color={note.assetBacked ? 'primary' : 'amber'}>{note.assetBacked ? 'asset backed' : 'not asset backed'}</Badge>
                <span style={{ fontFamily: THEME.font.mono, fontSize: '11px', color: THEME.text.muted }}>{formName(note.form)}</span>
              </div>
              <h3 style={{ fontFamily: THEME.font.heading, fontSize: '19px', fontWeight: 700, color: THEME.text.primary, margin: 0, letterSpacing: 0 }}>{note.name}</h3>
            </div>
            <div style={{ textAlign: 'right', flexShrink: 0 }}>
              <div style={{ fontFamily: THEME.font.body, fontSize: '10px', color: THEME.text.muted, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Paper NAV</div>
              <MonoText style={{ fontSize: '20px', fontWeight: 700, color: THEME.text.primary }}>{fmtNav(nav)}</MonoText>
              <div style={{ fontFamily: THEME.font.mono, fontSize: '11px', color: navDelta >= 0 ? THEME.primary[400] : THEME.red[400] }}>
                {fmtPct(navDelta * 100)}
              </div>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 150px', gap: '18px', alignItems: 'end', marginTop: '14px' }}>
            <p style={{ fontFamily: THEME.font.body, fontSize: '13.5px', lineHeight: 1.55, color: THEME.text.secondary, margin: 0 }}>
              {note.thesis}
            </p>
            <Sparkline data={hist} width={150} height={42} color={accent} style={{ width: '100%', height: '42px' }} />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: '12px', marginTop: '16px' }}>
            {[
              ['Circle ask', note.circleAskUsdc ? `${note.circleAskUsdc.toLocaleString()} USDC` : 'not sized', THEME.amber[400]],
              ['5d replay', fmtPct(note.return5dPct || 0), Number(note.return5dPct || 0) >= 0 ? THEME.primary[400] : THEME.red[400]],
              ['1m replay', fmtPct(note.return1mPct || 0), Number(note.return1mPct || 0) >= 0 ? THEME.primary[400] : THEME.red[400]],
              ['Arc gate', 'judge first', THEME.text.secondary],
            ].map(([k, v, c]) => (
              <div key={k}>
                <div style={{ fontFamily: THEME.font.body, fontSize: '10px', color: THEME.text.muted, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{k}</div>
                <MonoText style={{ fontSize: '13px', fontWeight: 700, color: c }}>{v}</MonoText>
              </div>
            ))}
          </div>

          {open && (
            <div style={{ marginTop: '20px', paddingTop: '20px', borderTop: `1px solid ${THEME.border.subtle}`, animation: 'fadeIn 0.3s ease' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr', gap: '18px', alignItems: 'start' }}>
                <div>
                  <SectionLabel>How the legs connect</SectionLabel>
                  <p style={{ fontFamily: THEME.font.body, fontSize: '12.8px', color: THEME.text.muted, lineHeight: 1.55, margin: '0 0 12px' }}>
                    {note.copyingSpread || 'The package maps a compute/energy spread into priced public legs plus direct event or forecast references.'}
                  </p>
                  <LegsTable legs={note.legs} directLegs={note.directLegs} />
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  <Card style={{ padding: '14px', background: THEME.bg.elevated }}>
                    <SectionLabel style={{ marginBottom: '8px' }}>Collateral</SectionLabel>
                    <CollateralChecklist note={note} />
                  </Card>
                  <ReplayRecord note={note} />
                </div>
              </div>
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '18px', gap: '12px', flexWrap: 'wrap' }}>
            <button onClick={() => setOpen(o => !o)} style={{
              background: 'none', border: 'none', cursor: 'pointer', padding: 0,
              fontFamily: THEME.font.body, fontSize: '13px', fontWeight: 600, color: THEME.text.secondary,
              display: 'flex', alignItems: 'center', gap: '6px',
            }}>
              {open ? 'Hide legs and replay' : 'View legs and replay'}
              <span style={{ display: 'inline-block', transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s', fontSize: '10px' }}>v</span>
            </button>
            <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
              {!account && <GlowButton size="sm" variant="secondary" onClick={() => setPage?.('account')}>Create account</GlowButton>}
              <GlowButton size="sm" variant={note.signal === 'CLOSE_OR_AVOID' ? 'secondary' : 'primary'} onClick={() => onBuy(note, nav)} disabled={buyDisabled}>
                {note.signal === 'CLOSE_OR_AVOID' ? 'Paper buy anyway' : 'Buy paper note'}
              </GlowButton>
            </div>
          </div>
        </div>
      </div>
    </Card>
  );
};

const BuyTicket = ({ note, mark, account, onConfirm, onClose, setPage }) => {
  const [size, setSize] = React.useState(Math.max(50, Math.min(2500, Number(note.circleAskUsdc || 500))));
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState('');
  const [done, setDone] = React.useState(false);
  const entry = Number(mark || note.markNav || 1);

  const confirm = async () => {
    setBusy(true);
    setError('');
    try {
      await onConfirm(note, size);
      setDone(true);
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 200, background: '#000000cc', backdropFilter: 'blur(8px)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '20px' }} onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{ background: THEME.bg.surface, border: `1px solid ${THEME.border.default}`, borderRadius: THEME.radius.lg, padding: '28px', width: '480px', maxWidth: '100%', boxShadow: '0 32px 64px #00000070' }}>
        {!done ? (
          <>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '18px', gap: '12px' }}>
              <div>
                <div style={{ fontFamily: THEME.font.mono, fontSize: '11px', color: THEME.text.muted, marginBottom: '4px' }}>BUY PAPER SPREAD NOTE</div>
                <h3 style={{ fontFamily: THEME.font.heading, fontSize: '20px', fontWeight: 700, color: THEME.text.primary, margin: 0 }}>{note.name}</h3>
              </div>
              <button onClick={onClose} style={{ background: 'none', border: 'none', color: THEME.text.muted, cursor: 'pointer', fontSize: '18px' }}>x</button>
            </div>

            {!account && (
              <Card style={{ padding: '14px', marginBottom: '16px', background: THEME.amber[400] + '10', borderColor: THEME.amber[400] + '30' }}>
                <div style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.secondary, lineHeight: 1.5, marginBottom: '12px' }}>
                  A signed Operator account is required before the backend can store your paper positions and PnL.
                </div>
                <GlowButton size="sm" onClick={() => { onClose(); setPage?.('account'); }}>Open account page</GlowButton>
              </Card>
            )}

            {note.signal === 'CLOSE_OR_AVOID' && (
              <div style={{ padding: '10px 12px', borderRadius: '8px', background: THEME.red[400] + '12', border: `1px solid ${THEME.red[400]}25`, marginBottom: '16px' }}>
                <span style={{ fontFamily: THEME.font.mono, fontSize: '11.5px', color: THEME.red[400] }}>Desk signal is CLOSE / AVOID. This opens a tracked paper ticket, not a recommendation.</span>
              </div>
            )}

            <label style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.secondary, display: 'block', marginBottom: '8px' }}>Paper size - test USDC</label>
            <input type="number" value={size} min={50} step={50} onChange={e => setSize(Math.max(0, Number(e.target.value)))} style={{
              width: '100%', boxSizing: 'border-box', padding: '12px 16px',
              background: THEME.bg.elevated, border: `1px solid ${THEME.border.default}`, borderRadius: THEME.radius.md,
              color: THEME.text.primary, fontFamily: THEME.font.mono, fontSize: '16px', fontWeight: 700, outline: 'none', marginBottom: '12px',
            }} />
            <div style={{ display: 'flex', gap: '8px', marginBottom: '18px', flexWrap: 'wrap' }}>
              {[250, 500, 1000, 2500].map(v => (
                <button key={v} onClick={() => setSize(v)} style={{
                  flex: '1 1 70px', padding: '8px', borderRadius: '8px', cursor: 'pointer',
                  background: size === v ? THEME.primary[400] + '18' : THEME.bg.elevated,
                  border: `1px solid ${size === v ? THEME.primary[400] + '50' : THEME.border.subtle}`,
                  color: size === v ? THEME.primary[400] : THEME.text.secondary,
                  fontFamily: THEME.font.mono, fontSize: '12px', fontWeight: 600,
                }}>{v}</button>
              ))}
            </div>

            <Card style={{ padding: '14px 16px', marginBottom: '18px', background: THEME.bg.elevated }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '10px', gap: '12px' }}>
                <span style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.secondary }}>Entry NAV</span>
                <MonoText style={{ fontWeight: 700 }}>{fmtNav(entry)}</MonoText>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '10px', gap: '12px' }}>
                <span style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.secondary }}>Account wallet</span>
                <MonoText style={{ fontSize: '11px', overflowWrap: 'anywhere' }}>{account?.walletAddress || 'required'}</MonoText>
              </div>
              <Divider style={{ margin: '10px 0' }} />
              <LegsTable legs={note.legs} directLegs={note.directLegs} size={size} />
            </Card>

            {error && <div style={{ fontFamily: THEME.font.body, fontSize: '12.5px', color: THEME.red[400], marginBottom: '12px' }}>{error}</div>}

            <GlowButton size="md" variant={note.signal === 'CLOSE_OR_AVOID' ? 'secondary' : 'primary'} style={{ width: '100%', justifyContent: 'center' }} onClick={confirm} disabled={!account || !size || busy}>
              {busy ? 'Opening...' : `Open paper ticket - ${fmtUsd(size, 0)} test USDC`}
            </GlowButton>
            <div style={{ textAlign: 'center', marginTop: '10px', fontFamily: THEME.font.mono, fontSize: '10.5px', color: THEME.text.faint }}>
              Stored server-side under your account. Arc remains locked unless judge.classify() returns EXECUTE.
            </div>
          </>
        ) : (
          <div style={{ textAlign: 'center', padding: '12px 0' }}>
            <div style={{ width: '60px', height: '60px', borderRadius: '50%', background: THEME.primary[400] + '18', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px' }}>
              <svg width="30" height="30" viewBox="0 0 32 32" fill="none"><path d="M8 16l6 6 10-12" stroke={THEME.primary[400]} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" /></svg>
            </div>
            <h3 style={{ fontFamily: THEME.font.heading, fontSize: '20px', fontWeight: 700, color: THEME.text.primary, margin: '0 0 6px' }}>Paper position opened</h3>
            <p style={{ fontFamily: THEME.font.body, fontSize: '13.5px', color: THEME.text.secondary, margin: '0 0 20px' }}>
              {fmtUsd(size, 0)} test USDC into <strong style={{ color: THEME.text.primary }}>{note.name}</strong> at NAV {fmtNav(entry)}.
            </p>
            <GlowButton size="md" style={{ width: '100%', justifyContent: 'center' }} onClick={onClose}>Done</GlowButton>
          </div>
        )}
      </div>
    </div>
  );
};

const InvestView = ({ notes, marks, account, onBuy, setPage }) => {
  const enterable = normalizeArray(notes).filter(n => n.signal === 'ENTER');
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '6px', flexWrap: 'wrap', gap: '8px' }}>
        <h2 style={{ fontFamily: THEME.font.heading, fontSize: '22px', fontWeight: 700, color: THEME.text.primary, margin: 0, letterSpacing: 0 }}>Syndicated Spread Notes</h2>
        <span style={{ fontFamily: THEME.font.mono, fontSize: '12px', color: THEME.text.muted }}>
          {normalizeArray(notes).length} backend notes · <span style={{ color: THEME.primary[400] }}>{enterable.length} buyable paper entries</span>
        </span>
      </div>
      <p style={{ fontFamily: THEME.font.body, fontSize: '13.5px', color: THEME.text.muted, margin: '0 0 22px', maxWidth: '760px', lineHeight: 1.55 }}>
        These are backend-built compute/energy spread instruments. A user buys a paper note, the account stores the ticket server-side, and PnL marks against the same backend replay and public-leg marks. Missing collateral is shown explicitly.
      </p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
        {normalizeArray(notes).length === 0 ? (
          <Card style={{ padding: '34px', textAlign: 'center', borderStyle: 'dashed' }}>
            <h4 style={{ fontFamily: THEME.font.heading, color: THEME.text.primary, margin: '0 0 8px' }}>No backend instruments yet</h4>
            <p style={{ fontFamily: THEME.font.body, color: THEME.text.muted, margin: 0 }}>Run the backend scanner so `/api/snapshot` can publish syndicated instrument candidates.</p>
          </Card>
        ) : notes.map(n => (
          <NoteCard key={n.id} note={n} mark={marks[n.id]} account={account} onBuy={onBuy} setPage={setPage} />
        ))}
      </div>
    </div>
  );
};

Object.assign(window, { InvestView, BuyTicket, NoteCard, SignalChip, LegsTable, ReplayRecord, formName });
