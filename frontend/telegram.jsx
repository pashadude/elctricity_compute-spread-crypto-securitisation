/* Arc Compute Sec — Telegram Mini App */

const TG_THEME = {
  bg: '#0B0F0E', surface: '#111916', elevated: '#172119',
  separator: '#1E2D25', blue: '#60A5FA', green: '#00DC82',
  red: '#EF4444', orange: '#F59E0B', text: '#FFFFFF',
  secondary: '#A1B5AB', tertiary: '#6B8578',
  accent: '#00DC82', accentBg: '#00DC8215',
};

const TG_BOT_URL = 'https://t.me/BotozenPowerBot';
const TG_CHANNEL_URL = 'https://t.me/botozen_power';
const TG_MINI_APP_PATH = '/tg';

const tgHasProxyPrice = (leg = {}) => (
  leg.externalProxyLastPrice !== null
  && leg.externalProxyLastPrice !== undefined
  && Number.isFinite(Number(leg.externalProxyLastPrice))
);

const tgProxySourceLabel = (leg = {}) => {
  const low = String(leg.externalProxySource || '').toLowerCase();
  if (low === 'ibkr_energy_history_csv') return `IBKR paper CSV${leg.externalProxyStale ? ' · stale' : ''}`;
  if (low === 'ibkr_tws_front_future') return 'IBKR paper TWS';
  if (low === 'ibkr_tws_stock') return 'IBKR paper TWS';
  if (low === 'yahoo_finance_chart') return 'Yahoo fallback';
  if (low === 'alpaca_market_data') return 'Alpaca fallback';
  return leg.externalProxySource || '';
};

const tgInventorySubtitle = (leg = {}) => {
  const parts = [
    leg.surface || 'surface',
    leg.directPairRole || leg.role || 'research only',
  ];
  if (leg.externalProxySymbol) parts.push(`proxy ${leg.externalProxySymbol}`);
  const source = tgProxySourceLabel(leg);
  if (source) parts.push(source);
  if (leg.externalProxyRegularMarketTime) parts.push(`as of ${leg.externalProxyRegularMarketTime}`);
  if (leg.endDate) parts.push(`resolves ${formatEventDate(leg.endDate)}`);
  return parts.filter(Boolean).join(' · ');
};

const tgInventoryTrailing = (leg = {}) => (
  tgHasProxyPrice(leg)
    ? `$${Number(leg.externalProxyLastPrice).toFixed(2)}`
    : (leg.pricingStatusLabel || 'watchlist')
);

const TgScreen = ({ children, title, subtitle, onBack, style }) => (
  <div style={{
    background: TG_THEME.bg, height: '100%', minHeight: '100%', display: 'flex', flexDirection: 'column',
    fontFamily: '-apple-system, "SF Pro Text", sans-serif', ...style,
  }}>
    {/* TG header */}
    <div style={{
      padding: '12px 16px', display: 'flex', alignItems: 'center', gap: '12px',
      borderBottom: `0.5px solid ${TG_THEME.separator}`,
      background: TG_THEME.bg,
    }}>
      {onBack && (
        <button type="button" onClick={onBack} style={{
          background: 'none', border: 'none', color: TG_THEME.green,
          fontSize: '16px', cursor: 'pointer', padding: '8px 6px',
          position: 'relative', zIndex: 5,
        }}>← Back</button>
      )}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: '17px', fontWeight: 600, color: TG_THEME.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{title}</div>
        {subtitle && <div style={{ fontSize: '12px', color: TG_THEME.secondary }}>{subtitle}</div>}
      </div>
    </div>
    <div style={{ flex: 1, overflow: 'auto' }}>{children}</div>
  </div>
);

const TgListItem = ({ icon, title, subtitle, trailing, onClick, accent }) => (
  <button onClick={onClick} style={{
    display: 'flex', alignItems: 'center', gap: '12px', width: '100%',
    padding: '12px 16px', background: 'none', border: 'none', cursor: onClick ? 'pointer' : 'default',
    textAlign: 'left', borderBottom: `0.5px solid ${TG_THEME.separator}`,
  }}>
    {icon && (
      <div style={{
        width: 36, height: 36, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: (accent || TG_THEME.blue) + '20', fontSize: '18px', flexShrink: 0,
      }}>{icon}</div>
    )}
      <div style={{ flex: 1, minWidth: 0 }}>
      <div style={{ fontSize: '15px', color: TG_THEME.text, fontWeight: 500, lineHeight: 1.25, overflowWrap: 'anywhere' }}>{title}</div>
      {subtitle && <div style={{ fontSize: '13px', color: TG_THEME.secondary, marginTop: '2px', lineHeight: 1.3, overflowWrap: 'anywhere' }}>{subtitle}</div>}
    </div>
    {trailing && <div style={{ flexShrink: 0 }}>{trailing}</div>}
  </button>
);

const TgBadge = ({ children, color }) => (
  <span style={{
    display: 'inline-flex', padding: '3px 8px', borderRadius: '6px',
    fontSize: '12px', fontWeight: 600, fontFamily: 'SF Mono, monospace',
    background: (color || TG_THEME.blue) + '20', color: color || TG_THEME.blue,
  }}>{children}</span>
);

