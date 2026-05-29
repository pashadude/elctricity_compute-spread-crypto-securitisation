/* Power by Botozen - Dashboard shell: Invest, Portfolio, Signal, Methodology */

const SubTabs = ({ tab, setTab, tabs, portfolioCount }) => (
  <div style={{ display: 'flex', gap: '2px', background: THEME.bg.surface, border: `1px solid ${THEME.border.subtle}`, borderRadius: '12px', padding: '4px', flexWrap: 'wrap' }}>
    {tabs.map(t => {
      const active = tab === t.id;
      return (
        <button key={t.id} onClick={() => setTab(t.id)} style={{
          display: 'inline-flex', alignItems: 'center', gap: '7px',
          padding: '9px 16px', borderRadius: '8px', border: 'none', cursor: 'pointer',
          fontFamily: THEME.font.body, fontSize: '13.5px', fontWeight: 600, letterSpacing: 0, whiteSpace: 'nowrap',
          background: active ? THEME.primary[400] + '16' : 'transparent',
          color: active ? THEME.primary[400] : THEME.text.secondary,
          transition: 'all 0.18s',
        }}>
          {t.label}
          {t.id === 'portfolio' && portfolioCount > 0 && (
            <span style={{ fontFamily: THEME.font.mono, fontSize: '10px', fontWeight: 700, padding: '1px 6px', borderRadius: '100px', background: active ? THEME.primary[400] + '25' : THEME.bg.hover, color: active ? THEME.primary[400] : THEME.text.muted }}>{portfolioCount}</span>
          )}
          {t.admin && <span style={{ fontFamily: THEME.font.mono, fontSize: '8.5px', fontWeight: 700, padding: '1px 5px', borderRadius: '4px', background: THEME.purple[400] + '20', color: THEME.purple[400], letterSpacing: '0.04em' }}>ADMIN</span>}
        </button>
      );
    })}
  </div>
);

const AccountStrip = ({ account, mode, setPage }) => (
  <Card style={{ padding: '12px 14px', background: account ? THEME.primary[400] + '0c' : THEME.amber[400] + '0c', borderColor: account ? THEME.primary[400] + '25' : THEME.amber[400] + '25' }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.primary, fontWeight: 700 }}>
          {account ? 'Account-backed paper trading is active' : 'Create an Operator account to save positions and PnL'}
        </div>
        <div style={{ fontFamily: THEME.font.mono, fontSize: '11px', color: THEME.text.muted, marginTop: '2px', overflowWrap: 'anywhere' }}>
          {account ? `${account.id} · ${account.walletAddress}` : `session cookie: ${mode?.session_secret_configured ? 'configured' : 'dev fallback'} · Circle/demo payment required`}
        </div>
      </div>
      <GlowButton size="sm" variant={account ? 'secondary' : 'primary'} onClick={() => setPage?.('account')}>
        {account ? 'Account' : 'Create account'}
      </GlowButton>
    </div>
  </Card>
);

