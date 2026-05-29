/* Arc Compute Sec — Telegram Mini App */

const TG_THEME = {
  bg: '#0B0F0E', surface: '#111916', elevated: '#172119',
  separator: '#1E2D25', blue: '#60A5FA', green: '#00DC82',
  red: '#EF4444', orange: '#F59E0B', text: '#FFFFFF',
  secondary: '#A1B5AB', tertiary: '#6B8578',
  accent: '#00DC82', accentBg: '#00DC8215',
  border: '#1E2D25', mono: 'SF Mono, ui-monospace, monospace',
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
  if (low === 'ibkr_forecast_inventory') return 'IBKR ForecastTrader inventory';
  if (low === 'polymarket_direct_watchlist') return 'Polymarket Gamma';
  if (low === 'kalshi_direct_ai_watchlist') return 'Kalshi public API';
  if (low === 'yahoo_finance_chart') return 'External proxy: Yahoo public quotes';
  if (low === 'yahoo_close_history') return 'Yahoo close-history replay';
  if (low === 'alpaca_market_data') return 'External proxy: Alpaca market data';
  return leg.externalProxySource || '';
};

const tgQuoteSourceLabel = tgProxySourceLabel;

const tgRecommendationTone = (construction = {}) => {
  const action = String(construction.recommended_action || '').toUpperCase();
  const label = String(construction.recommendation_label || '').toUpperCase();
  const summary = String(construction.recommendation_summary || '').toUpperCase();
  const text = `${action} ${label} ${summary}`;
  if (action === 'BUY_CONTRACT') return 'buy';
  if (text.includes('SELL') || text.includes('AVOID') || text.includes('CLOSE')) return 'sell';
  if (text.includes('HOLD')) return 'hold';
  return 'monitor';
};

const tgRecommendationColor = (construction = {}) => {
  const tone = tgRecommendationTone(construction);
  if (tone === 'buy') return TG_THEME.green;
  if (tone === 'sell') return TG_THEME.red;
  if (tone === 'hold') return TG_THEME.blue;
  return TG_THEME.orange;
};

const tgRecommendationFallback = (construction = {}) => {
  if (construction.recommended_action === 'BUY_CONTRACT') {
    return 'Agent says hedge now; close if a leg drags package PnL red.';
  }
  const tone = tgRecommendationTone(construction);
  if (tone === 'sell') return 'Do not open fresh exposure; close or avoid local mock tickets until proxy PnL recovers.';
  if (tone === 'hold') return 'Hold or monitor existing exposure; current marks do not justify a fresh buy.';
  return 'Agent says monitor until edge improves.';
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
    background: TG_THEME.bg,
    height: '100%',
    minHeight: '100%',
    display: 'flex',
    flexDirection: 'column',
    boxSizing: 'border-box',
    paddingTop: 'calc(10px + env(safe-area-inset-top, 0px))',
    paddingBottom: 'calc(10px + env(safe-area-inset-bottom, 0px))',
    fontFamily: '-apple-system, "SF Pro Text", sans-serif', ...style,
  }}>
    {/* TG header */}
    <div style={{
      padding: '10px 16px 12px', display: 'flex', alignItems: 'center', gap: '12px',
      borderBottom: `0.5px solid ${TG_THEME.separator}`,
      background: TG_THEME.bg,
      flexShrink: 0,
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
    <div style={{ flex: 1, minHeight: 0, overflow: 'auto', WebkitOverflowScrolling: 'touch' }}>{children}</div>
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

const TgMiniWalkthrough = ({ setScreen, account }) => (
  <div style={{
    background: TG_THEME.surface,
    borderRadius: '12px',
    padding: '14px 16px',
    marginBottom: '16px',
  }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '10px', alignItems: 'center', marginBottom: '10px' }}>
      <div>
        <div style={{ fontSize: '11px', color: TG_THEME.green, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
          Mini App walkthrough
        </div>
        <div style={{ fontSize: '12px', color: TG_THEME.secondary, marginTop: '2px', lineHeight: 1.35 }}>
          Same product as the web desk, compressed for Telegram.
        </div>
      </div>
      <TgBadge color={TG_THEME.green}>NEW</TgBadge>
    </div>
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '7px', marginBottom: '10px' }}>
      {[
        ['1', 'Read signal', 'dashboard'],
        ['2', account ? 'Open ticket' : 'Create account', account ? 'dashboard' : 'billing'],
        ['3', 'Track PnL', account ? 'portfolio' : 'billing'],
        ['4', 'Check venues', 'scouting'],
      ].map(([step, label, screen]) => (
        <button key={step} type="button" onClick={() => setScreen(screen)} style={{
          background: TG_THEME.elevated,
          border: `1px solid ${TG_THEME.border}`,
          borderRadius: '8px',
          padding: '9px 8px',
          textAlign: 'left',
          cursor: 'pointer',
        }}>
          <div style={{ fontSize: '10px', color: TG_THEME.tertiary, fontFamily: TG_THEME.mono }}>step {step}</div>
          <div style={{ fontSize: '12px', color: TG_THEME.text, fontWeight: 800, marginTop: '2px' }}>{label}</div>
        </button>
      ))}
    </div>
    <button type="button" onClick={() => setScreen('updates')} style={{
      width: '100%',
      padding: '11px 12px',
      borderRadius: '9px',
      border: 'none',
      background: TG_THEME.green,
      color: '#000',
      fontSize: '13px',
      fontWeight: 800,
      cursor: 'pointer',
    }}>
      View What Changed
    </button>
  </div>
);

const TG_SCREEN_IDS = new Set(['home', 'dashboard', 'portfolio', 'scouting', 'alerts', 'billing', 'scan', 'updates']);
const TG_RELEASE_STORY = [
  {
    label: 'Home / user path',
    file: 'miniapp-home.png',
    desc: 'Status, notional, Circle ask, Operator setup, and the four-step flow.',
    screen: 'home',
    color: TG_THEME.green,
  },
  {
    label: 'Mock contract',
    file: 'miniapp-contract.png',
    desc: 'Spread metrics, weighted legs, buy/monitor/sell recommendation, and judge gate.',
    screen: 'dashboard',
    color: TG_THEME.orange,
  },
  {
    label: 'Portfolio ledger',
    file: 'miniapp-portfolio.png',
    desc: 'Server-side account, wallet label, open tickets, realized ledger, and net paper PnL.',
    screen: 'portfolio',
    color: TG_THEME.green,
  },
  {
    label: 'Profitability ledger',
    file: 'profitability.png',
    desc: 'Paper ticket replay, latest mark PnL, OOS state, and buy/avoid labels.',
    screen: 'dashboard',
    color: TG_THEME.blue,
  },
  {
    label: 'Venue scouting',
    file: 'venue-copy.png',
    desc: 'IBKR, Polymarket, Kalshi, public quotes, crypto, and Opoint/Nebius roles.',
    screen: 'scouting',
    color: TG_THEME.blue,
  },
];

const useTgScreenRouter = () => {
  const [history, setHistory] = React.useState(() => {
    const params = new URLSearchParams(window.location.search || '');
    const requested = params.get('tg_screen') || params.get('screen');
    return TG_SCREEN_IDS.has(requested) ? ['home', requested] : ['home'];
  });
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
      if (document.visibilityState === 'hidden') return;
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 12000);
      try {
        const resp = await fetch('/api/snapshot', { cache: 'default', signal: controller.signal });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const snapshot = await resp.json();
        if (!cancelled) {
          setData(window.mapSnapshotToDashboardData ? window.mapSnapshotToDashboardData(snapshot) : data);
        }
      } catch (err) {
        if (!cancelled) {
          const message = err?.name === 'AbortError' ? 'HTTP timeout reading /api/snapshot' : String(err.message || err);
          setData(prev => ({ ...prev, connection: { status: 'offline', error: message } }));
        }
      } finally {
        clearTimeout(timeout);
      }
    };
    load();
    const t = setInterval(load, 10000);
    const onVisible = () => {
      if (document.visibilityState === 'visible') load();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      cancelled = true;
      clearInterval(t);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, []);
  return data;
};