const TgWebLinks = () => {
  const isMobile = useIsMobile(560);
  return (
  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', margin: '0 0 28px' }}>
    {[
      { label: 'Open Mini App', href: TG_MINI_APP_PATH, external: false, primary: true },
      { label: 'Open Bot', href: TG_BOT_URL, external: true },
      { label: 'Join Channel', href: TG_CHANNEL_URL, external: true },
    ].map(link => (
      <a
        key={link.label}
        href={link.href}
        target={link.external ? '_blank' : undefined}
        rel={link.external ? 'noreferrer' : undefined}
        style={{
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          minHeight: '38px', padding: '0 14px', borderRadius: '8px',
          border: `1px solid ${link.primary ? TG_THEME.green + '55' : TG_THEME.separator}`,
          background: link.primary ? TG_THEME.green : TG_THEME.surface,
          color: link.primary ? '#000' : TG_THEME.text,
          fontFamily: THEME.font.body, fontSize: '13px', fontWeight: 700,
          textDecoration: 'none',
          flex: isMobile ? '1 1 100%' : '0 0 auto',
        }}
      >
        {link.label}
      </a>
    ))}
  </div>
  );
};

const useTgScreenRouter = () => {
  const [history, setHistory] = React.useState(['home']);
  const screen = history[history.length - 1] || 'home';
  const setScreen = React.useCallback((next) => {
    setHistory(prev => {
      if (next === 'home') return ['home'];
      if (prev[prev.length - 1] === next) return prev;
      return [...prev, next];
    });
  }, []);
  const goBack = React.useCallback(() => {
    setHistory(prev => (prev.length > 1 ? prev.slice(0, -1) : ['home']));
  }, []);
  return { screen, setScreen, goBack };
};

const useTelegramBackendData = () => {
  const [data, setData] = React.useState(() => window.emptyDashboardData ? window.emptyDashboardData() : { pnl: {}, spread: {}, verdicts: [], positions: [], candidates: [], connection: { status: 'loading' } });
  React.useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const resp = await fetch('/api/snapshot', { cache: 'no-store' });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const snapshot = await resp.json();
        if (!cancelled) {
          setData(window.mapSnapshotToDashboardData ? window.mapSnapshotToDashboardData(snapshot) : data);
        }
      } catch (err) {
        if (!cancelled) setData(prev => ({ ...prev, connection: { status: 'offline', error: String(err.message || err) } }));
      }
    };
    load();
    const t = setInterval(load, 3000);
    return () => { cancelled = true; clearInterval(t); };
  }, []);
  return data;
};

const requestBackendScan = async () => {
  const resp = await fetch('/api/scans', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ max_positions: 1, multi_surface: true }),
  });
  const body = await resp.json();
  if (!resp.ok) throw new Error(body.error || `HTTP ${resp.status}`);
  return body.request;
};

const tgMockConstruction = (data) => data.syntheticInstrument?.outputs?.mock_hedge_construction || {};
const tgSearchPlan = (data) => data.syntheticInstrument?.outputs?.agent_search_plan || [];
const tgWeightedLegs = (data) => tgMockConstruction(data).weighted_legs || [];
const tgUsdc = (value, fallback = 'Pending') => {
  const n = Number(value || 0);
  return n > 0 ? n.toLocaleString(undefined, { maximumFractionDigits: 0 }) : fallback;
};
const tgRecommendation = (construction) => construction.recommended_action === 'BUY_CONTRACT' ? 'Buy' : 'Monitor';
const tgWeightLabel = (leg) => `${leg.side || 'hold'} ${leg.slug || leg.symbol || 'leg'} ${Number(leg.weight || 0).toLocaleString(undefined, { style: 'percent', maximumFractionDigits: 0 })}`;

/* ── Mini App Screens ── */