const DashboardPage = ({ refreshRate, adminMode, setPage }) => {
  const [tab, setTab] = React.useState('invest');
  const [ticket, setTicket] = React.useState(null);
  const data = usePowerDeskData(refreshRate);
  const [actionError, setActionError] = React.useState('');

  React.useEffect(() => { if (!adminMode && tab === 'operator') setTab('invest'); }, [adminMode, tab]);

  const tabs = [
    { id: 'invest', label: 'Invest' },
    { id: 'portfolio', label: 'Portfolio' },
    { id: 'signal', label: 'Market Signal' },
    { id: 'methodology', label: 'Methodology' },
    ...(adminMode ? [{ id: 'operator', label: 'Operator', admin: true }] : []),
  ];

  const openBuy = (note, mark) => setTicket({ note, mark });
  const confirmBuy = async (note, size) => {
    const portfolio = await openPaperPosition({ instrumentId: note.id, notionalUsdc: size });
    data.refresh();
    setActionError('');
    setTab('portfolio');
    return portfolio;
  };
  const closePosition = async (positionId) => {
    try {
      await closePaperPosition({ positionId });
      await data.refresh();
      setActionError('');
    } catch (err) {
      setActionError(String(err.message || err));
      throw err;
    }
  };

  const portfolioCount = normalizeArray(data.portfolio?.positions).length;

  return (
    <div style={{ padding: '24px 32px 80px', maxWidth: '1120px', margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h1 style={{ fontFamily: THEME.font.heading, fontSize: '26px', fontWeight: 800, color: THEME.text.primary, margin: 0, letterSpacing: 0 }}>
            Power Desk
          </h1>
          <p style={{ fontFamily: THEME.font.body, fontSize: '13.5px', color: THEME.text.muted, margin: '3px 0 0' }}>
            Compute/energy spread notes, account-backed paper tickets, Arc-gated settlement.
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          <Badge color="muted" style={{ fontSize: '10.5px' }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: THEME.amber[400], display: 'inline-block' }}></span>
            Paper marks
          </Badge>
          <div style={{ display: 'flex', alignItems: 'center', gap: '7px', padding: '5px 12px', borderRadius: '100px', background: THEME.bg.surface, border: `1px solid ${THEME.border.subtle}` }}>
            <span style={{ width: 7, height: 7, borderRadius: '50%', background: data.error ? THEME.red[400] : THEME.primary[400], animation: data.error ? 'none' : 'pulse 2s infinite' }}></span>
            <MonoText style={{ fontSize: '11px', color: THEME.text.muted }}>{data.error ? 'API error' : `Backend · ${(refreshRate / 1000).toFixed(1)}s`}</MonoText>
          </div>
        </div>
      </div>

      <div style={{ marginBottom: '16px' }}>
        <AccountStrip account={data.account} mode={data.accountMode} setPage={setPage} />
      </div>

      {data.error && (
        <Card style={{ padding: '12px 14px', marginBottom: '16px', background: THEME.red[400] + '10', borderColor: THEME.red[400] + '30' }}>
          <div style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.red[400] }}>{data.error}</div>
        </Card>
      )}
      {actionError && (
        <Card style={{ padding: '12px 14px', marginBottom: '16px', background: THEME.red[400] + '10', borderColor: THEME.red[400] + '30' }}>
          <div style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.red[400] }}>{actionError}</div>
        </Card>
      )}

      <div style={{ marginBottom: '26px' }}>
        <SubTabs tab={tab} setTab={setTab} tabs={tabs} portfolioCount={portfolioCount} />
      </div>

      {data.loading ? (
        <Card style={{ padding: '36px', textAlign: 'center' }}>
          <SectionLabel>Loading backend state</SectionLabel>
          <p style={{ fontFamily: THEME.font.body, color: THEME.text.muted, margin: 0 }}>Reading `/api/snapshot`, `/api/account`, and `/api/account/portfolio`.</p>
        </Card>
      ) : (
        <div key={tab} style={{ animation: 'fadeIn 0.3s ease' }}>
          {tab === 'invest' && <InvestView notes={data.notes} marks={data.marks} account={data.account} onBuy={openBuy} setPage={setPage} />}
          {tab === 'portfolio' && <PortfolioView portfolio={data.portfolio} account={data.account} goInvest={() => setTab('invest')} goAccount={() => setPage?.('account')} onClosePosition={closePosition} />}
          {tab === 'signal' && <SignalView spread={data.spread} stats={data.stats} indexCatalog={data.indexCatalog} goalCoverage={data.goalCoverage} />}
          {tab === 'methodology' && <MethodologyView />}
          {tab === 'operator' && adminMode && <OperatorView snapshot={data.snapshot} />}
        </div>
      )}

      {ticket && (
        <BuyTicket note={ticket.note} mark={ticket.mark} account={data.account} onConfirm={confirmBuy} onClose={() => setTicket(null)} setPage={setPage} />
      )}
    </div>
  );
};

Object.assign(window, { DashboardPage });
