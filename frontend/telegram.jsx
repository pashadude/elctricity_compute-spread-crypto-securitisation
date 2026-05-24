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

/* ── Mini App Screens ── */

const TgHome = ({ setScreen, data, requestScan }) => (
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
            { label: 'PnL', value: data.pnl.totalDisplay || 'Pending', color: data.pnl.hasReconciled ? TG_THEME.green : TG_THEME.secondary },
            { label: 'Jobs', value: String(data.pnl.wrappedJobs || 0), color: TG_THEME.text },
            { label: 'EXECUTEs', value: String(data.pnl.executes || 0), color: TG_THEME.text },
          ].map((s, i) => (
            <div key={i} style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '20px', fontWeight: 700, color: s.color, fontFamily: 'SF Mono, monospace' }}>{s.value}</div>
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
      <TgListItem icon="▦" title="Package Dashboard" subtitle="Spread, direct legs, proxy legs" accent={TG_THEME.green} onClick={() => setScreen('dashboard')} trailing={<span style={{ color: TG_THEME.secondary }}>›</span>} />
      <TgListItem icon="✓" title="Actionable Decisions" subtitle="EXECUTE / DEFER / CHALLENGE" accent={TG_THEME.green} onClick={() => setScreen('verdicts')} trailing={<TgBadge color={TG_THEME.green}>{data.verdicts?.length || 0}</TgBadge>} />
      <TgListItem icon="◇" title="Arc Positions" subtitle="ERC-8183 jobs on testnet" accent={TG_THEME.orange} onClick={() => setScreen('positions')} trailing={<span style={{ color: TG_THEME.secondary }}>›</span>} />
      <TgListItem icon="!" title="Alerts" subtitle="Sparse package notifications" accent={TG_THEME.orange} onClick={() => setScreen('alerts')} trailing={<span style={{ color: TG_THEME.secondary }}>›</span>} />
      <TgListItem icon="$" title="Subscription" subtitle="Operator plan · 5 test USDC" accent={TG_THEME.green} onClick={() => setScreen('billing')} trailing={<TgBadge color={TG_THEME.green}>$5</TgBadge>} />
    </div>

    {/* Quick actions */}
    <div style={{ padding: '0 16px 24px' }}>
      <div style={{ fontSize: '13px', color: TG_THEME.secondary, fontWeight: 600, marginBottom: '8px', paddingLeft: '4px' }}>Quick Actions</div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
        {[
          { label: 'Run Scan', icon: '▸', color: TG_THEME.green },
          { label: 'Mock Test', icon: '◎', color: TG_THEME.orange },
        ].map((a, i) => (
          <button key={i} onClick={() => setScreen('scan')} style={{
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

const TgDashboard = ({ setScreen, goBack, data }) => (
  <TgScreen title="Spread Package" subtitle="Arc Testnet" onBack={goBack}>
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
            <TgBadge color={data.syntheticInstrument.asset_backed ? TG_THEME.green : TG_THEME.orange}>
              {data.syntheticInstrument.asset_backed ? 'ASSET BACKED' : 'SYNTHETIC'}
            </TgBadge>
          </div>
          <div style={{ fontSize: '12px', color: TG_THEME.secondary, lineHeight: 1.4, marginBottom: '8px' }}>
            {data.syntheticInstrument.thesis}
          </div>
          <div style={{ fontSize: '12px', color: TG_THEME.secondary, lineHeight: 1.4, marginBottom: '6px' }}>
            Priced hedges: {((data.syntheticInstrument.outputs?.priced_hedge_basket || []).slice(0, 3).map(leg => leg.slug || leg.title).join(', ')) || 'needs live Yahoo/public prices'}
          </div>
          {data.syntheticInstrument.outputs?.mock_hedge_construction && (
            <div style={{ background: TG_THEME.elevated, borderRadius: '8px', padding: '9px', marginBottom: '6px' }}>
              <div style={{ fontSize: '10px', color: TG_THEME.secondary, textTransform: 'uppercase', fontWeight: 700 }}>Mock hedge funding</div>
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
            </div>
          )}
          {(data.syntheticInstrument.structure?.schematic_steps || []).length > 0 && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px', marginBottom: '6px' }}>
              {data.syntheticInstrument.structure.schematic_steps.slice(0, 4).map((step, i) => (
                <div key={step.key || i} style={{ background: TG_THEME.elevated, borderRadius: '7px', padding: '7px' }}>
                  <div style={{ fontSize: '10px', color: TG_THEME.secondary, textTransform: 'uppercase', fontWeight: 700 }}>{step.status}</div>
                  <div style={{ fontSize: '11px', color: TG_THEME.text, lineHeight: 1.25, marginTop: '2px' }}>{step.label}</div>
                </div>
              ))}
            </div>
          )}
          {(data.syntheticInstrument.outputs?.discovery_gaps || []).length > 0 && (
            <div style={{ fontSize: '12px', color: TG_THEME.orange, lineHeight: 1.4, marginBottom: '6px' }}>
              Pricing gaps: {data.syntheticInstrument.outputs.discovery_gaps.slice(0, 2).map(gap => `${gap.slug || gap.title} (${gap.status_label || 'Needs price'})`).join(', ')}
            </div>
          )}
          {(data.syntheticInstrument.outputs?.agent_search_plan || []).length > 0 && (
            <div style={{ fontSize: '12px', color: TG_THEME.secondary, lineHeight: 1.4, marginBottom: '6px' }}>
              Search next: {data.syntheticInstrument.outputs.agent_search_plan.slice(0, 2).map(item => `${item.surface}:${item.target}`).join(', ')}
            </div>
          )}
          <div style={{ fontSize: '12px', color: TG_THEME.tertiary, lineHeight: 1.4 }}>
            Next: {(data.syntheticInstrument.outputs?.agent_next_actions || [])[0] || 'wait for stronger signal'}
          </div>
        </div>
      )}

      {/* Package legs */}
      <div style={{ background: TG_THEME.surface, borderRadius: '12px', overflow: 'hidden' }}>
        <div style={{ padding: '12px 16px', fontSize: '11px', color: TG_THEME.secondary, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
          Current Spread Package
        </div>
        <div style={{ padding: '0 16px 10px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px' }}>
          {['1 Spread', '2 Package', '3 Legs', '4 Judge→Arc'].map((step, i) => (
            <div key={i} style={{ fontSize: '11px', color: TG_THEME.secondary, background: TG_THEME.elevated, borderRadius: '6px', padding: '6px 8px' }}>
              {step}
            </div>
          ))}
        </div>
        {data.currentPackage && (
          <div style={{ padding: '0 16px 10px' }}>
            <div style={{ fontSize: '13px', color: TG_THEME.text, fontWeight: 600 }}>
              {String(data.currentPackage.direction || data.direction || 'no_signal').replace('_', ' ')}
            </div>
            <div style={{ fontSize: '12px', color: TG_THEME.secondary, marginTop: '2px' }}>
              package verdict: {data.currentPackage.label || 'PENDING'}{data.currentPackage.reason ? ` · ${data.currentPackage.reason}` : ''}
              {data.currentPackage.repeatCount > 1 ? ` · ${data.currentPackage.repeatCount} scan rows collapsed` : ''}
            </div>
          </div>
        )}
        {[
          ['Direct event / forecast', data.currentPackage?.directLegs || []],
          ['Proxy', data.currentPackage?.proxyLegs || []],
        ].map(([section, legs]) => (
          <div key={section}>
            <div style={{ padding: '8px 16px 4px', fontSize: '11px', color: TG_THEME.tertiary, fontWeight: 600, textTransform: 'uppercase' }}>
              {section}
            </div>
            {legs.length ? legs.slice(0, 4).map((c, i) => {
              const trail = c.estPnl ? `${c.estPnl} $/$` : (c.pricingStatus || 'watchlist');
              return (
                <TgListItem key={`${section}-${i}`} icon={surfaceIcon(c.surface)} title={c.displayName || c.instrument || 'candidate'}
                  subtitle={`${c.surface || 'surface'} · ${c.directPairRole || c.role || 'expression leg'} · ${c.direction || c.dir || 'pending'} · ${c.sizing || 0} USDC${c.repeatCount > 1 ? ` · seen ${c.repeatCount} scans` : ''}${c.endDate ? ` · resolves ${formatEventDate(c.endDate)}` : ''}`}
                  trailing={<span style={{ fontFamily: 'SF Mono, monospace', fontSize: '13px', color: Number(c.estPnl || 0) < 0 ? TG_THEME.red : TG_THEME.green }}>{trail}</span>}
                />
              );
            }) : (
              <div style={{ padding: '8px 16px 12px', fontSize: '12px', color: TG_THEME.secondary }}>
                {section === 'Proxy'
                  ? 'No proxy leg routed for this signal.'
                  : (data.currentPackage?.directBlockedSummary || 'No direct leg currently passing discovery.')}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  </TgScreen>
);

const TgVerdicts = ({ setScreen, goBack, data }) => (
  <TgScreen title="Actionable Decisions" onBack={goBack}>
    <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
      {!(data.verdicts || []).length && (
        <div style={{ background: TG_THEME.surface, borderRadius: '10px', padding: '14px', fontSize: '13px', color: TG_THEME.secondary }}>
          No actionable judge decisions in this snapshot.
        </div>
      )}
      {(data.verdicts || []).slice(0, 8).map((v, i) => {
        const colors = { EXECUTE: TG_THEME.green, REJECT: TG_THEME.red, DEFER: TG_THEME.orange, CHALLENGE: '#BF5AF2' };
        return (
          <div key={i} style={{ background: TG_THEME.surface, borderRadius: '10px', padding: '14px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '15px' }}>{surfaceIcon(v.surface)}</span>
                <span style={{ fontSize: '15px', fontWeight: 600, color: TG_THEME.text }}>{v.displayName || v.instrument}</span>
              </div>
              <TgBadge color={colors[v.label]}>{v.label}</TgBadge>
            </div>
            <div style={{ fontSize: '12px', color: TG_THEME.secondary }}>
              {v.reason}{v.repeatCount > 1 ? ` · seen ${v.repeatCount} scans` : ''}{v.slug ? ` · ${v.slug}` : ''}{v.endDate ? ` · resolves ${formatEventDate(v.endDate)}` : ''}
            </div>
            {v.connection && (
              <div style={{ fontSize: '12px', color: TG_THEME.tertiary, marginTop: '6px', lineHeight: 1.35 }}>
                {v.connection}
              </div>
            )}
          </div>
        );
      })}
    </div>
  </TgScreen>
);

const TgPositions = ({ setScreen, goBack, data }) => (
  <TgScreen title="Arc Positions" subtitle="ERC-8183 Jobs" onBack={goBack}>
    <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
      {(data.positions || []).map((p, i) => (
        <div key={i} style={{ background: TG_THEME.surface, borderRadius: '10px', padding: '14px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontFamily: 'SF Mono, monospace', fontSize: '14px', fontWeight: 700, color: TG_THEME.green }}>#{p.jobId}</span>
              <TgBadge color={p.status === 'completed' ? TG_THEME.green : TG_THEME.orange}>{p.status}</TgBadge>
            </div>
            <span style={{
              fontFamily: 'SF Mono, monospace', fontSize: '15px', fontWeight: 700,
              color: p.pnl.startsWith('+') ? TG_THEME.green : TG_THEME.text,
            }}>{p.pnl === '-' ? '—' : p.pnl}</span>
          </div>
          <div style={{ fontSize: '13px', color: TG_THEME.secondary }}>
            {surfaceIcon(p.surface)} {p.surface} · {p.role || 'expression leg'} · {p.sizing} USDC
          </div>
          <div style={{ fontSize: '13px', color: TG_THEME.text, marginTop: '6px', fontWeight: 600 }}>
            {p.displayName || p.instrument}
          </div>
          {(p.slug || p.endDate) && (
            <div style={{ fontSize: '11px', color: TG_THEME.tertiary, marginTop: '3px' }}>
              {p.slug || p.instrument}{p.endDate ? ` · resolves ${formatEventDate(p.endDate)}` : ''}
            </div>
          )}
          {p.connection && (
            <div style={{ fontSize: '12px', color: TG_THEME.secondary, marginTop: '6px', lineHeight: 1.35 }}>
              {p.connection}
            </div>
          )}
          <div style={{ fontSize: '11px', color: TG_THEME.tertiary, marginTop: '6px', fontFamily: 'SF Mono, monospace' }}>
            {p.txHash}
          </div>
        </div>
      ))}
    </div>
  </TgScreen>
);

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
        {Object.entries({ signals: 'New Signals', verdicts: 'Actionable Package Decisions', positions: 'Arc Position Updates', pnl: 'PnL Thresholds', oracle: 'Oracle Evidence Updates' }).map(([k, label]) => (
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
            Operator-lite access: package dashboard, scan commands, actionable alerts, and Arc Testnet controls.
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
            <button onClick={() => setScreen('verdicts')} style={{
              padding: '14px 32px', borderRadius: '10px', border: 'none',
              background: TG_THEME.green, color: '#000', fontSize: '15px', fontWeight: 700, cursor: 'pointer',
            }}>View Verdicts</button>
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
    home: TgHome, dashboard: TgDashboard, verdicts: TgVerdicts,
    positions: TgPositions, alerts: TgAlerts, billing: TgBilling, scan: TgScanRunning,
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
          Full Mini App experience inside Telegram. Monitor canonical compute/energy spread packages, review actionable package decisions, manage Arc positions, and pay 5 Circle test USDC without leaving the chat.
        </p>
        <TgWebLinks />

        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {[
            { title: 'Live Signal Feed', desc: 'Real-time electricity–compute spread with package alerts', IconComp: IconGrid, iconColor: TG_THEME.orange },
            { title: 'Actionable Decisions', desc: 'Review EXECUTE/DEFER/CHALLENGE package decisions without reject spam', IconComp: IconJudge, iconColor: TG_THEME.green },
            { title: 'Arc Settlement', desc: 'Track ERC-8183 jobs and USDC escrow on testnet', IconComp: IconArc, iconColor: TG_THEME.green },
            { title: 'Circle Payments', desc: 'Operator access is 5 test USDC on Arc Testnet', IconComp: IconCoin, iconColor: TG_THEME.orange },
            { title: 'Scan Commands', desc: 'Trigger one-shot scans and mock tests from chat', IconComp: IconSignal, iconColor: TG_THEME.green },
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
    home: TgHome, dashboard: TgDashboard, verdicts: TgVerdicts,
    positions: TgPositions, alerts: TgAlerts, billing: TgBilling, scan: TgScanRunning,
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