const TgHome = ({ setScreen, data, requestScan }) => {
  const construction = tgMockConstruction(data);
  const searchCount = tgSearchPlan(data).length + (data.directInventory?.length || 0);
  const recommendation = tgRecommendation(construction);
  return (
  <TgScreen title="Botozen Power" subtitle="Compute/Energy Spread Desk">
    <div style={{ padding: '16px' }}>
      {/* Fink quote banner */}
      <div style={{
        background: `linear-gradient(135deg, ${TG_THEME.orange}12, ${TG_THEME.green}08)`,
        borderRadius: '12px', padding: '14px 16px', marginBottom: '12px',
        border: `1px solid ${TG_THEME.orange}20`,
      }}>
        <div style={{ fontSize: '14px', fontStyle: 'italic', color: TG_THEME.text, fontWeight: 600, lineHeight: 1.4, marginBottom: '6px' }}>
          "A new asset class will be buying futures of compute"
        </div>
        <div style={{ fontSize: '11px', color: TG_THEME.secondary }}>
          Larry Fink, CEO BlackRock
        </div>
      </div>

    {/* Status card */}
      <div style={{
        background: TG_THEME.surface, borderRadius: '12px', padding: '16px',
        marginBottom: '16px',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
          <span style={{ fontSize: '13px', color: TG_THEME.secondary }}>System Status</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <div style={{ width: 8, height: 8, borderRadius: '50%', background: data.connection.status === 'live' ? TG_THEME.green : TG_THEME.orange }}></div>
            <span style={{ fontSize: '13px', color: data.connection.status === 'live' ? TG_THEME.green : TG_THEME.orange, fontWeight: 600 }}>{data.connection.status === 'live' ? 'Live' : 'Offline'}</span>
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '12px' }}>
          {[
            { label: 'Notional', value: tgUsdc(construction.hedge_notional_usdc), color: TG_THEME.text },
            { label: 'Circle Ask', value: tgUsdc(construction.circle_testnet_usdc_request), color: TG_THEME.orange },
            { label: 'Action', value: recommendation, color: recommendation === 'Buy' ? TG_THEME.green : TG_THEME.orange },
          ].map((s, i) => (
            <div key={i} style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '18px', fontWeight: 700, color: s.color, fontFamily: 'SF Mono, monospace', overflowWrap: 'anywhere' }}>{s.value}</div>
              <div style={{ fontSize: '11px', color: TG_THEME.secondary, marginTop: '2px' }}>{s.label}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Live signal */}
      <div style={{
        background: `linear-gradient(135deg, ${TG_THEME.green}15, ${TG_THEME.surface})`,
        borderRadius: '12px', padding: '16px', marginBottom: '16px',
        border: `1px solid ${TG_THEME.green}20`,
      }}>
        <div style={{ fontSize: '11px', color: TG_THEME.green, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase', marginBottom: '8px' }}>
          Latest Signal
        </div>
        <div style={{ fontSize: '15px', color: TG_THEME.text, fontWeight: 600, marginBottom: '4px' }}>
          {String(data.direction || 'no_signal').replace('_', ' ')}
        </div>
        <div style={{ fontSize: '13px', color: TG_THEME.secondary }}>
          z = {Number(data.z || 0).toFixed(2)} · S_t = ${data.spread.st || '0.0000'}
        </div>
      </div>
    </div>

    {/* Menu */}
    <div style={{ background: TG_THEME.surface, borderRadius: '12px', margin: '0 16px 16px' }}>
      <TgListItem icon="▦" title="Mock Contract" subtitle="Buy / monitor / sell live-priced basket" accent={TG_THEME.green} onClick={() => setScreen('dashboard')} trailing={<span style={{ color: TG_THEME.secondary }}>›</span>} />
      <TgListItem icon="⌕" title="Agent Scouting" subtitle="IBKR, Polymarket, Opoint/Nebius research" accent={TG_THEME.blue} onClick={() => setScreen('scouting')} trailing={<TgBadge color={TG_THEME.blue}>{searchCount}</TgBadge>} />
      <TgListItem icon="!" title="Alerts" subtitle="Sparse product and runtime updates" accent={TG_THEME.orange} onClick={() => setScreen('alerts')} trailing={<span style={{ color: TG_THEME.secondary }}>›</span>} />
      <TgListItem icon="$" title="Subscription" subtitle="Operator plan · 5 test USDC" accent={TG_THEME.green} onClick={() => setScreen('billing')} trailing={<TgBadge color={TG_THEME.green}>$5</TgBadge>} />
    </div>

    {/* Quick actions */}
    <div style={{ padding: '0 16px 24px' }}>
      <div style={{ fontSize: '13px', color: TG_THEME.secondary, fontWeight: 600, marginBottom: '8px', paddingLeft: '4px' }}>Quick Actions</div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
        {[
          { label: 'Run Scan', icon: '▸', color: TG_THEME.green, screen: 'scan' },
          { label: 'Contract', icon: '◎', color: TG_THEME.orange, screen: 'dashboard' },
        ].map((a, i) => (
          <button key={i} onClick={() => setScreen(a.screen)} style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px',
            padding: '14px', borderRadius: '10px', border: 'none', cursor: 'pointer',
            background: TG_THEME.surface, color: a.color,
            fontSize: '14px', fontWeight: 600,
          }}><span style={{ fontSize: '18px' }}>{a.icon}</span> {a.label}</button>
        ))}
      </div>
    </div>
  </TgScreen>
  );
};