const useTelegramAccountData = () => {
  const [state, setState] = React.useState({
    loading: true,
    error: '',
    account: window.readDemoOperatorAccount?.() || null,
    portfolio: null,
  });

  const refresh = React.useCallback(async () => {
    try {
      const account = window.refreshOperatorAccount
        ? await window.refreshOperatorAccount()
        : (window.readDemoOperatorAccount?.() || null);
      setState(prev => ({ ...prev, loading: false, error: '', account: account || null }));
      if (!account || !window.refreshAccountPortfolio) {
        setState(prev => ({ ...prev, portfolio: null }));
        return;
      }
      try {
        const portfolio = await window.refreshAccountPortfolio();
        setState(prev => ({ ...prev, loading: false, error: '', account: account || null, portfolio: portfolio || null }));
      } catch (portfolioErr) {
        setState(prev => ({ ...prev, loading: false, error: '', account: account || null, portfolio: prev.portfolio || null }));
      }
    } catch (err) {
      setState(prev => ({ ...prev, loading: false, error: String(err.message || err) }));
    }
  }, []);

  React.useEffect(() => {
    refresh();
    const t = setInterval(() => {
      if (document.visibilityState !== 'hidden') refresh();
    }, 15000);
    const onAccount = () => refresh();
    const onVisible = () => {
      if (document.visibilityState === 'visible') refresh();
    };
    window.addEventListener('botozen:account', onAccount);
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      clearInterval(t);
      window.removeEventListener('botozen:account', onAccount);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [refresh]);

  return { ...state, refresh };
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
const tgSpreadFamilies = (data) => data.spreadFamilies?.families || [];
const tgSpreadArchetypes = (data) => data.spreadFamilies?.archetypeScoreboard || [];
const tgIndexCoverage = (data) => data.spreadFamilies?.indexCoverage || null;
const tgIndexCatalog = (data) => data.spreadFamilies?.indexCatalog || data.indexCatalog || null;
const tgProxyBaskets = (data) => data.proxyBaskets?.baskets || [];
const tgInstrumentMenu = (data) => data.syntheticInstrument?.outputs?.syndicated_instrument_menu || [];
const tgSpreadTradeMap = (data) => data.syntheticInstrument?.outputs?.spread_archetype_trade_map || [];
const tgProfitabilityLedger = (data) => data.syntheticInstrument?.outputs?.spread_profitability_ledger
  || data.indexCatalog?.profitabilityLedger
  || { realized_note: 'Waiting for backend profitability rows.', rows: [] };
const tgPortfolioSignal = (data) => data.syntheticInstrument?.outputs?.portfolio_signal_summary || null;
const tgVenueCopyMatrix = (data) => data.syntheticInstrument?.outputs?.real_venue_copy_matrix || {};
const tgDirectEventPairs = (data) => data.syntheticInstrument?.outputs?.direct_event_pair_candidates || {};
const tgVenueEvidence = (data) => data.venueEvidence?.rows || [];
const tgOracleEvidence = (data) => data.oracleResults || {};
const tgGoalCoverage = (data) => data.goalCoverage || { overall_status: 'NEEDS_WORK', overall_score: 0, items: [] };
const tgCampaign = (data) => data.telegramCampaign || { posts: [], posted_count: 0, total_posts: 0, pending_count: 0 };
const tgMiniappRelease = (data) => data.telegramMiniappRelease || { posts: [], posted_count: 0, total_posts: 0, pending_count: 0 };
const tgUsdc = (value, fallback = 'Pending') => {
  const n = Number(value || 0);
  return n > 0 ? n.toLocaleString(undefined, { maximumFractionDigits: 0 }) : fallback;
};
const tgMoney = (value, digits = 2) => {
  const n = Number(value || 0);
  return `${n >= 0 ? '+' : '-'}$${Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
};
const tgBestBuyableInstrument = (portfolio) => {
  const instruments = portfolio?.instruments || [];
  return instruments.find(item => item.supportsFreshBuy)
    || instruments.find(item => item.signal === 'ENTER')
    || instruments[0]
    || null;
};
const tgCanOpen = (construction) => {
  const score = Number(construction.entry_signal_score ?? construction.profitability_score ?? 0);
  const threshold = Number(construction.entry_threshold_score ?? 70);
  return construction.recommended_action === 'BUY_CONTRACT'
    && score >= threshold
    && construction.judge_verdict?.label === 'EXECUTE';
};
const tgRecommendation = (construction) => tgCanOpen(construction)
  ? (construction.recommendation_label || 'Open paper hedge')
  : (construction.recommendation_label || 'Monitor');
const tgWeightLabel = (leg) => `${leg.side || 'hold'} ${leg.slug || leg.symbol || 'leg'} ${Number(leg.weight || 0).toLocaleString(undefined, { style: 'percent', maximumFractionDigits: 0 })}`;

/* ── Mini App Screens ── */

const TgHome = ({ setScreen, data, accountData, requestScan }) => {
  const construction = tgMockConstruction(data);
  const searchCount = tgSearchPlan(data).length + (data.directInventory?.length || 0);
  const recommendation = tgRecommendation(construction);
  const recommendationColor = tgCanOpen(construction) ? TG_THEME.green : TG_THEME.orange;
  const recommendationParts = String(recommendation || 'Monitor').split(':');
  const recommendationHeadline = recommendationParts[0] || 'Monitor';
  const recommendationHint = recommendationParts.slice(1).join(':').trim();
  const account = accountData?.account || null;
  const summary = accountData?.portfolio?.summary || {};
  const openCount = Number(summary.openCount || 0);
  const netPnl = Number(summary.netPnlUsdc || 0);
  const goalCoverage = tgGoalCoverage(data);
  const coverageItems = (goalCoverage.items || []).slice(0, 5);
  const requirementItems = (goalCoverage.requirements || []).slice(0, 5);
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
            { label: 'Action', value: recommendationHeadline, hint: recommendationHint, color: recommendationColor },
          ].map((s, i) => (
            <div key={i} style={{ textAlign: 'center' }}>
              <div style={{ fontSize: String(s.value).length > 9 ? '15px' : '18px', fontWeight: 700, color: s.color, fontFamily: 'SF Mono, monospace', overflowWrap: 'anywhere', lineHeight: 1.15 }}>{s.value}</div>
              {s.hint && <div style={{ fontSize: '9px', color: TG_THEME.tertiary, lineHeight: 1.2, marginTop: '2px', overflowWrap: 'anywhere' }}>{s.hint}</div>}
              <div style={{ fontSize: '11px', color: TG_THEME.secondary, marginTop: '2px' }}>{s.label}</div>
            </div>
          ))}
        </div>
      </div>

      <TgMiniWalkthrough setScreen={setScreen} account={account} />

      {coverageItems.length > 0 && (
        <div style={{
          background: TG_THEME.surface,
          borderRadius: '12px',
          padding: '14px 16px',
          marginBottom: '16px',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '10px', alignItems: 'center', marginBottom: '10px' }}>
            <div>
              <div style={{ fontSize: '11px', color: TG_THEME.green, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                Goal coverage
              </div>
              <div style={{ fontSize: '11px', color: TG_THEME.secondary, lineHeight: 1.35, marginTop: '2px' }}>
                {goalCoverage.summary || 'Backend readiness telemetry.'}
              </div>
            </div>
            <TgBadge color={goalCoverage.overall_status === 'READY' ? TG_THEME.green : TG_THEME.orange}>
              {Math.round(Number(goalCoverage.overall_score || 0))}%
            </TgBadge>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '6px' }}>
            {(requirementItems.length ? requirementItems : coverageItems).map(item => (
              <div key={item.id} style={{ background: TG_THEME.elevated, borderRadius: '8px', padding: '8px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'flex-start' }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: '12px', color: TG_THEME.text, fontWeight: 800, overflowWrap: 'anywhere' }}>{item.label}</div>
                    <div style={{ fontSize: '10px', color: TG_THEME.tertiary, lineHeight: 1.3, marginTop: '2px' }}>
                      {item.metric || `${Number(item.score || 0).toFixed(0)}% proven`}
                    </div>
                  </div>
                  <div style={{ fontSize: '10px', color: item.status === 'READY' ? TG_THEME.green : TG_THEME.orange, fontWeight: 800, textAlign: 'right' }}>
                    {String(item.status || '').replaceAll('_', ' ')}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div style={{
        background: TG_THEME.surface,
        borderRadius: '12px',
        padding: '14px 16px',
        marginBottom: '16px',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '10px', alignItems: 'center', marginBottom: '8px' }}>
          <div>
            <div style={{ fontSize: '11px', color: TG_THEME.green, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase' }}>Account</div>
            <div style={{ fontSize: '13px', color: TG_THEME.secondary, marginTop: '2px' }}>
              {account ? `${account.id} · ${openCount} open tickets` : 'No signed Operator workspace'}
            </div>
          </div>
          <TgBadge color={account ? TG_THEME.green : TG_THEME.orange}>{account ? 'ACTIVE' : 'SETUP'}</TgBadge>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
          <div style={{ background: TG_THEME.elevated, borderRadius: '8px', padding: '8px' }}>
            <div style={{ fontSize: '10px', color: TG_THEME.tertiary }}>Net paper PnL</div>
            <div style={{ fontSize: '14px', color: netPnl < 0 ? TG_THEME.red : TG_THEME.green, fontFamily: TG_THEME.mono, fontWeight: 800 }}>{tgMoney(netPnl)}</div>
          </div>
          <button onClick={() => setScreen(account ? 'portfolio' : 'billing')} style={{
            background: account ? TG_THEME.green : TG_THEME.orange,
            color: '#000', border: 'none', borderRadius: '8px', fontSize: '13px', fontWeight: 800,
            cursor: 'pointer',
          }}>
            {account ? 'Open Portfolio' : 'Create Account'}
          </button>
        </div>
      </div>

      <div style={{
        background: TG_THEME.surface,
        borderRadius: '12px',
        padding: '14px 16px',
        marginBottom: '16px',
      }}>
        <div style={{ fontSize: '11px', color: TG_THEME.green, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase', marginBottom: '10px' }}>
          Telegram surfaces
        </div>
        <TgWebLinks />
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
        {data.spread.source && (
          <div style={{ fontSize: '11px', color: TG_THEME.tertiary, marginTop: '4px', lineHeight: 1.35 }}>
            elec: {data.spread.source === 'eia_plus_power_proxy' ? 'EIA + power proxy' : data.spread.source.replaceAll('_', ' ')}
            {data.spread.proxyMovePct !== null && data.spread.proxyMovePct !== undefined
              ? ` · ${Number(data.spread.proxyMovePct) >= 0 ? '+' : ''}${Number(data.spread.proxyMovePct).toFixed(2)}%`
              : ''}
          </div>
        )}
      </div>
    </div>

    {/* Menu */}
    <div style={{ background: TG_THEME.surface, borderRadius: '12px', margin: '0 16px 16px' }}>
      <TgListItem icon="▦" title="Mock Contract" subtitle="Buy / monitor / sell live-priced basket" accent={TG_THEME.green} onClick={() => setScreen('dashboard')} trailing={<span style={{ color: TG_THEME.secondary }}>›</span>} />
      <TgListItem icon="$" title="My Portfolio" subtitle={account ? 'Server-side account PnL and paper tickets' : 'Create account before saving tickets'} accent={TG_THEME.green} onClick={() => setScreen(account ? 'portfolio' : 'billing')} trailing={<TgBadge color={account ? TG_THEME.green : TG_THEME.orange}>{account ? `${openCount}` : 'setup'}</TgBadge>} />
      <TgListItem icon="⌕" title="Agent Scouting" subtitle="IBKR, Polymarket, Opoint/Nebius research" accent={TG_THEME.blue} onClick={() => setScreen('scouting')} trailing={<TgBadge color={TG_THEME.blue}>{searchCount}</TgBadge>} />
      <TgListItem icon="★" title="What Changed" subtitle="Mini App release notes and screenshot map" accent={TG_THEME.orange} onClick={() => setScreen('updates')} trailing={<TgBadge color={TG_THEME.orange}>new</TgBadge>} />
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

const TgDashboard = ({ setScreen, goBack, data, accountData }) => {
  const weightedLegs = tgWeightedLegs(data);
  const searchPlan = tgSearchPlan(data);
  const construction = tgMockConstruction(data);
  const account = accountData?.account || null;
  const portfolio = accountData?.portfolio || null;
  const buyable = tgBestBuyableInstrument(portfolio);
  const summary = portfolio?.summary || {};
  const indexCatalog = tgIndexCatalog(data);
  const profitabilityLedger = tgProfitabilityLedger(data);
  const [ticketBusy, setTicketBusy] = React.useState(false);
  const [ticketError, setTicketError] = React.useState('');
  const [ticketDone, setTicketDone] = React.useState('');
  const openMiniTicket = async () => {
    if (!account) {
      setScreen('billing');
      return;
    }
    if (!buyable?.id) {
      setTicketError('No backend instrument is currently available for a paper ticket.');
      return;
    }
    setTicketBusy(true);
    setTicketError('');
    setTicketDone('');
    try {
      const notional = Math.max(50, Number(buyable.circleAskUsdc || construction.circle_testnet_usdc_request || 500));
      await window.openPaperPosition?.({ instrumentId: buyable.id, notionalUsdc: notional });
      await accountData?.refresh?.();
      setTicketDone(`Opened ${buyable.name || buyable.id}`);
    } catch (err) {
      setTicketError(String(err.message || err));
    } finally {
      setTicketBusy(false);
    }
  };
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
            { label: 'Power Share', value: data.spread.powerSharePct === null || data.spread.powerSharePct === undefined ? '-' : `${Number(data.spread.powerSharePct).toFixed(2)}%`, unit: '', color: Number(data.spread.powerSharePct || 0) < 2.5 ? TG_THEME.orange : TG_THEME.green },
            { label: 'Z-Score', value: Number(data.z || 0).toFixed(2), unit: '', color: Math.abs(Number(data.z || 0)) > 1 ? TG_THEME.red : TG_THEME.green },
          ].map((m, i) => (
            <div key={i} style={{ padding: '10px', background: TG_THEME.elevated, borderRadius: '8px' }}>
              <div style={{ fontSize: '11px', color: TG_THEME.secondary }}>{m.label}</div>
              <span style={{ fontSize: '18px', fontWeight: 700, color: m.color, fontFamily: 'SF Mono, monospace' }}>{m.value}</span>
              <span style={{ fontSize: '11px', color: TG_THEME.secondary }}>{m.unit}</span>
            </div>
          ))}
        </div>
        {data.spread.source && (
          <div style={{ fontSize: '11px', color: TG_THEME.tertiary, lineHeight: 1.35, marginTop: '10px' }}>
            Electricity mark: {data.spread.source === 'eia_plus_power_proxy' ? 'EIA anchor + public power/fuel proxy' : data.spread.source.replaceAll('_', ' ')}
            {data.spread.baseElec ? ` · base $${Number(data.spread.baseElec).toFixed(2)}/MWh` : ''}
            {data.spread.proxyMovePct !== null && data.spread.proxyMovePct !== undefined
              ? ` · move ${Number(data.spread.proxyMovePct) >= 0 ? '+' : ''}${Number(data.spread.proxyMovePct).toFixed(2)}%`
              : ''}
          </div>
        )}
        {data.spread.powerSharePct !== null && data.spread.powerSharePct !== undefined && Number(data.spread.powerSharePct) < 2.5 && (
          <div style={{ fontSize: '11px', color: TG_THEME.orange, lineHeight: 1.35, marginTop: '8px' }}>
            Weak energy materiality: this cloud mark is mostly compute-price movement unless proxy baskets and direct events confirm the power thesis.
          </div>
        )}
        {tgSpreadArchetypes(data).length > 0 && (
          <div style={{ marginTop: '12px' }}>
            <div style={{ fontSize: '11px', color: TG_THEME.secondary, fontWeight: 700, marginBottom: '6px' }}>Oil-style spread menu</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {tgSpreadArchetypes(data).slice(0, 4).map(item => (
                <div key={item.archetype_id} style={{ background: TG_THEME.elevated, borderRadius: '8px', padding: '8px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'flex-start' }}>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: '12px', color: TG_THEME.text, fontWeight: 700, overflowWrap: 'anywhere' }}>{item.label}</div>
                      <div style={{ fontSize: '10px', color: TG_THEME.tertiary, lineHeight: 1.35 }}>
                        {item.oil_analogy} · {item.strategy_label || item.evidence_level || 'planned'}
                      </div>
                    </div>
                    <div style={{ fontSize: '10px', color: item.is_promotable ? TG_THEME.green : (item.evidence_level === 'planned' ? TG_THEME.tertiary : TG_THEME.orange), fontWeight: 800, textAlign: 'right' }}>
                      {String(item.replay_status || '').replaceAll('_', ' ')}
                    </div>
                  </div>
                  <div style={{ fontSize: '10px', color: TG_THEME.secondary, lineHeight: 1.35, marginTop: '4px' }}>
                    z {Number(item.latest_z || 0).toFixed(2)} · {item.tested_trades || 0} trades · WR {Number(item.win_rate || 0).toFixed(0)}%
                    {item.oos_status ? ` · OOS ${String(item.oos_status).replaceAll('_', ' ')} ${Number(item.oos_test_pnl_per_unit || 0).toFixed(2)}` : ''}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
        {indexCatalog && (
          <div style={{ marginTop: '12px' }}>
            <div style={{ fontSize: '11px', color: TG_THEME.secondary, fontWeight: 700, marginBottom: '6px' }}>Index catalog</div>
            {tgIndexCoverage(data)?.summary && (
              <div style={{ background: TG_THEME.elevated, borderRadius: '8px', padding: '8px', marginBottom: '6px' }}>
                <div style={{ fontSize: '10px', color: TG_THEME.secondary, lineHeight: 1.35 }}>
                  {tgIndexCoverage(data).summary}
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '5px', marginTop: '6px' }}>
                  {[
                    ['power', `${tgIndexCoverage(data).electricity?.usable || 0}/${tgIndexCoverage(data).electricity?.total || 0}`, TG_THEME.orange],
                    ['compute', `${tgIndexCoverage(data).compute?.usable || 0}/${tgIndexCoverage(data).compute?.total || 0}`, TG_THEME.blue],
                    ['spreads', `${tgIndexCoverage(data).spread_archetypes?.replayed || 0}/${tgIndexCoverage(data).spread_archetypes?.total || 0}`, TG_THEME.green],
                  ].map(([label, value, color]) => (
                    <div key={label} style={{ background: TG_THEME.surface, borderRadius: '6px', padding: '6px', minWidth: 0 }}>
                      <div style={{ fontSize: '9px', color: TG_THEME.tertiary, textTransform: 'uppercase' }}>{label}</div>
                      <div style={{ fontSize: '11px', color, fontFamily: TG_THEME.mono, fontWeight: 800 }}>{value}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {[
              ['Electricity', indexCatalog.electricity || indexCatalog.electricityIndexes || []],
              ['Compute', indexCatalog.compute || indexCatalog.computeIndexes || []],
              ['Spread forms', indexCatalog.spread_archetypes || indexCatalog.spreadArchetypes || []],
            ].map(([label, rows]) => (
              <div key={label} style={{ background: TG_THEME.elevated, borderRadius: '8px', padding: '8px', marginBottom: '6px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'center', marginBottom: '5px' }}>
                  <div style={{ fontSize: '11px', color: TG_THEME.text, fontWeight: 800 }}>{label}</div>
                  <div style={{ fontSize: '10px', color: TG_THEME.tertiary, fontWeight: 800 }}>{rows.length}</div>
                </div>
                {(rows || []).slice(0, 3).map(item => (
                  <div key={item.id} style={{ borderTop: `1px solid ${TG_THEME.border}`, paddingTop: '5px', marginTop: '5px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px' }}>
                      <div style={{ minWidth: 0, fontSize: '11px', color: TG_THEME.text, fontWeight: 700, overflowWrap: 'anywhere' }}>{item.label}</div>
                      <div style={{ fontSize: '9px', color: String(item.status || '').includes('active') ? TG_THEME.green : TG_THEME.orange, fontWeight: 800, textAlign: 'right' }}>
                        {String(item.status || 'planned').replaceAll('_', ' ')}
                      </div>
                    </div>
                    <div style={{ fontSize: '9px', color: TG_THEME.tertiary, lineHeight: 1.35, marginTop: '2px' }}>
                      {item.role || item.oil_analogy || item.venue || ''}
                    </div>
                  </div>
                ))}
              </div>
            ))}
          </div>
        )}
        {tgSpreadFamilies(data).length > 0 && (
          <div style={{ marginTop: '12px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'center', marginBottom: '6px' }}>
              <div style={{ fontSize: '11px', color: TG_THEME.secondary, fontWeight: 700 }}>Spread-family replay</div>
              <TgBadge color={data.spreadFamilies?.entryGatePass ? TG_THEME.green : TG_THEME.orange}>
                {data.spreadFamilies?.entryGatePass ? 'PASS' : 'MONITOR'}
              </TgBadge>
            </div>
            {data.spreadFamilies?.primarySource && (
              <div style={{ fontSize: '10px', color: TG_THEME.tertiary, lineHeight: 1.35, marginBottom: '6px' }}>
                source: {String(data.spreadFamilies.primarySource).replaceAll('_', ' ')}
              </div>
            )}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {tgSpreadFamilies(data).slice(0, 3).map(family => (
                <div key={`${family.family_id}-${family.strategy_id || 'default'}`} style={{ background: TG_THEME.elevated, borderRadius: '8px', padding: '8px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'flex-start' }}>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: '12px', color: TG_THEME.text, fontWeight: 700, overflowWrap: 'anywhere' }}>{family.label}</div>
                      <div style={{ fontSize: '10px', color: TG_THEME.tertiary, lineHeight: 1.35 }}>
                        {family.strategy_label || 'Replay'} · z {Number(family.latest_z || 0).toFixed(2)} · {family.tested_trades || 0} trades · WR {Number(family.win_rate || 0).toFixed(0)}%
                        {family.oos_status ? ` · OOS ${String(family.oos_status).replaceAll('_', ' ')} ${Number(family.oos_test_pnl_per_unit || 0).toFixed(2)}` : ''}
                      </div>
                    </div>
                    <div style={{ fontSize: '10px', color: family.is_promotable ? TG_THEME.green : TG_THEME.orange, fontWeight: 800, textAlign: 'right' }}>
                      {String(family.status || '').replaceAll('_', ' ')}
                    </div>
                  </div>
                  <div style={{ fontSize: '10px', color: TG_THEME.secondary, lineHeight: 1.35, marginTop: '4px' }}>
                    {family.status_reason}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
        {tgProxyBaskets(data).length > 0 && (
          <div style={{ marginTop: '12px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'center', marginBottom: '6px' }}>
              <div style={{ fontSize: '11px', color: TG_THEME.secondary, fontWeight: 700 }}>Proxy basket replay</div>
              <TgBadge color={data.proxyBaskets?.entryGatePass ? TG_THEME.green : TG_THEME.orange}>
                {data.proxyBaskets?.entryGatePass ? 'PASS' : 'MONITOR'}
              </TgBadge>
            </div>
            {tgProxyBaskets(data).slice(0, 2).map(basket => (
              <div key={basket.basket_id} style={{ background: TG_THEME.elevated, borderRadius: '8px', padding: '8px', marginBottom: '6px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'flex-start' }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: '12px', color: TG_THEME.text, fontWeight: 700, overflowWrap: 'anywhere' }}>{basket.label}</div>
                    <div style={{ fontSize: '10px', color: TG_THEME.tertiary, lineHeight: 1.35 }}>
                      {(basket.latest_signal || 'MONITOR').replaceAll('_', ' ')} · 5d {Number(basket.trailing_returns?.['5d']?.return_pct || 0).toFixed(1)}% · 1m {Number(basket.trailing_returns?.['1m']?.return_pct || 0).toFixed(1)}%
                    </div>
                    <div style={{ fontSize: '10px', color: TG_THEME.tertiary, lineHeight: 1.35 }}>
                      {basket.recommendation?.replaceAll('_', ' ') || 'MONITOR'} · total {Number(basket.total_return_pct || 0).toFixed(1)}% · WR {Number(basket.win_rate || 0).toFixed(0)}%
                    </div>
                  </div>
                  <div style={{ fontSize: '10px', color: basket.latest_signal === 'SELL' ? TG_THEME.red : (basket.latest_signal === 'BUY' ? TG_THEME.green : TG_THEME.orange), fontWeight: 800, textAlign: 'right' }}>
                    {String(basket.latest_signal || basket.status || '').replaceAll('_', ' ')}
                  </div>
                </div>
                <div style={{ fontSize: '10px', color: TG_THEME.secondary, lineHeight: 1.35, marginTop: '4px' }}>
                  {basket.signal_reason || basket.status_reason}
                </div>
              </div>
            ))}
          </div>
        )}
        {data.pnl && (
          <div style={{ marginTop: '12px', background: TG_THEME.elevated, borderRadius: '8px', padding: '9px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'center' }}>
              <div style={{ fontSize: '11px', color: TG_THEME.secondary, fontWeight: 700 }}>Settled PnL ledger</div>
              <TgBadge color={data.pnl.hasReconciled ? TG_THEME.green : TG_THEME.orange}>
                {data.pnl.statusLabel || 'No settled PnL'}
              </TgBadge>
            </div>
            <div style={{ fontSize: '10px', color: TG_THEME.secondary, lineHeight: 1.35, marginTop: '5px' }}>
              {data.pnl.totalDisplay || 'No settled PnL'} · {data.pnl.tradesDisplay || '0 settled'} trades. Replay and local tickets are not realized PnL.
            </div>
          </div>
        )}
      </div>

      <div style={{ background: TG_THEME.surface, borderRadius: '12px', padding: '16px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'center', marginBottom: '10px' }}>
          <div>
            <div style={{ fontSize: '11px', color: TG_THEME.green, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase' }}>Account ticket</div>
            <div style={{ fontSize: '12px', color: TG_THEME.secondary, marginTop: '2px' }}>
              {account ? `${account.id} · ${summary.openCount || 0} open` : 'Sign in before a ticket can be saved'}
            </div>
          </div>
          <TgBadge color={account ? TG_THEME.green : TG_THEME.orange}>{account ? 'SERVER' : 'NO ACCOUNT'}</TgBadge>
        </div>
        <div style={{ background: TG_THEME.elevated, borderRadius: '8px', padding: '9px', marginBottom: '10px' }}>
          <div style={{ fontSize: '12px', color: TG_THEME.text, fontWeight: 700, overflowWrap: 'anywhere' }}>
            {buyable?.name || 'No syndicated note available yet'}
          </div>
          <div style={{ fontSize: '10px', color: TG_THEME.secondary, lineHeight: 1.35, marginTop: '3px' }}>
            {buyable ? `${buyable.latestSignal || buyable.signal || 'MONITOR'} · ${buyable.profitabilityStatus || buyable.status || 'watch'} · ask ${tgUsdc(buyable.circleAskUsdc, 'not sized')} test USDC` : 'Run a scan or wait for the backend instrument menu.'}
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginBottom: '10px' }}>
          <div style={{ background: TG_THEME.elevated, borderRadius: '8px', padding: '8px' }}>
            <div style={{ fontSize: '10px', color: TG_THEME.tertiary }}>Unrealized</div>
            <div style={{ fontSize: '13px', color: Number(summary.unrealizedPnlUsdc || 0) < 0 ? TG_THEME.red : TG_THEME.green, fontFamily: TG_THEME.mono, fontWeight: 800 }}>{tgMoney(summary.unrealizedPnlUsdc || 0)}</div>
          </div>
          <div style={{ background: TG_THEME.elevated, borderRadius: '8px', padding: '8px' }}>
            <div style={{ fontSize: '10px', color: TG_THEME.tertiary }}>Realized</div>
            <div style={{ fontSize: '13px', color: Number(summary.realizedPnlUsdc || 0) < 0 ? TG_THEME.red : TG_THEME.green, fontFamily: TG_THEME.mono, fontWeight: 800 }}>{tgMoney(summary.realizedPnlUsdc || 0)}</div>
          </div>
        </div>
        {ticketError && <div style={{ fontSize: '11px', color: TG_THEME.red, lineHeight: 1.35, marginBottom: '8px' }}>{ticketError}</div>}
        {ticketDone && <div style={{ fontSize: '11px', color: TG_THEME.green, lineHeight: 1.35, marginBottom: '8px' }}>{ticketDone}</div>}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
          <button onClick={openMiniTicket} disabled={ticketBusy || !buyable} style={{
            padding: '12px', borderRadius: '9px', border: 'none',
            background: account ? TG_THEME.green : TG_THEME.orange,
            color: '#000', fontSize: '13px', fontWeight: 800,
            cursor: ticketBusy || !buyable ? 'wait' : 'pointer',
            opacity: ticketBusy || !buyable ? 0.65 : 1,
          }}>
            {account ? (ticketBusy ? 'Opening...' : 'Open Paper Ticket') : 'Create Account'}
          </button>
          <button onClick={() => setScreen('portfolio')} style={{
            padding: '12px', borderRadius: '9px', border: `1px solid ${TG_THEME.separator}`,
            background: TG_THEME.elevated, color: TG_THEME.text, fontSize: '13px', fontWeight: 800,
            cursor: 'pointer',
          }}>
            Portfolio
          </button>
        </div>
        <div style={{ fontSize: '10px', color: TG_THEME.tertiary, lineHeight: 1.35, marginTop: '8px' }}>
          This saves a paper ticket to the backend account ledger. It is not an IBKR, Polymarket, Circle, or Arc order.
        </div>
      </div>

      {tgInstrumentMenu(data).length > 0 && (
        <div style={{ background: TG_THEME.surface, borderRadius: '12px', padding: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'center', marginBottom: '8px' }}>
            <div style={{ fontSize: '11px', color: TG_THEME.green, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
              Syndicated structures
            </div>
            <TgBadge color={TG_THEME.orange}>NOT ABS YET</TgBadge>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {tgInstrumentMenu(data).slice(0, 4).map(item => (
              <div key={item.instrument_type} style={{ background: TG_THEME.elevated, borderRadius: '8px', padding: '8px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'flex-start' }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: '12px', color: TG_THEME.text, fontWeight: 700, overflowWrap: 'anywhere' }}>{item.title}</div>
                    <div style={{ fontSize: '10px', color: TG_THEME.tertiary, lineHeight: 1.35 }}>
                      {item.direction_aligned ? 'active spread · ' : ''}{item.spread_archetype} · {String(item.basket_direction || 'unmapped').replaceAll('_', ' ')}
                    </div>
                    <div style={{ fontSize: '10px', color: TG_THEME.tertiary, lineHeight: 1.35 }}>
                      5d {Number(item.trailing_returns?.['5d']?.return_pct || 0).toFixed(1)}% · 1m {Number(item.trailing_returns?.['1m']?.return_pct || 0).toFixed(1)}%
                    </div>
                  </div>
                  <div style={{ fontSize: '10px', color: item.latest_signal === 'SELL' ? TG_THEME.red : (item.latest_signal === 'BUY' ? TG_THEME.green : TG_THEME.orange), fontWeight: 800, textAlign: 'right' }}>
                    {item.latest_signal || 'MONITOR'}
                  </div>
                </div>
                <div style={{ fontSize: '10px', color: TG_THEME.secondary, lineHeight: 1.35, marginTop: '4px' }}>
                  {item.status?.replaceAll('_', ' ')} · {item.status_reason}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {tgPortfolioSignal(data)?.rows?.length > 0 && (
        <div style={{ background: TG_THEME.surface, borderRadius: '12px', padding: '16px' }}>
          {(() => {
            const summary = tgPortfolioSignal(data);
            const action = String(summary.action || 'MONITOR');
            const color = action.includes('OPEN') || action === 'ROTATE'
              ? TG_THEME.green
              : (action.includes('CLOSE') || action.includes('AVOID') ? TG_THEME.red : TG_THEME.orange);
            return (
              <>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'center', marginBottom: '8px' }}>
                  <div style={{ fontSize: '11px', color: TG_THEME.green, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                    Portfolio signal
                  </div>
                  <TgBadge color={color}>{action.replaceAll('_', ' ')}</TgBadge>
                </div>
                <div style={{ fontSize: '13px', color: TG_THEME.text, fontWeight: 700, lineHeight: 1.35, marginBottom: '6px' }}>
                  {summary.headline || 'Monitor spread portfolio'}
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px', marginBottom: '8px' }}>
                  {[
                    ['ticket', summary.paper_ticket_total_pnl_usdc],
                    ['mark', summary.latest_mark_total_pnl_usdc],
                  ].map(([label, value]) => (
                    <div key={label} style={{ background: TG_THEME.elevated, borderRadius: '8px', padding: '7px' }}>
                      <div style={{ fontSize: '9px', color: TG_THEME.tertiary, textTransform: 'uppercase' }}>{label} PnL</div>
                      <div style={{ fontSize: '12px', color: Number(value || 0) < 0 ? TG_THEME.red : TG_THEME.green, fontFamily: TG_THEME.mono, fontWeight: 700 }}>
                        ${Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}
                      </div>
                    </div>
                  ))}
                </div>
                <div style={{ fontSize: '10px', color: TG_THEME.secondary, lineHeight: 1.35 }}>
                  {Number(summary.buy_count || 0)} buy · {Number(summary.close_or_avoid_count || 0)} avoid/sell · {Number(summary.wait_count || 0)} wait. Arc stays locked until judge.classify() returns EXECUTE.
                </div>
              </>
            );
          })()}
        </div>
      )}

      {profitabilityLedger && (
        <div style={{ background: TG_THEME.surface, borderRadius: '12px', padding: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'center', marginBottom: '8px' }}>
            <div style={{ fontSize: '11px', color: TG_THEME.green, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
              Profitability ledger
            </div>
            <TgBadge color={TG_THEME.orange}>PAPER PNL</TgBadge>
          </div>
          <div style={{ fontSize: '10px', color: TG_THEME.tertiary, lineHeight: 1.35, marginBottom: '8px' }}>
            {profitabilityLedger.realized_note}
            {profitabilityLedger.paper_notional_usdc
              ? ` Paper notional $${Number(profitabilityLedger.paper_notional_usdc).toLocaleString()}.`
              : ''}
            {' First mark is the entry baseline; $0 there is expected.'}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {(profitabilityLedger.rows || []).length ? profitabilityLedger.rows.slice(0, 4).map(row => {
              const status = row.profitability_status || 'MONITOR';
              const color = status === 'PAPER_BUY'
                ? TG_THEME.green
                : (String(status).includes('SELL') || String(status).includes('AVOID') ? TG_THEME.red : TG_THEME.orange);
              const latestPnl = row.latest_paper_pnl_usdc === '' || row.latest_paper_pnl_usdc === undefined
                ? null
                : Number(row.latest_paper_pnl_usdc || 0);
              const tradePnl = row.paper_trade_total_pnl_usdc === '' || row.paper_trade_total_pnl_usdc === undefined
                ? null
                : Number(row.paper_trade_total_pnl_usdc || 0);
              const pnlColor = latestPnl === null ? TG_THEME.tertiary : (latestPnl < 0 ? TG_THEME.red : TG_THEME.green);
              const tradeColor = tradePnl === null ? TG_THEME.tertiary : (tradePnl < 0 ? TG_THEME.red : TG_THEME.green);
              const recentMarks = row.recent_paper_marks || [];
              const tradeReplay = row.paper_trade_replay || {};
              const openTrade = tradeReplay.open_trade || null;
              const closedTrades = tradeReplay.closed_trades || [];
              const oosText = row.oos_status && row.oos_status !== 'NO_OOS_REPLAY'
                ? `OOS ${String(row.oos_status).replaceAll('_', ' ')} ${row.oos_test_return_pct === '' || row.oos_test_return_pct === undefined ? '' : `${Number(row.oos_test_return_pct).toFixed(1)}%`}`
                : 'OOS -';
              const oosColor = row.oos_status === 'FAILED'
                ? TG_THEME.red
                : (row.oos_status === 'PASSED' ? TG_THEME.green : TG_THEME.tertiary);
              return (
                <div key={row.archetype_id} style={{ background: TG_THEME.elevated, borderRadius: '8px', padding: '8px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'flex-start' }}>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: '12px', color: TG_THEME.text, fontWeight: 700, overflowWrap: 'anywhere' }}>#{row.rank} {row.label}</div>
                      <div style={{ fontSize: '10px', color: TG_THEME.tertiary, lineHeight: 1.35 }}>
                        {(row.expression_title || row.basket_id || 'No expression')} · {row.latest_signal || 'MONITOR'}
                      </div>
                      <div style={{ fontSize: '10px', color: TG_THEME.tertiary, lineHeight: 1.35 }}>
                        5d {Number(row.paper_5d_return_pct || 0).toFixed(1)}% · 1m {Number(row.paper_1m_return_pct || 0).toFixed(1)}% · WR {Number(row.paper_win_rate || row.spread_replay_win_rate || 0).toFixed(0)}%
                      </div>
                      <div style={{ fontSize: '10px', color: pnlColor, fontFamily: TG_THEME.mono, lineHeight: 1.35 }}>
                        PnL vs entry {latestPnl === null ? '-' : `$${latestPnl.toLocaleString(undefined, { maximumFractionDigits: 2 })}`} · {row.latest_paper_return_pct === '' || row.latest_paper_return_pct === undefined ? '-' : `${Number(row.latest_paper_return_pct).toFixed(2)}%`}
                      </div>
                      <div style={{ fontSize: '10px', color: tradeColor, fontFamily: TG_THEME.mono, lineHeight: 1.35 }}>
                        ticket PnL {tradePnl === null ? '-' : `$${tradePnl.toLocaleString(undefined, { maximumFractionDigits: 2 })}`} · {row.paper_trade_action || 'WAIT'} · hit {row.paper_trade_hit_rate === '' || row.paper_trade_hit_rate === undefined ? '-' : `${Number(row.paper_trade_hit_rate).toFixed(0)}%`}
                      </div>
                      <div style={{ fontSize: '10px', color: oosColor, fontFamily: TG_THEME.mono, lineHeight: 1.35 }}>
                        {oosText}
                      </div>
                      {(row.signal_reason || row.current_action_reason) && (
                        <div style={{ fontSize: '10px', color: TG_THEME.secondary, lineHeight: 1.35, marginTop: '3px' }}>
                          {row.signal_reason || row.current_action_reason}
                        </div>
                      )}
                      {recentMarks.length > 0 && (
                        <div style={{ display: 'flex', gap: '5px', flexWrap: 'wrap', marginTop: '4px' }}>
                          {recentMarks.slice(-3).map(mark => (
                            <span key={`${row.archetype_id}-${mark.date}`} style={{ fontSize: '9px', color: TG_THEME.tertiary, fontFamily: TG_THEME.mono }}>
                              {String(mark.date || '').slice(5)} {mark.mark_type === 'entry' ? 'baseline' : `${Number(mark.paper_pnl_usdc || 0) >= 0 ? '+' : ''}$${Number(mark.paper_pnl_usdc || 0).toFixed(0)}`}
                            </span>
                          ))}
                        </div>
                      )}
                      {(openTrade || closedTrades.length > 0) && (
                        <div style={{ display: 'flex', gap: '5px', flexWrap: 'wrap', marginTop: '4px' }}>
                          {openTrade && (
                            <span style={{ fontSize: '9px', color: tradeColor, fontFamily: TG_THEME.mono }}>
                              open {String(openTrade.entry_date || '').slice(5)}→{String(openTrade.mark_date || '').slice(5)} {Number(openTrade.pnl_usdc || 0) >= 0 ? '+' : ''}${Number(openTrade.pnl_usdc || 0).toFixed(0)}
                            </span>
                          )}
                          {closedTrades.slice(-2).map((trade, idx) => (
                            <span key={`${row.archetype_id}-trade-${trade.entry_date}-${trade.exit_date}-${idx}`} style={{ fontSize: '9px', color: Number(trade.pnl_usdc || 0) < 0 ? TG_THEME.red : TG_THEME.green, fontFamily: TG_THEME.mono }}>
                              {String(trade.entry_date || '').slice(5)}→{String(trade.exit_date || '').slice(5)} {Number(trade.pnl_usdc || 0) >= 0 ? '+' : ''}${Number(trade.pnl_usdc || 0).toFixed(0)}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                    <div style={{ fontSize: '10px', color, fontWeight: 800, textAlign: 'right' }}>
                      {String(status).replaceAll('_', ' ')}
                    </div>
                  </div>
                </div>
              );
            }) : (
              <div style={{ background: TG_THEME.elevated, borderRadius: '8px', padding: '9px', fontSize: '11px', color: TG_THEME.secondary, lineHeight: 1.35 }}>
                Waiting for spread replay and paper-ticket rows from the backend. The panel stays visible so users know where profitability will appear.
              </div>
            )}
          </div>
        </div>
      )}

      {tgSpreadTradeMap(data).length > 0 && (
        <div style={{ background: TG_THEME.surface, borderRadius: '12px', padding: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'center', marginBottom: '8px' }}>
            <div style={{ fontSize: '11px', color: TG_THEME.green, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
              Spread trade map
            </div>
            <TgBadge color={TG_THEME.blue}>INDEX TO BASKET</TgBadge>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {tgSpreadTradeMap(data).slice(0, 4).map(row => {
              const selected = row.selected_expression || {};
              const signal = selected.latest_signal || 'MONITOR';
              const action = row.tradability_action || 'MONITOR';
              const color = String(action).includes('AVOID') || signal === 'SELL'
                ? TG_THEME.red
                : (String(action).includes('BUY') || signal === 'BUY' ? TG_THEME.green : TG_THEME.orange);
              return (
                <div key={row.archetype_id} style={{ background: TG_THEME.elevated, borderRadius: '8px', padding: '8px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'flex-start' }}>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: '12px', color: TG_THEME.text, fontWeight: 700, overflowWrap: 'anywhere' }}>{row.label}</div>
                      <div style={{ fontSize: '10px', color: TG_THEME.tertiary, lineHeight: 1.35 }}>
                        {row.oil_analogy} · {String(row.replay_status || 'NO_REPLAY').replaceAll('_', ' ')}
                      </div>
                      <div style={{ fontSize: '10px', color: TG_THEME.tertiary, lineHeight: 1.35 }}>
                        {(selected.title || selected.basket_label || 'No expression')} · 5d {Number(selected.return_5d_pct || 0).toFixed(1)}% · 1m {Number(selected.return_1m_pct || 0).toFixed(1)}%
                      </div>
                    </div>
                    <div style={{ fontSize: '10px', color, fontWeight: 800, textAlign: 'right' }}>
                      {String(action).replaceAll('_', ' ')}
                    </div>
                  </div>
                  <div style={{ fontSize: '10px', color: TG_THEME.secondary, lineHeight: 1.35, marginTop: '4px' }}>
                    {row.tradability_reason}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {(tgDirectEventPairs(data).rows || []).length > 0 && (
        <div style={{ background: TG_THEME.surface, borderRadius: '12px', padding: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'center', marginBottom: '8px' }}>
            <div style={{ fontSize: '11px', color: TG_THEME.green, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
              Direct event pairs
            </div>
            <TgBadge color={TG_THEME.blue}>
              {tgDirectEventPairs(data).ready_for_judge_count || 0}/{tgDirectEventPairs(data).pair_count || 0}
            </TgBadge>
          </div>
          <div style={{ fontSize: '10px', color: TG_THEME.tertiary, lineHeight: 1.35, marginBottom: '8px' }}>
            {tgDirectEventPairs(data).target_pair || 'Energy/grid-stress leg paired against AI compute-demand leg.'}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {(tgDirectEventPairs(data).rows || []).slice(0, 3).map(row => {
              const energy = row.energy_leg || {};
              const compute = row.compute_leg || {};
              const oracle = row.oracle_evidence || {};
              const color = String(row.readiness || '').includes('PRICE')
                ? TG_THEME.orange
                : TG_THEME.blue;
              const oracleColor = String(oracle.gate || '').includes('CRITIQUE') || String(oracle.latest_verdict || '').includes('VETO')
                ? TG_THEME.red
                : (String(oracle.gate || '').includes('SUPPORT') ? TG_THEME.green : TG_THEME.orange);
              return (
                <div key={row.pair_id} style={{ background: TG_THEME.elevated, borderRadius: '8px', padding: '8px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'flex-start', marginBottom: '5px' }}>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: '12px', color: TG_THEME.text, fontWeight: 700, overflowWrap: 'anywhere' }}>
                        {(energy.title || energy.slug || 'energy leg')} → {(compute.title || compute.slug || 'compute leg')}
                      </div>
                      <div style={{ fontSize: '9px', color: TG_THEME.tertiary, fontFamily: TG_THEME.mono, lineHeight: 1.35 }}>
                        {row.pair_id} · {(row.surfaces || []).join(' + ')}
                      </div>
                    </div>
                    <div style={{ fontSize: '10px', color, fontWeight: 800, textAlign: 'right' }}>
                      {String(row.readiness || 'WATCH').replaceAll('_', ' ')}
                    </div>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px', marginBottom: '5px' }}>
                    {[
                      ['energy', energy, TG_THEME.orange],
                      ['compute', compute, TG_THEME.blue],
                    ].map(([label, leg, itemColor]) => (
                      <div key={label} style={{ background: TG_THEME.surface, borderRadius: '6px', padding: '6px', minWidth: 0 }}>
                        <div style={{ fontSize: '9px', color: itemColor, textTransform: 'uppercase', fontWeight: 800 }}>{String(leg.pair_side || 'watch')} {label}</div>
                        <div style={{ fontSize: '10px', color: TG_THEME.secondary, lineHeight: 1.25, overflowWrap: 'anywhere' }}>
                          {leg.surface || 'surface'} · {leg.slug || 'slug'}
                        </div>
                      </div>
                    ))}
                  </div>
                  <div style={{ fontSize: '10px', color: TG_THEME.secondary, lineHeight: 1.35 }}>
                    {row.action}
                  </div>
                  <div style={{ fontSize: '10px', color: oracleColor, lineHeight: 1.35, marginTop: '4px', fontFamily: TG_THEME.mono }}>
                    oracle {String(oracle.gate || 'NO_ORACLE_RECEIPTS').replaceAll('_', ' ')} · {Number(oracle.receipts || 0)} receipts{oracle.latest_verdict ? ` · ${oracle.latest_verdict}` : ''}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

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
          {data.syntheticInstrument.outputs?.oracle_judge_evidence && (
            <div style={{ fontSize: '11px', color: TG_THEME.secondary, lineHeight: 1.35, marginBottom: '6px', background: TG_THEME.elevated, borderRadius: '8px', padding: '8px' }}>
              LLM/news evidence: {String(data.syntheticInstrument.outputs.oracle_judge_evidence.status || 'NO_RECEIPTS').replaceAll('_', ' ')}
              {' '}· {data.syntheticInstrument.outputs.oracle_judge_evidence.row_count || 0} receipts
              {' '}· {data.syntheticInstrument.outputs.oracle_judge_evidence.latest_verdict || 'no verdict'}
            </div>
          )}
          {data.syntheticInstrument.outputs?.operator_signal_sheet && (
            <div style={{ background: TG_THEME.elevated, borderRadius: '8px', padding: '9px', marginBottom: '6px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'flex-start' }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: '10px', color: TG_THEME.secondary, textTransform: 'uppercase', fontWeight: 700 }}>Operator signal</div>
                  <div style={{ fontSize: '12px', color: TG_THEME.text, fontWeight: 700, lineHeight: 1.25, marginTop: '3px' }}>
                    {data.syntheticInstrument.outputs.operator_signal_sheet.headline}
                  </div>
                </div>
                <TgBadge color={String(data.syntheticInstrument.outputs.operator_signal_sheet.overall_action || '').includes('AVOID') ? TG_THEME.red : TG_THEME.orange}>
                  {String(data.syntheticInstrument.outputs.operator_signal_sheet.overall_action || 'MONITOR').replaceAll('_', ' ')}
                </TgBadge>
              </div>
              <div style={{ fontSize: '10px', color: TG_THEME.secondary, lineHeight: 1.35, marginTop: '5px' }}>
                {data.syntheticInstrument.outputs.operator_signal_sheet.reason}
              </div>
              {(data.syntheticInstrument.outputs.operator_signal_sheet.rows || []).slice(0, 3).map(row => (
                <div key={row.key} style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 68px', gap: '6px', alignItems: 'center', paddingTop: '6px', marginTop: '6px', borderTop: `1px solid ${TG_THEME.border}` }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: '11px', color: TG_THEME.text, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.label}</div>
                    <div style={{ fontSize: '9px', color: TG_THEME.tertiary, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.reason}</div>
                  </div>
                  <div style={{ fontSize: '10px', color: String(row.action || '').includes('AVOID') || row.signal === 'SELL' ? TG_THEME.red : TG_THEME.orange, fontWeight: 800, textAlign: 'right' }}>
                    {String(row.action || 'MONITOR').replaceAll('_', ' ')}
                  </div>
                </div>
              ))}
            </div>
          )}
          {(data.syntheticInstrument.outputs?.collateral_profile_candidates || []).length > 0 && (
            <div style={{ background: TG_THEME.elevated, borderRadius: '8px', padding: '9px', marginBottom: '6px' }}>
              <div style={{ fontSize: '10px', color: TG_THEME.secondary, textTransform: 'uppercase', fontWeight: 700, marginBottom: '6px' }}>Collateral materiality</div>
              {(data.syntheticInstrument.outputs.collateral_profile_candidates || []).slice(0, 3).map(profile => (
                <div key={profile.profile_id} style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 54px 58px', gap: '6px', alignItems: 'center', padding: '5px 0', borderTop: `1px solid ${TG_THEME.border}` }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: '11px', color: TG_THEME.text, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{profile.label}</div>
                    <div style={{ fontSize: '9px', color: TG_THEME.tertiary, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{profile.action}</div>
                  </div>
                  <div style={{ fontSize: '11px', color: profile.materiality_gate === 'PASS' ? TG_THEME.green : TG_THEME.orange, fontWeight: 800, textAlign: 'right' }}>
                    {Number(profile.modeled_power_cost_share_pct || 0).toFixed(1)}%
                  </div>
                  <div style={{ fontSize: '10px', color: profile.materiality_gate === 'PASS' ? TG_THEME.green : TG_THEME.orange, fontWeight: 800, textAlign: 'right' }}>
                    {profile.materiality_gate || 'MON'}
                  </div>
                </div>
              ))}
            </div>
          )}
          {data.syntheticInstrument.outputs?.mock_hedge_construction && (
            <div style={{ background: TG_THEME.elevated, borderRadius: '8px', padding: '9px', marginBottom: '6px' }}>
              <div style={{ fontSize: '10px', color: TG_THEME.secondary, textTransform: 'uppercase', fontWeight: 700 }}>Mock contract entry check</div>
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
              <div style={{ fontSize: '11px', color: tgRecommendationColor(data.syntheticInstrument.outputs.mock_hedge_construction), lineHeight: 1.35, marginTop: '4px' }}>
                {data.syntheticInstrument.outputs.mock_hedge_construction.recommendation_summary || tgRecommendationFallback(data.syntheticInstrument.outputs.mock_hedge_construction)}
              </div>
              {data.syntheticInstrument.outputs.mock_hedge_construction.decision_basis_hash && (
                <div style={{ fontSize: '10px', color: TG_THEME.tertiary, fontFamily: TG_THEME.mono, lineHeight: 1.35, marginTop: '4px' }}>
                  refresh {data.syntheticInstrument.outputs.mock_hedge_construction.decision_basis_hash}
                </div>
              )}
              <div style={{ fontSize: '10px', color: TG_THEME.tertiary, lineHeight: 1.35, marginTop: '4px' }}>
                Entry score {Math.round(Number(data.syntheticInstrument.outputs.mock_hedge_construction.entry_signal_score || data.syntheticInstrument.outputs.mock_hedge_construction.profitability_score || 0))}/100; buy threshold {Math.round(Number(data.syntheticInstrument.outputs.mock_hedge_construction.entry_threshold_score || 70))}/100; Arc stays gated by judge.classify().
              </div>
              {data.syntheticInstrument.outputs.mock_hedge_construction.judge_verdict?.label && (
                <div style={{ fontSize: '10px', color: TG_THEME.tertiary, fontFamily: TG_THEME.mono, lineHeight: 1.35, marginTop: '4px' }}>
                  judge {data.syntheticInstrument.outputs.mock_hedge_construction.judge_verdict.label}/{data.syntheticInstrument.outputs.mock_hedge_construction.judge_verdict.reason_code || 'checked'}
                </div>
              )}
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
  const venueRows = tgVenueEvidence(data);
  const venueCopy = tgVenueCopyMatrix(data);
  const venueCopyRows = venueCopy.rows || [];
  const indexCoverage = tgIndexCoverage(data) || {};
  const indexCatalog = tgIndexCatalog(data) || {};
  const electricityIndexes = indexCatalog.electricity || [];
  const computeIndexes = indexCatalog.compute || [];
  const oracle = tgOracleEvidence(data);
  const verdictCounts = oracle.verdict_counts || {};
  const verdictText = Object.entries(verdictCounts).map(([k, v]) => `${k}:${v}`).join(' · ') || 'none';
  const familyLine = (counts) => Object.entries(counts || {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, 4)
    .map(([k, v]) => `${String(k).replaceAll('_', ' ')} ${v}`)
    .join(' · ');
  const tradeabilityLine = (counts) => Object.entries(counts || {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, 4)
    .map(([k, v]) => `${String(k).replaceAll('_', ' ')} ${v}`)
    .join(' · ');
  return (
  <TgScreen title="Agent Scouting" subtitle="Research only" onBack={goBack}>
    <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
      <div style={{ background: TG_THEME.surface, borderRadius: '10px', padding: '14px', fontSize: '13px', color: TG_THEME.secondary, lineHeight: 1.45 }}>
        These rows are not the contract. The agent uses Opoint/Nebius, IBKR ForecastTrader, and Polymarket to find legs that are actually driven by the compute/energy spread. Public channel posts stay quiet until the mock contract changes or an operator action is needed.
      </div>
      <div style={{ background: TG_THEME.surface, borderRadius: '12px', padding: '14px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'center', marginBottom: '8px' }}>
          <div style={{ fontSize: '11px', color: TG_THEME.green, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
            Index universe
          </div>
          <TgBadge color={TG_THEME.green}>
            {(indexCoverage.spread_archetypes?.replayed || 0)}/{(indexCoverage.spread_archetypes?.total || 0)} replayed
          </TgBadge>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginBottom: '8px' }}>
          {[
            ['Power', `${indexCoverage.electricity?.usable || 0}/${indexCoverage.electricity?.total || electricityIndexes.length}`, familyLine(indexCoverage.electricity?.family_counts), tradeabilityLine(indexCoverage.electricity?.tradeability_counts)],
            ['Compute', `${indexCoverage.compute?.usable || 0}/${indexCoverage.compute?.total || computeIndexes.length}`, familyLine(indexCoverage.compute?.family_counts), tradeabilityLine(indexCoverage.compute?.tradeability_counts)],
          ].map(([label, value, detail, tradeability]) => (
            <div key={label} style={{ background: TG_THEME.elevated, borderRadius: '8px', padding: '9px', minWidth: 0 }}>
              <div style={{ fontSize: '10px', color: TG_THEME.tertiary }}>{label} indexes</div>
              <div style={{ fontSize: '15px', color: TG_THEME.text, fontWeight: 800, fontFamily: 'SF Mono, monospace' }}>{value}</div>
              <div style={{ fontSize: '10px', color: TG_THEME.secondary, lineHeight: 1.3, marginTop: '3px', overflowWrap: 'anywhere' }}>{detail || 'families pending'}</div>
              <div style={{ fontSize: '10px', color: TG_THEME.tertiary, lineHeight: 1.3, marginTop: '4px', overflowWrap: 'anywhere' }}>{tradeability || 'tradeability pending'}</div>
            </div>
          ))}
        </div>
        <div style={{ fontSize: '10px', color: TG_THEME.secondary, lineHeight: 1.35 }}>
          Registered rows include physical power marks, fuel-stack proxies, GPU rental marks, direct-event watchlists, public equities, and miner-margin proxies. Planned rows are shown as research gaps, not tradable marks.
        </div>
      </div>
      <div style={{ background: TG_THEME.surface, borderRadius: '12px', padding: '14px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'center', marginBottom: '8px' }}>
          <div style={{ fontSize: '11px', color: TG_THEME.green, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
            LLM / News judge evidence
          </div>
          <TgBadge color={oracle.status === 'EVIDENCE_LOGGED' ? TG_THEME.green : TG_THEME.orange}>
            {String(oracle.status || 'NO RECEIPTS').replaceAll('_', ' ')}
          </TgBadge>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
          {[
            ['Receipts', oracle.row_count || 0],
            ['Desk receipts', oracle.current_desk_row_count || 0],
            ['Scope', String(oracle.latest_scope || 'none').replaceAll('_', ' ')],
            ['Query', String(oracle.latest_query_label || 'none').replaceAll('_', ' ')],
            ['Verdicts', verdictText],
            ['Articles', `${oracle.filtered_articles || 0}/${oracle.raw_articles || 0}`],
            ['Reason', oracle.latest_reason_code || 'none'],
          ].map(([label, value]) => (
            <div key={label} style={{ background: TG_THEME.elevated, borderRadius: '8px', padding: '8px', minWidth: 0 }}>
              <div style={{ fontSize: '10px', color: TG_THEME.tertiary }}>{label}</div>
              <div style={{ fontSize: '12px', color: TG_THEME.text, fontWeight: 700, overflowWrap: 'anywhere' }}>{value}</div>
            </div>
          ))}
        </div>
        <div style={{ fontSize: '10px', color: TG_THEME.secondary, lineHeight: 1.35, marginTop: '8px' }}>
          Evidence only: Opoint/Nebius can support or criticize a leg, but Arc stays locked until scorer and judge gates clear. Compute/power receipts are preferred over generic energy receipts on this desk.
        </div>
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
          Real venue copy matrix
        </div>
        {venueCopyRows.length ? venueCopyRows.slice(0, 6).map((row, i) => (
          <div key={row.surface || i} style={{ padding: '10px 16px', borderTop: i ? `0.5px solid ${TG_THEME.separator}` : 'none' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'flex-start' }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: '13px', color: TG_THEME.text, fontWeight: 700, overflowWrap: 'anywhere' }}>{row.label || row.surface}</div>
                <div style={{ fontSize: '10px', color: TG_THEME.tertiary, lineHeight: 1.35 }}>
                  {String(row.copy_role || '').replaceAll('_', ' ')} · priced {row.priced_count || 0} · proxy {row.external_proxy_count || 0}
                </div>
              </div>
              <TgBadge color={String(row.copy_status || '').includes('PROXY') || String(row.copy_status || '').includes('JUDGE') ? TG_THEME.green : TG_THEME.orange}>
                {String(row.copy_status || 'watch').replaceAll('_', ' ')}
              </TgBadge>
            </div>
            {(row.spread_links || []).length > 0 && (
              <div style={{ fontSize: '10px', color: TG_THEME.secondary, lineHeight: 1.35, marginTop: '4px' }}>
                copies {(row.spread_links || []).slice(0, 2).map(link => link.label || link.archetype_id).join(', ')}
              </div>
            )}
            <div style={{ fontSize: '10px', color: TG_THEME.secondary, lineHeight: 1.35, marginTop: '4px' }}>
              {row.action}
            </div>
          </div>
        )) : (
          <div style={{ padding: '12px 16px', fontSize: '12px', color: TG_THEME.secondary }}>
            Venue copy matrix is empty in this snapshot.
          </div>
        )}
      </div>
      <div style={{ background: TG_THEME.surface, borderRadius: '12px', overflow: 'hidden' }}>
        <div style={{ padding: '12px 16px', fontSize: '11px', color: TG_THEME.secondary, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
          Venue evidence matrix
        </div>
        {venueRows.length ? venueRows.slice(0, 6).map((row, i) => (
          <div key={row.surface || i} style={{ padding: '10px 16px', borderTop: i ? `0.5px solid ${TG_THEME.separator}` : 'none' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'flex-start' }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: '13px', color: TG_THEME.text, fontWeight: 700, overflowWrap: 'anywhere' }}>{row.label || row.surface}</div>
                <div style={{ fontSize: '10px', color: TG_THEME.tertiary, lineHeight: 1.35 }}>
                  {row.role || 'evidence'} · priced {row.priced_count || 0} · proxy {row.external_proxy_count || 0}
                </div>
                {row.auth_status && (
                  <div style={{ fontSize: '10px', color: row.auth_status === 'AUTHENTICATED' ? TG_THEME.green : TG_THEME.orange, lineHeight: 1.35, marginTop: '2px' }}>
                    auth {String(row.auth_status).replaceAll('_', ' ').toLowerCase()}
                  </div>
                )}
                {(row.quote_sources || []).length > 0 && (
                  <div style={{ fontSize: '10px', color: TG_THEME.secondary, lineHeight: 1.35, marginTop: '2px', overflowWrap: 'anywhere' }}>
                    source {(row.quote_sources || []).map(src => tgQuoteSourceLabel({ externalProxySource: src })).join(', ')}
                  </div>
                )}
              </div>
              <TgBadge color={row.status === 'LIVE_PRICED' || row.status === 'EVIDENCE_LOGGED' ? TG_THEME.green : TG_THEME.orange}>
                {String(row.status || 'watch').replaceAll('_', ' ')}
              </TgBadge>
            </div>
            <div style={{ fontSize: '10px', color: TG_THEME.secondary, lineHeight: 1.35, marginTop: '4px' }}>
              {(row.gaps || [data.venueEvidence?.guardrail || 'Judge required before Arc.'])[0]}
            </div>
          </div>
        )) : (
          <div style={{ padding: '12px 16px', fontSize: '12px', color: TG_THEME.secondary }}>
            Venue evidence matrix is empty in this snapshot.
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

const TgUpdates = ({ setScreen, goBack, data, accountData }) => {
  const account = accountData?.account || null;
  const menuCount = tgInstrumentMenu(data).length;
  const ledgerRows = tgProfitabilityLedger(data)?.rows || [];
  const venueRows = tgVenueCopyMatrix(data)?.rows || [];
  const releaseState = tgMiniappRelease(data);
  const releasePosted = Number(releaseState.posted_count || 0);
  const releaseTotal = Number(releaseState.total_posts || TG_RELEASE_STORY.length);
  const updates = [
    {
      title: 'Account-backed Mini App',
      desc: account
        ? 'Operator account is active. Paper tickets and PnL refresh from the backend ledger.'
        : 'Create Operator once; then tickets and PnL are restored by signed backend session.',
      status: account ? 'ACTIVE' : 'SETUP',
      color: account ? TG_THEME.green : TG_THEME.orange,
      screen: account ? 'portfolio' : 'billing',
    },
    {
      title: 'Mock contract actions',
      desc: 'Mock Contract now owns the user path: read signal, open paper ticket, monitor marks, close from Portfolio.',
      status: 'LIVE',
      color: TG_THEME.green,
      screen: 'dashboard',
    },
    {
      title: 'Syndicated spread menu',
      desc: `${menuCount || 'No'} structures are wired to oil-style spread replay, public proxy marks, and judge-gated Arc language.`,
      status: menuCount ? `${menuCount}` : 'WAIT',
      color: menuCount ? TG_THEME.green : TG_THEME.orange,
      screen: 'dashboard',
    },
    {
      title: 'Profitability discipline',
      desc: `${ledgerRows.length || 'No'} ledger rows separate paper-ticket PnL from settled venue PnL, so users know what is mock-traded.`,
      status: ledgerRows.length ? `${ledgerRows.length}` : 'WAIT',
      color: ledgerRows.length ? TG_THEME.green : TG_THEME.orange,
      screen: 'dashboard',
    },
    {
      title: 'Scouting stays separate',
      desc: `${venueRows.length || 'No'} venue-copy rows explain IBKR, Polymarket, Kalshi, Opoint/Nebius, and public quote roles without channel reject spam.`,
      status: venueRows.length ? `${venueRows.length}` : 'RESEARCH',
      color: TG_THEME.blue,
      screen: 'scouting',
    },
  ];
  return (
    <TgScreen title="What's New" subtitle="Release notes" onBack={goBack}>
      <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
        <div style={{ background: TG_THEME.surface, borderRadius: '12px', padding: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '10px', alignItems: 'flex-start', marginBottom: '8px' }}>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: '11px', color: TG_THEME.green, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase' }}>Telegram product layer</div>
              <div style={{ fontSize: '18px', color: TG_THEME.text, fontWeight: 850, lineHeight: 1.2, marginTop: '5px' }}>
                Mini App is now the user trading surface
              </div>
            </div>
            <TgBadge color={TG_THEME.green}>SCREENSHOT READY</TgBadge>
          </div>
          <div style={{ fontSize: '12px', color: TG_THEME.secondary, lineHeight: 1.45 }}>
            Channel posts now pair short release notes with actual Mini App screenshots. Each post explains one new product section, what the user can do there, and what stays paper-only or judge-gated.
          </div>
        </div>

        <div style={{ background: TG_THEME.surface, borderRadius: '12px', padding: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '10px', alignItems: 'center', marginBottom: '10px' }}>
            <div>
              <div style={{ fontSize: '11px', color: TG_THEME.green, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase' }}>Channel screenshot deck</div>
              <div style={{ fontSize: '11px', color: TG_THEME.secondary, lineHeight: 1.35, marginTop: '2px' }}>
                Public posts are sparse: product changes, screenshots, and operator-relevant context only.
              </div>
            </div>
            <TgBadge color={releasePosted === releaseTotal && releaseTotal > 0 ? TG_THEME.green : TG_THEME.orange}>
              {releasePosted}/{releaseTotal}
            </TgBadge>
          </div>
          <div style={{ background: TG_THEME.elevated, borderRadius: '8px', padding: '8px', marginBottom: '9px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'center' }}>
              <div style={{ fontSize: '11px', color: TG_THEME.text, fontWeight: 800 }}>
                {String(releaseState.status || 'READY_TO_POST').replaceAll('_', ' ')}
              </div>
              <div style={{ fontSize: '9px', color: TG_THEME.tertiary, fontFamily: TG_THEME.mono }}>
                {releaseState.post_command || 'npm run telegram:miniapp-release-post'}
              </div>
            </div>
            <div style={{ fontSize: '10px', color: TG_THEME.secondary, lineHeight: 1.35, marginTop: '3px' }}>
              Status is read from sent post keys only. Bot tokens and message bodies are never exposed to the Mini App.
            </div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '7px' }}>
            {TG_RELEASE_STORY.map(item => (
              <button key={item.file} type="button" onClick={() => setScreen(item.screen)} style={{
                width: '100%',
                display: 'grid',
                gridTemplateColumns: '34px minmax(0, 1fr)',
                gap: '9px',
                alignItems: 'center',
                textAlign: 'left',
                background: TG_THEME.elevated,
                border: `1px solid ${TG_THEME.border}`,
                borderRadius: '9px',
                padding: '9px',
                cursor: 'pointer',
              }}>
                <div style={{
                  width: 34, height: 34, borderRadius: '8px',
                  background: item.color + '20',
                  color: item.color,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '16px',
                  fontWeight: 900,
                }}>
                  ◼
                </div>
                <div style={{ minWidth: 0 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '7px', alignItems: 'baseline' }}>
                    <div style={{ fontSize: '12px', color: TG_THEME.text, fontWeight: 800, overflowWrap: 'anywhere' }}>{item.label}</div>
                    <div style={{ fontSize: '9px', color: TG_THEME.tertiary, fontFamily: TG_THEME.mono, whiteSpace: 'nowrap' }}>{item.file}</div>
                  </div>
                  <div style={{ fontSize: '10px', color: TG_THEME.secondary, lineHeight: 1.35, marginTop: '2px', overflowWrap: 'anywhere' }}>{item.desc}</div>
                </div>
              </button>
            ))}
          </div>
          <a
            href={TG_CHANNEL_URL}
            target="_blank"
            rel="noreferrer"
            style={{
              display: 'flex',
              justifyContent: 'center',
              alignItems: 'center',
              minHeight: '38px',
              marginTop: '10px',
              borderRadius: '9px',
              background: TG_THEME.green,
              color: '#000',
              fontSize: '13px',
              fontWeight: 800,
              textDecoration: 'none',
            }}
          >
            Open Channel
          </a>
        </div>

        <div style={{ background: TG_THEME.surface, borderRadius: '12px', overflow: 'hidden' }}>
          {updates.map((item, i) => (
            <button key={item.title} type="button" onClick={() => setScreen(item.screen)} style={{
              width: '100%',
              background: 'none',
              border: 'none',
              borderTop: i ? `0.5px solid ${TG_THEME.separator}` : 'none',
              padding: '12px 16px',
              textAlign: 'left',
              cursor: 'pointer',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'flex-start' }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: '13px', color: TG_THEME.text, fontWeight: 800, overflowWrap: 'anywhere' }}>{item.title}</div>
                  <div style={{ fontSize: '11px', color: TG_THEME.secondary, lineHeight: 1.4, marginTop: '3px', overflowWrap: 'anywhere' }}>{item.desc}</div>
                </div>
                <TgBadge color={item.color}>{item.status}</TgBadge>
              </div>
            </button>
          ))}
        </div>

        <div style={{ background: TG_THEME.surface, borderRadius: '12px', padding: '16px' }}>
          <div style={{ fontSize: '11px', color: TG_THEME.green, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase', marginBottom: '10px' }}>Screenshot map</div>
          {[
            { label: 'Release notes', file: 'miniapp-updates.png', desc: 'This screen, used for the compact Mini App update post.' },
            ...TG_RELEASE_STORY,
            { label: 'Index/spread menu', file: 'indexes-spreads.png', desc: 'Electricity and compute indexes plus oil-style spread forms.' },
          ].map(({ label, file, desc }) => (
            <div key={file} style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 118px', gap: '8px', alignItems: 'center', padding: '7px 0', borderTop: `1px solid ${TG_THEME.border}` }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: '12px', color: TG_THEME.text, fontWeight: 750 }}>{label}</div>
                <div style={{ fontSize: '10px', color: TG_THEME.secondary, lineHeight: 1.35, marginTop: '2px' }}>{desc}</div>
              </div>
              <div style={{ fontSize: '9px', color: TG_THEME.tertiary, fontFamily: TG_THEME.mono, textAlign: 'right', overflowWrap: 'anywhere' }}>{file}</div>
            </div>
          ))}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
          <button onClick={() => setScreen('dashboard')} style={{ padding: '13px', borderRadius: '10px', border: 'none', background: TG_THEME.green, color: '#000', fontSize: '13px', fontWeight: 800 }}>Mock Contract</button>
          <button onClick={() => setScreen('scouting')} style={{ padding: '13px', borderRadius: '10px', border: `1px solid ${TG_THEME.separator}`, background: TG_THEME.elevated, color: TG_THEME.text, fontSize: '13px', fontWeight: 800 }}>Scouting</button>
        </div>
      </div>
    </TgScreen>
  );
};

const TgAlerts = ({ setScreen, goBack, data }) => {
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

const TgPortfolio = ({ setScreen, goBack, accountData }) => {
  const account = accountData?.account || null;
  const portfolio = accountData?.portfolio || null;
  const summary = portfolio?.summary || {};
  const positions = portfolio?.positions || [];
  const realized = portfolio?.realized || [];
  const instruments = portfolio?.instruments || [];
  const best = tgBestBuyableInstrument(portfolio);
  const [closing, setClosing] = React.useState('');
  const [error, setError] = React.useState('');

  const closePosition = async (positionId) => {
    setClosing(positionId);
    setError('');
    try {
      await window.closePaperPosition?.({ positionId });
      await accountData?.refresh?.();
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setClosing('');
    }
  };

  const openWebAccount = () => {
    const url = `${window.location.origin}/account`;
    if (window.Telegram?.WebApp?.openLink) window.Telegram.WebApp.openLink(url);
    else window.location.href = '/account';
  };

  if (!account) {
    return (
      <TgScreen title="My Portfolio" subtitle="Account required" onBack={goBack}>
        <div style={{ padding: '16px' }}>
          <div style={{ background: TG_THEME.surface, borderRadius: '12px', padding: '16px', marginBottom: '12px' }}>
            <TgBadge color={TG_THEME.orange}>NO ACCOUNT</TgBadge>
            <div style={{ fontSize: '18px', color: TG_THEME.text, fontWeight: 800, marginTop: '12px', lineHeight: 1.25 }}>
              Create Operator before saving paper tickets
            </div>
            <div style={{ fontSize: '12px', color: TG_THEME.secondary, lineHeight: 1.45, marginTop: '8px' }}>
              The Mini App no longer uses browser-only mock state. Positions and PnL are stored server-side under a signed session cookie and payer wallet.
            </div>
          </div>
          <button onClick={() => setScreen('billing')} style={{
            width: '100%', padding: '14px', borderRadius: '10px', border: 'none',
            background: TG_THEME.green, color: '#000', fontSize: '15px', fontWeight: 800,
          }}>Create Operator Account</button>
        </div>
      </TgScreen>
    );
  }

  return (
    <TgScreen title="My Portfolio" subtitle="Server-side paper ledger" onBack={goBack}>
      <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
        <div style={{ background: TG_THEME.surface, borderRadius: '12px', padding: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'flex-start', marginBottom: '10px' }}>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: '11px', color: TG_THEME.green, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase' }}>Operator account</div>
              <div style={{ fontSize: '12px', color: TG_THEME.secondary, fontFamily: TG_THEME.mono, overflowWrap: 'anywhere', marginTop: '3px' }}>{account.id}</div>
            </div>
            <TgBadge color={TG_THEME.green}>ACTIVE</TgBadge>
          </div>
          <div style={{ fontSize: '10px', color: TG_THEME.tertiary, fontFamily: TG_THEME.mono, overflowWrap: 'anywhere' }}>
            wallet {account.walletAddress || 'not set'}
          </div>
        </div>

        <div style={{ background: TG_THEME.surface, borderRadius: '12px', padding: '16px' }}>
          <div style={{ fontSize: '11px', color: TG_THEME.green, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase', marginBottom: '10px' }}>PnL</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
            {[
              ['Open notional', `$${Number(summary.openNotionalUsdc || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`, TG_THEME.text],
              ['Unrealized', tgMoney(summary.unrealizedPnlUsdc || 0), Number(summary.unrealizedPnlUsdc || 0) < 0 ? TG_THEME.red : TG_THEME.green],
              ['Realized', tgMoney(summary.realizedPnlUsdc || 0), Number(summary.realizedPnlUsdc || 0) < 0 ? TG_THEME.red : TG_THEME.green],
              ['Net', tgMoney(summary.netPnlUsdc || 0), Number(summary.netPnlUsdc || 0) < 0 ? TG_THEME.red : TG_THEME.green],
            ].map(([label, value, color]) => (
              <div key={label} style={{ background: TG_THEME.elevated, borderRadius: '8px', padding: '9px' }}>
                <div style={{ fontSize: '10px', color: TG_THEME.tertiary }}>{label}</div>
                <div style={{ fontSize: '14px', color, fontFamily: TG_THEME.mono, fontWeight: 800, marginTop: '2px' }}>{value}</div>
              </div>
            ))}
          </div>
          <div style={{ fontSize: '10px', color: TG_THEME.secondary, lineHeight: 1.35, marginTop: '9px' }}>
            Paper PnL is current backend NAV minus entry NAV. It is not settled venue PnL or Arc escrow PnL.
          </div>
        </div>

        <div style={{ background: TG_THEME.surface, borderRadius: '12px', overflow: 'hidden' }}>
          <div style={{ padding: '12px 16px', fontSize: '11px', color: TG_THEME.secondary, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
            Open positions
          </div>
          {positions.length ? positions.map(pos => (
            <div key={pos.positionId} style={{ padding: '12px 16px', borderTop: `0.5px solid ${TG_THEME.separator}` }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'flex-start' }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: '13px', color: TG_THEME.text, fontWeight: 700, overflowWrap: 'anywhere' }}>{pos.noteName}</div>
                  <div style={{ fontSize: '10px', color: TG_THEME.tertiary, fontFamily: TG_THEME.mono, marginTop: '2px' }}>
                    {pos.positionId} · entry {Number(pos.entryMark || 0).toFixed(4)} / mark {Number(pos.currentMark || 0).toFixed(4)}
                  </div>
                  <div style={{ fontSize: '10px', color: TG_THEME.secondary, marginTop: '3px' }}>
                    {Number(pos.notionalUsdc || 0).toLocaleString()} test USDC · {Number(pos.returnPct || 0).toFixed(2)}%
                  </div>
                </div>
                <div style={{ textAlign: 'right', flexShrink: 0 }}>
                  <div style={{ fontSize: '13px', color: Number(pos.unrealizedPnlUsdc || 0) < 0 ? TG_THEME.red : TG_THEME.green, fontFamily: TG_THEME.mono, fontWeight: 800 }}>
                    {tgMoney(pos.unrealizedPnlUsdc || 0)}
                  </div>
                  <button onClick={() => closePosition(pos.positionId)} disabled={closing === pos.positionId} style={{
                    marginTop: '6px', padding: '6px 9px', borderRadius: '7px', border: `1px solid ${TG_THEME.separator}`,
                    background: TG_THEME.elevated, color: TG_THEME.text, fontSize: '11px', fontWeight: 700,
                  }}>{closing === pos.positionId ? 'Closing' : 'Close'}</button>
                </div>
              </div>
            </div>
          )) : (
            <div style={{ padding: '14px 16px', fontSize: '12px', color: TG_THEME.secondary, lineHeight: 1.45 }}>
              No open paper positions yet. The current buyable note is {best?.name || 'waiting for backend promotion'}.
            </div>
          )}
        </div>

        <div style={{ background: TG_THEME.surface, borderRadius: '12px', overflow: 'hidden' }}>
          <div style={{ padding: '12px 16px', fontSize: '11px', color: TG_THEME.secondary, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
            Realized ledger
          </div>
          {realized.length ? realized.slice(0, 5).map(row => (
            <div key={row.positionId} style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 74px', gap: '8px', padding: '10px 16px', borderTop: `0.5px solid ${TG_THEME.separator}` }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: '12px', color: TG_THEME.text, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.noteName}</div>
                <div style={{ fontSize: '10px', color: TG_THEME.tertiary }}>{Number(row.retPct || 0).toFixed(2)}% · {Number(row.notionalUsdc || 0).toLocaleString()} test USDC</div>
              </div>
              <div style={{ fontSize: '12px', color: Number(row.pnlUsdc || 0) < 0 ? TG_THEME.red : TG_THEME.green, fontFamily: TG_THEME.mono, fontWeight: 800, textAlign: 'right' }}>{tgMoney(row.pnlUsdc || 0)}</div>
            </div>
          )) : (
            <div style={{ padding: '14px 16px', fontSize: '12px', color: TG_THEME.secondary }}>
              No closed paper tickets yet.
            </div>
          )}
        </div>

        {error && <div style={{ fontSize: '12px', color: TG_THEME.red }}>{error}</div>}

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
          <button onClick={() => setScreen('dashboard')} style={{ padding: '13px', borderRadius: '10px', border: 'none', background: TG_THEME.green, color: '#000', fontSize: '13px', fontWeight: 800 }}>Mock Contract</button>
          <button onClick={openWebAccount} style={{ padding: '13px', borderRadius: '10px', border: `1px solid ${TG_THEME.separator}`, background: TG_THEME.elevated, color: TG_THEME.text, fontSize: '13px', fontWeight: 800 }}>Web Account</button>
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
  const accountData = useTelegramAccountData();
  const viewport = useViewport();
  const isMobile = viewport.width <= 900;
  const deviceWidth = Math.min(375, Math.max(300, viewport.width - 32));
  const deviceHeight = isMobile ? Math.min(720, Math.max(620, Math.round(deviceWidth * 1.82))) : 700;
  const screens = {
    home: TgHome, dashboard: TgDashboard, portfolio: TgPortfolio, scouting: TgScouting,
    updates: TgUpdates, alerts: TgAlerts, billing: TgBilling, scan: TgScanRunning,
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
      <div style={{
        flex: 1,
        paddingTop: isMobile ? '4px' : '20px',
        order: isMobile ? 2 : 1,
      }}>
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
      <div style={{
        flexShrink: 0,
        alignSelf: isMobile ? 'center' : 'flex-start',
        maxWidth: '100%',
        order: isMobile ? 1 : 2,
      }}>
        <IOSDevice width={deviceWidth} height={deviceHeight} dark>
          <Screen setScreen={setScreen} goBack={goBack} data={data} accountData={accountData} requestScan={requestBackendScan} />
        </IOSDevice>
      </div>
    </div>
  );
};

const TelegramMiniApp = () => {
  const { screen, setScreen, goBack } = useTgScreenRouter();
  const data = useTelegramBackendData();
  const accountData = useTelegramAccountData();
  const screens = {
    home: TgHome, dashboard: TgDashboard, portfolio: TgPortfolio, scouting: TgScouting,
    updates: TgUpdates, alerts: TgAlerts, billing: TgBilling, scan: TgScanRunning,
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
      paddingTop: 'env(safe-area-inset-top, 0px)',
      background: TG_THEME.bg, color: TG_THEME.text,
    }}>
      <Screen setScreen={setScreen} goBack={goBack} data={data} accountData={accountData} requestScan={requestBackendScan} />
    </div>
  );
};

Object.assign(window, { TelegramPage, TelegramMiniApp });