const TgDashboard = ({ setScreen, goBack, data }) => {
  const weightedLegs = tgWeightedLegs(data);
  const searchPlan = tgSearchPlan(data);
  return (
  <TgScreen title="Mock Contract" subtitle="Live-priced demo" onBack={goBack}>
    <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
      {/* Spread */}
      <div style={{ background: TG_THEME.surface, borderRadius: '12px', padding: '16px' }}>
        <div style={{ fontSize: '11px', color: TG_THEME.secondary, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase', marginBottom: '12px' }}>
          Electricity–Compute Spread
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
          {[
            { label: 'Electricity', value: `$${data.spread.elec || '0.00'}`, unit: '/MWh', color: TG_THEME.orange },
            { label: 'Compute', value: `$${data.spread.compute || '0.0000'}`, unit: '/GPU-hr', color: TG_THEME.blue },
            { label: 'Spread S_t', value: `$${data.spread.st || '0.0000'}`, unit: '', color: TG_THEME.green },
            { label: 'Z-Score', value: Number(data.z || 0).toFixed(2), unit: '', color: Math.abs(Number(data.z || 0)) > 1 ? TG_THEME.red : TG_THEME.green },
          ].map((m, i) => (
            <div key={i} style={{ padding: '10px', background: TG_THEME.elevated, borderRadius: '8px' }}>
              <div style={{ fontSize: '11px', color: TG_THEME.secondary }}>{m.label}</div>
              <span style={{ fontSize: '18px', fontWeight: 700, color: m.color, fontFamily: 'SF Mono, monospace' }}>{m.value}</span>
              <span style={{ fontSize: '11px', color: TG_THEME.secondary }}>{m.unit}</span>
            </div>
          ))}
        </div>
      </div>

      {data.syntheticInstrument && (
        <div style={{ background: TG_THEME.surface, borderRadius: '12px', padding: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '10px', alignItems: 'flex-start', marginBottom: '8px' }}>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: '11px', color: TG_THEME.green, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase', marginBottom: '4px' }}>
                Agent Synthetic Proposal
              </div>
              <div style={{ fontSize: '15px', color: TG_THEME.text, fontWeight: 700, lineHeight: 1.25, overflowWrap: 'anywhere' }}>
                {data.syntheticInstrument.instrument_name}
              </div>
            </div>
            <TgBadge color={TG_THEME.green}>LIVE MOCK</TgBadge>
          </div>
          <div style={{ fontSize: '12px', color: TG_THEME.secondary, lineHeight: 1.4, marginBottom: '8px' }}>
            {data.syntheticInstrument.thesis}
          </div>
          <div style={{ fontSize: '12px', color: TG_THEME.secondary, lineHeight: 1.4, marginBottom: '6px' }}>
            Priced hedges: {((data.syntheticInstrument.outputs?.priced_hedge_basket || []).slice(0, 3).map(leg => leg.slug || leg.title).join(', ')) || 'needs live Yahoo/public prices'}
          </div>
          {data.syntheticInstrument.outputs?.mock_hedge_construction && (
            <div style={{ background: TG_THEME.elevated, borderRadius: '8px', padding: '9px', marginBottom: '6px' }}>
              <div style={{ fontSize: '10px', color: TG_THEME.secondary, textTransform: 'uppercase', fontWeight: 700 }}>Buy / monitor mock contract</div>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'baseline', marginTop: '4px' }}>
                <div style={{ fontSize: '13px', color: TG_THEME.text, fontWeight: 700 }}>
                  ${Number(data.syntheticInstrument.outputs.mock_hedge_construction.hedge_notional_usdc || 0).toLocaleString()} notional
                </div>
                <div style={{ fontSize: '13px', color: TG_THEME.orange, fontWeight: 700 }}>
                  ${Number(data.syntheticInstrument.outputs.mock_hedge_construction.circle_testnet_usdc_request || 0).toLocaleString()} test USDC
                </div>
              </div>
              <div style={{ fontSize: '11px', color: TG_THEME.secondary, lineHeight: 1.35, marginTop: '4px' }}>
                {((data.syntheticInstrument.outputs.mock_hedge_construction.weighted_legs || []).slice(0, 3).map(leg => `${leg.side} ${leg.slug} ${Number(leg.weight || 0).toLocaleString(undefined, { style: 'percent', maximumFractionDigits: 0 })}`).join(', '))}
              </div>
              <div style={{ fontSize: '11px', color: TG_THEME.green, lineHeight: 1.35, marginTop: '4px' }}>
                {data.syntheticInstrument.outputs.mock_hedge_construction.recommended_action === 'BUY_CONTRACT' ? 'Agent says buy while profitable; close if a leg drags package PnL red.' : 'Agent says monitor until edge improves.'}
              </div>
            </div>
          )}
          {(data.syntheticInstrument.outputs?.agent_search_plan || []).length > 0 && (
            <div style={{ fontSize: '12px', color: TG_THEME.secondary, lineHeight: 1.4, marginBottom: '6px' }}>
              Agent scouting: {data.syntheticInstrument.outputs.agent_search_plan.slice(0, 2).map(item => `${item.surface}:${item.target}`).join(', ')}
            </div>
          )}
          <div style={{ fontSize: '12px', color: TG_THEME.tertiary, lineHeight: 1.4 }}>
            Next: {(data.syntheticInstrument.outputs?.agent_next_actions || [])[0] || 'wait for stronger signal'}
          </div>
        </div>
      )}

      {/* Live weighted basket */}
      <div style={{ background: TG_THEME.surface, borderRadius: '12px', overflow: 'hidden' }}>
        <div style={{ padding: '12px 16px', fontSize: '11px', color: TG_THEME.secondary, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
          Live-priced basket
        </div>
        <div style={{ padding: '0 16px 10px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px' }}>
          {['1 Spread', '2 Price basket', '3 Buy/monitor', '4 Arc only if EXECUTE'].map((step, i) => (
            <div key={i} style={{ fontSize: '11px', color: TG_THEME.secondary, background: TG_THEME.elevated, borderRadius: '6px', padding: '6px 8px' }}>
              {step}
            </div>
          ))}
        </div>
        <div style={{ padding: '0 16px 10px' }}>
          <div style={{ fontSize: '13px', color: TG_THEME.text, fontWeight: 600 }}>
            {String(data.direction || 'no_signal').replace('_', ' ')}
          </div>
          <div style={{ fontSize: '12px', color: TG_THEME.secondary, marginTop: '2px', lineHeight: 1.35 }}>
            Mock contract is local testnet first. IBKR/Polymarket stay in scouting until they are priced and thesis-matched.
          </div>
        </div>
        {weightedLegs.length ? weightedLegs.slice(0, 8).map((leg, i) => (
          <TgListItem
            key={`${leg.slug || leg.symbol || 'leg'}-${i}`}
            icon={String(leg.side || '').toLowerCase() === 'short' ? '↓' : '↑'}
            title={tgWeightLabel(leg)}
            subtitle={leg.description || `${leg.source || 'public quote'} · ${leg.surface || 'public_market'}`}
            trailing={<span style={{ fontFamily: 'SF Mono, monospace', fontSize: '12px', color: TG_THEME.secondary }}>{leg.last_price ? `$${Number(leg.last_price).toFixed(2)}` : 'priced'}</span>}
          />
        )) : (
          <div style={{ padding: '8px 16px 12px', fontSize: '12px', color: TG_THEME.secondary }}>
            Waiting for live prices before a mock contract is promoted.
          </div>
        )}
      </div>

      <div style={{ background: TG_THEME.surface, borderRadius: '12px', overflow: 'hidden' }}>
        <div style={{ padding: '12px 16px', fontSize: '11px', color: TG_THEME.secondary, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
          Agent scouting
        </div>
        {(searchPlan.length || data.directInventory?.length) ? (
          <>
            {searchPlan.slice(0, 3).map((item, i) => (
              <div key={`${item.surface}-${i}`} style={{ padding: '10px 16px', borderBottom: `0.5px solid ${TG_THEME.separator}` }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'center' }}>
                  <div style={{ fontSize: '13px', color: TG_THEME.text, fontWeight: 700, overflowWrap: 'anywhere' }}>{item.target}</div>
                  <TgBadge color={TG_THEME.blue}>{item.surface}</TgBadge>
                </div>
                <div style={{ fontSize: '11px', color: TG_THEME.secondary, lineHeight: 1.35, marginTop: '4px', overflowWrap: 'anywhere' }}>
                  {item.query || 'searching for thesis-matched priced legs'}
                </div>
              </div>
            ))}
            {(data.directInventory || []).slice(0, 4).map((leg, i) => (
              <TgListItem
                key={`${leg.slug || leg.instrument || 'inventory'}-${i}`}
                icon={surfaceIcon(leg.surface)}
                title={leg.displayName || leg.instrument || leg.slug || 'research leg'}
                subtitle={tgInventorySubtitle(leg)}
                trailing={<span style={{ fontSize: '11px', color: TG_THEME.secondary }}>{tgInventoryTrailing(leg)}</span>}
              />
            ))}
          </>
        ) : (
          <div style={{ padding: '8px 16px 12px', fontSize: '12px', color: TG_THEME.secondary }}>
            No IBKR or Polymarket research legs are currently promoted into scouting.
          </div>
        )}
      </div>
    </div>
  </TgScreen>
  );
};

const TgScouting = ({ setScreen, goBack, data }) => {
  const searchPlan = tgSearchPlan(data);
  return (
  <TgScreen title="Agent Scouting" subtitle="Research only" onBack={goBack}>
    <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
      <div style={{ background: TG_THEME.surface, borderRadius: '10px', padding: '14px', fontSize: '13px', color: TG_THEME.secondary, lineHeight: 1.45 }}>
        These rows are not the contract. The agent uses Opoint/Nebius, IBKR ForecastTrader, and Polymarket to find legs that are actually driven by the compute/energy spread. Public channel posts stay quiet until the mock contract changes or an operator action is needed.
      </div>
      <div style={{ background: TG_THEME.surface, borderRadius: '12px', overflow: 'hidden' }}>
        <div style={{ padding: '12px 16px', fontSize: '11px', color: TG_THEME.secondary, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
          Search queue
        </div>
        {searchPlan.length ? searchPlan.map((item, i) => (
          <div key={`${item.surface}-${i}`} style={{ padding: '12px 16px', borderTop: i ? `0.5px solid ${TG_THEME.separator}` : 'none' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'center' }}>
              <div style={{ fontSize: '14px', color: TG_THEME.text, fontWeight: 700 }}>{item.target || 'spread driver search'}</div>
              <TgBadge color={TG_THEME.blue}>{item.surface || 'agent'}</TgBadge>
            </div>
            <div style={{ fontSize: '12px', color: TG_THEME.secondary, lineHeight: 1.35, marginTop: '5px', overflowWrap: 'anywhere' }}>
              {item.query || 'looking for thesis-matched priced legs'}
            </div>
          </div>
        )) : (
          <div style={{ padding: '12px 16px', fontSize: '12px', color: TG_THEME.secondary }}>
            Search queue is empty in this snapshot.
          </div>
        )}
      </div>
      <div style={{ background: TG_THEME.surface, borderRadius: '12px', overflow: 'hidden' }}>
        <div style={{ padding: '12px 16px', fontSize: '11px', color: TG_THEME.secondary, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
          Research watchlist
        </div>
        {(data.directInventory || []).length ? (data.directInventory || []).slice(0, 10).map((leg, i) => (
          <TgListItem
            key={`${leg.slug || leg.instrument || 'leg'}-${i}`}
            icon={surfaceIcon(leg.surface)}
            title={leg.displayName || leg.instrument || leg.slug || 'research leg'}
            subtitle={tgInventorySubtitle(leg)}
            trailing={<span style={{ fontSize: '11px', color: TG_THEME.secondary }}>{tgInventoryTrailing(leg)}</span>}
          />
        )) : (
          <div style={{ padding: '12px 16px', fontSize: '12px', color: TG_THEME.secondary }}>
            No venue watchlist rows in this snapshot.
          </div>
        )}
      </div>
    </div>
  </TgScreen>
  );
};

const TgAlerts = ({ setScreen, goBack }) => {
  const [alerts, setAlerts] = React.useState({
    signals: true, verdicts: true, positions: true, pnl: false, oracle: false,
  });
  const Toggle = ({ on, onToggle }) => (
    <button onClick={onToggle} style={{
      width: 44, height: 26, borderRadius: 13, border: 'none', cursor: 'pointer',
      background: on ? TG_THEME.green : TG_THEME.elevated, position: 'relative',
      transition: 'background 0.2s',
    }}>
      <div style={{
        width: 22, height: 22, borderRadius: 11, background: '#fff',
        position: 'absolute', top: 2, left: on ? 20 : 2, transition: 'left 0.2s',
      }}></div>
    </button>
  );
  return (
    <TgScreen title="Alert Settings" onBack={goBack}>
      <div style={{ background: TG_THEME.surface, borderRadius: '12px', margin: '16px' }}>
        {Object.entries({ signals: 'Mock Contract Updates', verdicts: 'Buy / Monitor Recommendations', positions: 'Operator Runtime Errors', pnl: 'PnL Drag Warnings', oracle: 'Scouting Evidence Updates' }).map(([k, label]) => (
          <TgListItem key={k} title={label} trailing={
            <Toggle on={alerts[k]} onToggle={() => setAlerts(a => ({ ...a, [k]: !a[k] }))} />
          } />
        ))}
      </div>
    </TgScreen>
  );
};

const TgBilling = ({ setScreen, goBack }) => {
  const [processing, setProcessing] = React.useState(false);
  const [account, setAccount] = React.useState(() => window.readDemoOperatorAccount?.() || null);
  const [error, setError] = React.useState('');
  const paid = account?.status === 'active';

  React.useEffect(() => {
    const refresh = (event) => {
      if (event?.type === 'botozen:account') setAccount(event.detail || null);
      else setAccount(window.readDemoOperatorAccount?.() || null);
    };
    window.addEventListener('storage', refresh);
    window.addEventListener('botozen:account', refresh);
    return () => {
      window.removeEventListener('storage', refresh);
      window.removeEventListener('botozen:account', refresh);
    };
  }, []);

  const completePayment = () => {
    setProcessing(true);
    setError('');
    setTimeout(async () => {
      try {
        const created = await window.createDemoOperatorAccount?.({
          plan: { id: 'operator', name: 'Operator', price: '5', usdc: '5' },
          wallet: window.DEMO_OPERATOR_WALLET,
          txHash: window.DEMO_OPERATOR_TX,
        });
        setAccount(created || window.readDemoOperatorAccount?.() || null);
      } catch (err) {
        setError(String(err.message || err));
      } finally {
        setProcessing(false);
      }
    }, 2500);
  };

  const openWebAccount = () => {
    const url = `${window.location.origin}/account`;
    if (window.Telegram?.WebApp?.openLink) window.Telegram.WebApp.openLink(url);
    else window.location.href = '/account';
  };

  return (
    <TgScreen title="Subscription" onBack={goBack}>
      <div style={{ padding: '16px' }}>
        <div style={{
          background: `linear-gradient(135deg, ${TG_THEME.green}, ${TG_THEME.surface})`,
          borderRadius: '12px', padding: '20px', marginBottom: '16px',
          border: `1px solid ${TG_THEME.green}25`,
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
            <TgBadge color={TG_THEME.green}>Operator Plan</TgBadge>
            <span style={{ fontSize: '13px', color: paid ? TG_THEME.green : TG_THEME.secondary }}>{paid ? 'Active' : 'Trial: 7 days left'}</span>
          </div>
          <div style={{ fontSize: '32px', fontWeight: 800, color: TG_THEME.text, fontFamily: 'SF Mono, monospace' }}>
            5 <span style={{ fontSize: '16px', fontWeight: 500 }}>USDC/mo</span>
          </div>
          <div style={{ fontSize: '12px', color: TG_THEME.secondary, marginTop: '8px', lineHeight: 1.4 }}>
            Operator-lite access: live-priced mock contract, buy/monitor/sell controls, scan commands, and sparse channel alerts.
          </div>
        </div>

        <div style={{ background: TG_THEME.surface, borderRadius: '12px', padding: '16px', marginBottom: '16px' }}>
          <div style={{ fontSize: '13px', fontWeight: 600, color: TG_THEME.text, marginBottom: '12px' }}>Pay with Circle test USDC</div>
          <div style={{ fontSize: '12px', color: TG_THEME.secondary, lineHeight: 1.4, marginBottom: '12px' }}>
            Paid state is now stored server-side and restored by a signed session cookie.
          </div>
          {error && <div style={{ fontSize: '12px', color: TG_THEME.red, marginBottom: '10px' }}>{error}</div>}
          {!paid ? (
            <button
              onClick={completePayment}
              disabled={processing}
              style={{
                width: '100%', padding: '14px', borderRadius: '10px', border: 'none',
                background: processing ? TG_THEME.elevated : TG_THEME.green,
                color: processing ? TG_THEME.secondary : '#000', fontSize: '15px', fontWeight: 700,
                cursor: processing ? 'wait' : 'pointer',
              }}
            >
              {processing ? 'Processing on Arc Testnet...' : 'Pay 5 USDC'}
            </button>
          ) : (
            <div style={{ textAlign: 'center', padding: '8px 0' }}>
              <div style={{ fontSize: '24px', marginBottom: '8px' }}>✓</div>
              <div style={{ fontSize: '15px', fontWeight: 600, color: TG_THEME.green }}>Operator Account Active</div>
              {account?.id && <div style={{ fontSize: '12px', color: TG_THEME.secondary, fontFamily: 'SF Mono, monospace', marginTop: '4px' }}>{account.id}</div>}
              <div style={{ fontSize: '12px', color: TG_THEME.secondary, fontFamily: 'SF Mono, monospace', marginTop: '4px' }}>tx: 0x3fbd...9678</div>
            </div>
          )}
        </div>

        <div style={{ background: TG_THEME.surface, borderRadius: '12px', overflow: 'hidden' }}>
          <TgListItem title="Web Account" subtitle={paid ? 'Open paid Operator workspace' : 'Created after payment'} onClick={openWebAccount} trailing={<span style={{ color: TG_THEME.secondary }}>›</span>} />
          <TgListItem title="Billing History" subtitle={paid ? '1 mock Circle testnet payment' : 'No payments yet'} trailing={<span style={{ color: TG_THEME.secondary }}>›</span>} />
          <TgListItem title="Reset Demo Account" onClick={() => window.clearDemoOperatorAccount?.()} trailing={<span style={{ color: TG_THEME.red }}>Reset</span>} />
        </div>
      </div>
    </TgScreen>
  );
};

const TgScanRunning = ({ setScreen, goBack }) => {
  const [step, setStep] = React.useState(0);
  const [queued, setQueued] = React.useState('');
  const [error, setError] = React.useState('');
  const steps = [
    { text: 'Submitting scan request...', icon: '▸' },
    { text: queued ? `Queued request ${queued}` : 'Waiting for backend queue...', icon: '◎' },
    { text: 'Worker will run the existing judge-gated runtime path', icon: '✓' },
  ];
  React.useEffect(() => {
    let cancelled = false;
    requestBackendScan()
      .then(req => { if (!cancelled) setQueued(req.request_id); })
      .catch(err => { if (!cancelled) setError(String(err.message || err)); });
    return () => { cancelled = true; };
  }, []);
  React.useEffect(() => {
    if (step < steps.length) {
      const t = setTimeout(() => setStep(s => s + 1), 800 + Math.random() * 600);
      return () => clearTimeout(t);
    }
  }, [step]);

  return (
    <TgScreen title="Running Scan" onBack={goBack}>
      <div style={{ padding: '24px 16px' }}>
        {steps.slice(0, step).map((s, i) => (
          <div key={i} style={{
            display: 'flex', alignItems: 'center', gap: '12px',
            padding: '12px', marginBottom: '4px', borderRadius: '8px',
            background: i === step - 1 ? TG_THEME.surface : 'transparent',
            animation: 'fadeIn 0.3s ease',
          }}>
            <span style={{ fontSize: '18px' }}>{s.icon}</span>
            <span style={{ fontSize: '14px', color: i === step - 1 ? TG_THEME.text : TG_THEME.secondary }}>{s.text}</span>
          </div>
        ))}
        {step < steps.length && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '12px' }}>
            <div style={{
              width: 18, height: 18, border: `2px solid ${TG_THEME.tertiary}`,
              borderTopColor: TG_THEME.green, borderRadius: '50%',
              animation: 'spin 1s linear infinite',
            }}></div>
            <span style={{ fontSize: '14px', color: TG_THEME.secondary }}>Processing...</span>
          </div>
        )}
        {step >= steps.length && (
          <div style={{ marginTop: '20px', textAlign: 'center' }}>
            {error && <div style={{ color: TG_THEME.red, fontSize: '13px', marginBottom: '12px' }}>{error}</div>}
            <button onClick={() => setScreen('dashboard')} style={{
              padding: '14px 32px', borderRadius: '10px', border: 'none',
              background: TG_THEME.green, color: '#000', fontSize: '15px', fontWeight: 700, cursor: 'pointer',
            }}>View Mock Contract</button>
          </div>
        )}
      </div>
    </TgScreen>
  );
};

/* ── Telegram Page Wrapper ── */
const TelegramPage = () => {
  const { screen, setScreen, goBack } = useTgScreenRouter();
  const data = useTelegramBackendData();
  const viewport = useViewport();
  const isMobile = viewport.width <= 900;
  const deviceWidth = Math.min(375, Math.max(300, viewport.width - 32));
  const deviceHeight = isMobile ? Math.min(720, Math.max(620, Math.round(deviceWidth * 1.82))) : 700;
  const screens = {
    home: TgHome, dashboard: TgDashboard, scouting: TgScouting,
    alerts: TgAlerts, billing: TgBilling, scan: TgScanRunning,
  };
  const Screen = screens[screen] || TgHome;

  return (
    <div style={{
      padding: isMobile ? '24px 16px 40px' : '40px 32px',
      maxWidth: '1100px', margin: '0 auto',
      display: 'flex', gap: isMobile ? '28px' : '48px', alignItems: isMobile ? 'stretch' : 'flex-start',
      flexDirection: isMobile ? 'column' : 'row',
    }}>
      {/* Description */}
      <div style={{ flex: 1, paddingTop: isMobile ? '4px' : '20px' }}>
        <SectionLabel>Telegram Mini App</SectionLabel>
        <h2 style={{
          fontFamily: THEME.font.heading, fontSize: isMobile ? '30px' : '36px', fontWeight: 800,
          color: THEME.text.primary, letterSpacing: 0, margin: '0 0 16px',
        }}>
          Your desk in<br />your pocket
        </h2>
        <p style={{
          fontFamily: THEME.font.body, fontSize: '16px', lineHeight: 1.7,
          color: THEME.text.secondary, marginBottom: '32px',
        }}>
          Full Mini App experience inside Telegram. Monitor the live-priced mock contract, buy/monitor/sell local testnet tickets, review agent scouting, and pay 5 Circle test USDC without leaving the chat.
        </p>
        <TgWebLinks />

        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {[
            { title: 'Live Mock Contract', desc: 'Real-time electricity-compute basket with notional and Circle ask', IconComp: IconGrid, iconColor: TG_THEME.orange },
            { title: 'Buy / Monitor / Sell', desc: 'Freeze a local ticket, refresh marks, and see which leg drags PnL red', IconComp: IconJudge, iconColor: TG_THEME.green },
            { title: 'Agent Scouting', desc: 'IBKR, Polymarket, and Opoint/Nebius are research inputs only', IconComp: IconArc, iconColor: TG_THEME.blue },
            { title: 'Circle Payments', desc: 'Operator access is 5 test USDC on Arc Testnet', IconComp: IconCoin, iconColor: TG_THEME.orange },
            { title: 'Scan Commands', desc: 'Trigger one-shot scans while public rejects stay muted', IconComp: IconSignal, iconColor: TG_THEME.green },
          ].map((f, i) => (
            <Card key={i} hoverable style={{ padding: '16px', display: 'flex', gap: '14px', alignItems: 'flex-start' }}>
              <f.IconComp size={24} color={f.iconColor} />
              <div>
                <div style={{ fontFamily: THEME.font.heading, fontSize: '15px', fontWeight: 700, color: THEME.text.primary }}>{f.title}</div>
                <div style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.secondary, marginTop: '2px' }}>{f.desc}</div>
              </div>
            </Card>
          ))}
        </div>
      </div>

      {/* Phone frame */}
      <div style={{ flexShrink: 0, alignSelf: isMobile ? 'center' : 'flex-start', maxWidth: '100%' }}>
        <IOSDevice width={deviceWidth} height={deviceHeight} dark>
          <Screen setScreen={setScreen} goBack={goBack} data={data} requestScan={requestBackendScan} />
        </IOSDevice>
      </div>
    </div>
  );
};

const TelegramMiniApp = () => {
  const { screen, setScreen, goBack } = useTgScreenRouter();
  const data = useTelegramBackendData();
  const screens = {
    home: TgHome, dashboard: TgDashboard, scouting: TgScouting,
    alerts: TgAlerts, billing: TgBilling, scan: TgScanRunning,
  };
  const Screen = screens[screen] || TgHome;

  React.useEffect(() => {
    const webApp = window.Telegram?.WebApp;
    if (!webApp) return;
    webApp.ready();
    webApp.expand();
    webApp.setHeaderColor?.(TG_THEME.bg);
    webApp.setBackgroundColor?.(TG_THEME.bg);
  }, []);

  return (
    <div style={{
      height: '100dvh', width: '100vw', overflow: 'hidden',
      background: TG_THEME.bg, color: TG_THEME.text,
    }}>
      <Screen setScreen={setScreen} goBack={goBack} data={data} requestScan={requestBackendScan} />
    </div>
  );
};

Object.assign(window, { TelegramPage, TelegramMiniApp });
