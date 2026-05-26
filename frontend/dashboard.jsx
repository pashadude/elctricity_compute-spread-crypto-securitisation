/* Arc Compute Sec — Dashboard */

/* ── Backend Data Engine ── */
const numberOr = (value, fallback = 0) => {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
};

const tsMs = (value) => {
  const n = numberOr(value, Date.now() / 1000);
  return n < 10_000_000_000 ? n * 1000 : n;
};

const surfaceRank = (surface) => ({ polymarket: 0, ibkr_prediction: 1, kalshi: 2, crypto: 3, ibkr: 4 }[surface] ?? 9);
const isPredictionSurface = (surface) => ['polymarket', 'ibkr_prediction', 'kalshi'].includes(surface);
const sortByPrimarySurface = (rows) => [...rows].sort((a, b) => (
  surfaceRank(a.surface) - surfaceRank(b.surface)
));

const roleLabel = (role, surface) => ({
  direct_prediction_event: 'direct event leg',
  miner_margin_proxy: 'miner-margin proxy',
  liquid_equity_proxy: 'liquid equity proxy',
  macro_context_forecast: 'macro context forecast',
}[role] || ({
  polymarket: 'direct event leg',
  ibkr_prediction: 'direct forecast leg',
  crypto: 'miner-margin proxy',
  ibkr: 'liquid equity proxy',
  kalshi: 'direct event leg',
}[surface] || 'expression leg'));

const formatEventDate = (value) => {
  if (!value) return '';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleDateString('en', { month: 'short', day: 'numeric', year: 'numeric' });
};

const pricingStatusLabel = (status) => {
  const low = String(status || '').toLowerCase();
  if (low === 'unpriced_snapshot') return 'Needs live venue price';
  if (low === 'metadata_watchlist') return 'Metadata only';
  if (low === 'priced_watchlist') return 'Live price available';
  if (low === 'priced_public_market') return 'Public price available';
  if (low === 'price_unavailable') return 'Price unavailable';
  if (low === 'ibkr_quote_unavailable') return 'IBKR quote unavailable';
  if (low === 'closed_watchlist') return 'Closed';
  return String(status || 'Needs review').replaceAll('_', ' ');
};

const proxySourceLabel = (source, stale = false) => {
  const low = String(source || '').toLowerCase();
  if (low === 'public_quote') return 'Public quote adapter';
  if (low === 'ibkr_energy_history_csv') return `IBKR paper CSV${stale ? ' · stale' : ''}`;
  if (low === 'ibkr_tws_front_future') return 'IBKR paper TWS front future';
  if (low === 'ibkr_tws_stock') return 'IBKR paper TWS stock';
  if (low === 'yahoo_finance_chart') return 'Yahoo fallback';
  if (low === 'alpaca_market_data') return 'Alpaca fallback';
  if (low === 'ibkr_tws') return 'IBKR paper TWS';
  return source || 'external proxy';
};

const quoteSourceLabels = (sources = []) => {
  const labels = [...new Set((sources || []).map(src => proxySourceLabel(src)).filter(Boolean))];
  return labels;
};

const quoteSourceSummary = (sources = []) => quoteSourceLabels(sources).join(', ');

const proxyMarkMeta = (leg = {}) => {
  const parts = [proxySourceLabel(leg.externalProxySource, leg.externalProxyStale)];
  if (leg.externalProxyRegularMarketTime) parts.push(`as of ${leg.externalProxyRegularMarketTime}`);
  if (leg.externalProxyExpiry) parts.push(`expiry ${leg.externalProxyExpiry}`);
  return parts.filter(Boolean).join(' · ');
};

const hasExternalProxyPrice = (row = {}) => (
  row.externalProxyLastPrice !== null
  && row.externalProxyLastPrice !== undefined
  && Number.isFinite(Number(row.externalProxyLastPrice))
);

const isMockRow = (row = {}) => {
  const text = [row.instrument, row.displayName, row.slug, row.description]
    .filter(Boolean).join(' ').toLowerCase();
  return Boolean(row.isMock) || text.includes('mock');
};

const isHiddenAuditRow = (row = {}) => (
  isMockRow(row) || Boolean(row.isThesisMismatch) || Boolean(row.isLegacyArtifact)
);

const isRejectedRow = (row = {}) => String(row.label || '').toUpperCase() === 'REJECT';
const isActionableRow = (row = {}) => !isHiddenAuditRow(row) && !isRejectedRow(row);

const dedupeRows = (rows, keyFn) => {
  const seen = new Map();
  rows.forEach(row => {
    const key = keyFn(row);
    const existing = seen.get(key);
    if (!existing) {
      seen.set(key, { ...row, repeatCount: row.repeatCount || 1 });
      return;
    }
    existing.repeatCount = (existing.repeatCount || 1) + (row.repeatCount || 1);
  });
  return [...seen.values()].sort((a, b) => (b.ts || 0) - (a.ts || 0));
};

const legKey = (row = {}) => [
  row.surface, row.instrument, row.direction || row.dir, row.role, row.label, row.reason,
].join('|');

const derivePrimaryExposure = ({ positions = [], verdicts = [], candidates = [] }) => {
  const latestPosition = positions[0];
  if (latestPosition) {
    const matchingVerdict = verdicts.find(v => (
      v.surface === latestPosition.surface && v.instrument === latestPosition.instrument
    ));
    return {
      surface: latestPosition.surface,
      instrument: latestPosition.instrument || 'selected leg',
      displayName: latestPosition.displayName || latestPosition.instrument || 'selected leg',
      slug: latestPosition.slug || '',
      description: latestPosition.description || '',
      endDate: latestPosition.endDate || '',
      connection: latestPosition.connection || '',
      direction: latestPosition.direction || matchingVerdict?.direction || 'pending',
      sizing: latestPosition.sizing || matchingVerdict?.sizing || 0,
      verdict: matchingVerdict?.label || 'EXECUTE',
      jobStatus: latestPosition.status || 'wrapped',
      jobId: latestPosition.jobId,
      estPnl: matchingVerdict?.estPnl || '',
      role: latestPosition.role || roleLabel('', latestPosition.surface),
    };
  }
  const topVerdict = sortByPrimarySurface(verdicts)[0];
  if (topVerdict) {
    return {
      surface: topVerdict.surface,
      instrument: topVerdict.instrument || 'candidate leg',
      displayName: topVerdict.displayName || topVerdict.instrument || 'candidate leg',
      slug: topVerdict.slug || '',
      description: topVerdict.description || '',
      endDate: topVerdict.endDate || '',
      connection: topVerdict.connection || '',
      direction: topVerdict.direction || 'pending',
      sizing: topVerdict.sizing || 0,
      verdict: topVerdict.label || 'DEFER',
      jobStatus: topVerdict.label === 'EXECUTE' ? 'ready' : 'not wrapped',
      jobId: '',
      estPnl: topVerdict.estPnl || '',
      role: topVerdict.role || roleLabel('', topVerdict.surface),
    };
  }
  const topCandidate = candidates[0];
  if (topCandidate) {
    return {
      surface: topCandidate.surface,
      instrument: topCandidate.instrument || 'candidate leg',
      displayName: topCandidate.displayName || topCandidate.instrument || 'candidate leg',
      slug: topCandidate.slug || '',
      description: topCandidate.description || '',
      endDate: topCandidate.endDate || '',
      connection: topCandidate.connection || '',
      direction: topCandidate.dir || topCandidate.direction || 'pending',
      sizing: topCandidate.sizing || 0,
      verdict: topCandidate.label || 'pending',
      jobStatus: topCandidate.inventory ? 'watchlist' : 'not wrapped',
      jobId: '',
      estPnl: topCandidate.estPnl || '',
      role: topCandidate.role || roleLabel('', topCandidate.surface),
    };
  }
  return null;
};

const emptyDashboardData = (status = 'loading', error = '') => ({
  spread: { elec: '0.00', compute: '0.0000', st: '0.0000', k: 0.5, kwh: 0.7 },
  history: [],
  z: 0,
  mean: 0,
  std: 0,
  direction: 'no_signal',
  primaryExposure: null,
  candidates: [],
  verdicts: [],
  positions: [],
  directInventory: [],
  packages: [],
  currentPackage: null,
  syntheticInstrument: null,
  pnl: {
    total: 0, totalDisplay: 'Pending', winRate: 0, trades: 0,
    tradesDisplay: 'Pending', wrappedJobs: 0, executes: 0, hasReconciled: false,
  },
  oracleResults: genOracleResults(),
  connection: { status, error, updatedAt: Date.now() },
});

const mapSnapshotToDashboardData = (snapshot) => {
  const spreadLatest = snapshot?.spread?.latest || {};
  const signal = snapshot?.signal?.latest || {};
  const history = (snapshot?.spread?.history || []).map(v => numberOr(v)).filter(Number.isFinite);
  const mean = history.length ? history.reduce((a, b) => a + b, 0) / history.length : 0;
  const std = history.length > 1
    ? Math.sqrt(history.reduce((a, b) => a + (b - mean) ** 2, 0) / (history.length - 1))
    : 0;
  const mapLeg = (v, i, prefix = 'v') => ({
    ts: tsMs(v.ts || snapshot.generated_at),
    label: v.label || (v.inventory ? 'WATCHLIST' : 'DEFER'),
    reason: v.reason_code || '',
    reasonLabel: pricingStatusLabel(v.reason_code || v.pricing_status || ''),
    instrument: v.instrument || '',
    displayName: v.display_label || v.leg_title || v.instrument || '',
    slug: v.leg_slug || '',
    description: v.leg_description || '',
    endDate: v.leg_end_date || '',
    role: roleLabel(v.leg_role, v.surface),
    connection: v.leg_connection || '',
    isMock: Boolean(v.is_mock),
    isThesisMismatch: Boolean(v.is_thesis_mismatch),
    isLegacyArtifact: Boolean(v.is_legacy_artifact),
    surface: v.surface || '',
    direction: v.direction || '',
    confidence: numberOr(v.confidence, 0).toFixed(3),
    sizing: numberOr(v.sizing_usdc, 0),
    estPnl: (v.est_pnl_per_dollar === undefined || v.est_pnl_per_dollar === '') ? '' : numberOr(v.est_pnl_per_dollar, 0).toFixed(4),
    pricingStatus: v.pricing_status || '',
    pricingStatusLabel: v.pricing_status_label || pricingStatusLabel(v.pricing_status || ''),
    externalProxySymbol: v.external_proxy_symbol || '',
    externalProxyTitle: v.external_proxy_title || '',
    externalProxyRole: v.external_proxy_role || '',
    externalProxyLastPrice: v.external_proxy_last_price === undefined || v.external_proxy_last_price === '' ? null : numberOr(v.external_proxy_last_price, null),
    externalProxySource: v.external_proxy_source || '',
    externalProxySourcePriority: v.external_proxy_source_priority || '',
    externalProxyRegularMarketTime: v.external_proxy_regular_market_time || '',
    externalProxyExpiry: v.external_proxy_expiry || '',
    externalProxyStale: Boolean(v.external_proxy_stale),
    externalProxyStatus: v.external_proxy_status || '',
    externalProxyStatusLabel: v.external_proxy_status_label || '',
    directPairRole: v.direct_pair_role || '',
    inventory: Boolean(v.inventory),
    source: v.source || '',
    packageId: v.package_id || v.arb_signal_id || '',
    repeatCount: numberOr(v.repeat_count, 1),
    id: v.action_payload_hash || `${prefix}-${i}`,
  });
  const rawVerdicts = ((snapshot?.verdict_rollups || []).length ? snapshot.verdict_rollups : (snapshot?.verdicts || []))
    .map((v, i) => mapLeg(v, i, 'v'));
  const rawPositions = (snapshot?.positions || []).map((p, i) => ({
    ts: tsMs(p.ts || snapshot.generated_at),
    jobId: p.job_id || `local-${i}`,
    surface: p.surface || '',
    instrument: p.instrument || '',
    displayName: p.display_label || p.leg_title || p.instrument || '',
    slug: p.leg_slug || '',
    description: p.leg_description || '',
    endDate: p.leg_end_date || '',
    role: roleLabel(p.leg_role, p.surface),
    connection: p.leg_connection || '',
    isMock: Boolean(p.is_mock),
    isThesisMismatch: Boolean(p.is_thesis_mismatch),
    isLegacyArtifact: Boolean(p.is_legacy_artifact),
    direction: p.direction || '',
    status: p.status || p.stage || 'unknown',
    sizing: numberOr(p.notional_usdc, 0),
    pnl: p.actual_pnl_usd !== undefined ? `${numberOr(p.actual_pnl_usd).toFixed(2)}` : '-',
    txHash: p.tx_hash ? `${String(p.tx_hash).slice(0, 10)}...` : '',
    arcscanUrl: p.arcscan_url || '',
    packageId: p.package_id || p.arb_signal_id || '',
    repeatCount: numberOr(p.repeat_count, 1),
  }));
  const verdicts = dedupeRows(rawVerdicts.filter(isActionableRow), legKey);
  const positions = dedupeRows(rawPositions.filter(p => !isHiddenAuditRow(p)), legKey);
  const directInventory = dedupeRows(
    (snapshot?.direct_inventory || []).map((leg, i) => mapLeg(leg, i, 'inv')).filter(row => !isHiddenAuditRow(row)),
    legKey,
  );
  const repeatByLeg = new Map(verdicts.map(v => [legKey(v), numberOr(v.repeatCount, 1)]));
  const withRollupRepeat = (leg) => ({
    ...leg,
    repeatCount: Math.max(numberOr(leg.repeatCount, 1), numberOr(repeatByLeg.get(legKey(leg)), 1)),
  });
  const candidates = verdicts.map(v => ({
    id: v.id,
    surface: v.surface,
    instrument: v.instrument,
    displayName: v.displayName,
    slug: v.slug,
    description: v.description,
    endDate: v.endDate,
    role: v.role,
    connection: v.connection,
    dir: v.direction,
    sizing: v.sizing,
    conviction: Math.abs(numberOr(signal.z, 0)).toFixed(2),
    estPnl: v.estPnl,
    pricingStatus: v.pricingStatus,
    pricingStatusLabel: v.pricingStatusLabel,
    externalProxySymbol: v.externalProxySymbol,
    externalProxyTitle: v.externalProxyTitle,
    externalProxyRole: v.externalProxyRole,
    externalProxyLastPrice: v.externalProxyLastPrice,
    externalProxySource: v.externalProxySource,
    externalProxySourcePriority: v.externalProxySourcePriority,
    externalProxyRegularMarketTime: v.externalProxyRegularMarketTime,
    externalProxyExpiry: v.externalProxyExpiry,
    externalProxyStale: v.externalProxyStale,
    externalProxyStatus: v.externalProxyStatus,
    externalProxyStatusLabel: v.externalProxyStatusLabel,
    directPairRole: v.directPairRole,
    inventory: v.inventory,
    source: v.source,
    label: v.label,
    reason: v.reason,
    reasonLabel: v.reasonLabel,
    repeatCount: v.repeatCount,
  }));
  const sortedCandidates = sortByPrimarySurface(candidates);
  const packages = (snapshot?.packages || []).map((pkg, i) => {
    const directLegs = (pkg.direct_legs || []).map((leg, j) => mapLeg(leg, j, `pkg-${i}-d`)).filter(isActionableRow);
    const proxyLegs = (pkg.proxy_legs || []).map((leg, j) => mapLeg(leg, j, `pkg-${i}-p`)).filter(isActionableRow);
    const positionLegs = (pkg.positions || []).map((leg, j) => ({
      ...mapLeg(leg, j, `pkg-${i}-pos`),
      status: leg.status || leg.stage || '',
      jobId: leg.job_id || '',
    })).filter(leg => !isHiddenAuditRow(leg));
    const direct = dedupeRows(directLegs, legKey).map(withRollupRepeat);
    const proxy = dedupeRows(proxyLegs, legKey).map(withRollupRepeat);
    const visibleDirect = direct.length ? direct : directInventory.filter(leg => isPredictionSurface(leg.surface));
    const packageDirection = ['long', 'short'].includes(String(pkg.direction || ''))
      ? (signal.direction || pkg.direction)
      : (pkg.direction || signal.direction || 'no_signal');
    return {
      id: pkg.id || pkg.package_id || pkg.arb_signal_id || `pkg-${i}`,
      packageId: pkg.package_id || '',
      signalId: pkg.arb_signal_id || '',
      ts: tsMs(pkg.ts || snapshot.generated_at),
      direction: packageDirection,
      label: pkg.label || 'PENDING',
      reason: pkg.reason_code || '',
      repeatCount: [...visibleDirect, ...proxy].reduce((sum, leg) => sum + numberOr(leg.repeatCount, 1), 0) || numberOr(pkg.repeat_count, 1),
      directBlockedSummary: pkg.direct_blocked_summary || '',
      proxyBlockedSummary: pkg.proxy_blocked_summary || '',
      rejectedDirectRepeatCount: numberOr(pkg.rejected_direct_repeat_count, 0),
      rejectedProxyRepeatCount: numberOr(pkg.rejected_proxy_repeat_count, 0),
      actionableDirectLegCount: numberOr(pkg.actionable_direct_leg_count, direct.length),
      actionableProxyLegCount: numberOr(pkg.actionable_proxy_leg_count, proxy.length),
      directLegs: visibleDirect,
      proxyLegs: proxy,
      positions: dedupeRows(positionLegs, legKey),
    };
  }).filter(pkg => pkg.label !== 'REJECT' && (pkg.directLegs.length || pkg.proxyLegs.length || pkg.positions.length))
    .sort((a, b) => b.ts - a.ts);
  const fallbackDirectLegs = dedupeRows(
    [...sortedCandidates.filter(c => isPredictionSurface(c.surface)), ...directInventory.filter(c => isPredictionSurface(c.surface))],
    legKey,
  );
  const fallbackProxyLegs = sortedCandidates.filter(c => !isPredictionSurface(c.surface));
  const fallbackPackage = (sortedCandidates.length || directInventory.length) ? {
    id: signal.signal_id || 'current-package',
    packageId: '',
    signalId: signal.signal_id || '',
    ts: tsMs(signal.ts || snapshot?.generated_at),
    direction: signal.direction || 'no_signal',
    label: sortedCandidates[0]?.label || 'WATCHLIST',
    reason: sortedCandidates[0]?.reason || (directInventory.length ? 'direct_event_inventory' : ''),
    repeatCount: [...fallbackDirectLegs, ...fallbackProxyLegs].reduce((sum, leg) => sum + numberOr(leg.repeatCount, 1), 0),
    directLegs: fallbackDirectLegs,
    proxyLegs: fallbackProxyLegs,
    positions: [],
  } : null;
  const currentPackage = packages[0] || fallbackPackage;
  const primaryExposure = derivePrimaryExposure({ positions, verdicts, candidates: sortedCandidates.length ? sortedCandidates : directInventory });
  const pnl = snapshot?.pnl || {};
  const hasReconciled = Boolean(pnl.has_reconciled) || numberOr(pnl.trades, 0) > 0;
  const reconciledTrades = numberOr(pnl.reconciled_trades, numberOr(pnl.trades, 0));
  const wrappedJobs = numberOr(pnl.wrapped_jobs, positions.filter(p => !String(p.jobId).startsWith('local-')).length);
  const executes = numberOr(pnl.executed_verdicts, verdicts.filter(v => v.label === 'EXECUTE').length);
  return {
    spread: {
      elec: numberOr(spreadLatest.electricity_per_mwh).toFixed(2),
      compute: numberOr(spreadLatest.compute_per_gpu_hr).toFixed(4),
      st: numberOr(spreadLatest.S_t).toFixed(4),
      k: numberOr(spreadLatest.k, 0.5),
      kwh: numberOr(spreadLatest.kwh_per_gpu_hr, 0.7),
    },
    history,
    z: numberOr(signal.z),
    mean,
    std,
    direction: signal.direction || 'no_signal',
    primaryExposure,
    candidates: sortedCandidates,
    verdicts,
    positions,
    directInventory,
    packages,
    currentPackage,
    syntheticInstrument: snapshot?.synthetic_instrument || null,
    pnl: {
      total: numberOr(pnl.total),
      totalDisplay: hasReconciled ? `$${numberOr(pnl.total).toFixed(4)}` : 'Pending',
      winRate: numberOr(pnl.win_rate),
      trades: reconciledTrades,
      tradesDisplay: hasReconciled ? String(reconciledTrades) : 'Pending',
      wrappedJobs,
      executes,
      hasReconciled,
    },
    oracleResults: genOracleResults(),
    connection: {
      status: 'live',
      error: '',
      updatedAt: tsMs(snapshot?.generated_at),
      runtime: snapshot?.runtime || {},
      mode: snapshot?.mode || {},
    },
  };
};

const useLiveData = (refreshRate) => {
  const [data, setData] = React.useState(() => emptyDashboardData());

  React.useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const resp = await fetch('/api/snapshot', { cache: 'no-store' });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const snapshot = await resp.json();
        if (!cancelled) setData(mapSnapshotToDashboardData(snapshot));
      } catch (err) {
        if (!cancelled) setData(prev => ({
          ...prev,
          connection: { status: 'offline', error: String(err.message || err), updatedAt: Date.now() },
        }));
      }
    };
    load();
    const interval = setInterval(load, refreshRate);
    return () => { cancelled = true; clearInterval(interval); };
  }, [refreshRate]);

  return data;
};

function genCandidates(z) {
  const surfaces = [
    { surface: 'crypto', instrument: 'BTC/USD', dir: 'short', sizing: 5.0 },
    { surface: 'crypto', instrument: 'ETH/USD', dir: 'short', sizing: 3.0 },
    { surface: 'ibkr', instrument: 'GOOGL', dir: 'short', sizing: 1.0 },
    { surface: 'ibkr', instrument: 'AMZN', dir: 'short', sizing: 1.0 },
    { surface: 'ibkr', instrument: 'MSFT', dir: 'short', sizing: 1.0 },
    { surface: 'polymarket', instrument: 'ERCOT grid event', dir: 'short', sizing: 2.0 },
    { surface: 'polymarket', instrument: 'AI infra milestone', dir: 'short', sizing: 2.0 },
  ];
  return surfaces.map((s, i) => ({
    id: `c-${(Math.random() * 99999).toFixed(0)}`,
    ...s,
    conviction: Math.abs(z).toFixed(2),
    estPnl: (Math.random() * 0.15 + 0.02).toFixed(4),
  }));
}

function genVerdicts() {
  const labels = ['EXECUTE', 'REJECT', 'REJECT', 'EXECUTE', 'DEFER', 'EXECUTE', 'REJECT', 'EXECUTE', 'CHALLENGE', 'EXECUTE'];
  const reasons = { EXECUTE: 'all_gates_passed', REJECT: 'premium_gate_fail', DEFER: 'stale_data', CHALLENGE: 'size_above_challenge_threshold_v0_defer' };
  const instruments = ['BTC/USD', 'ETH/USD', 'GOOGL', 'AMZN', 'MSFT', 'ERCOT grid', 'AI milestone'];
  return labels.map((l, i) => ({
    ts: Date.now() - i * 180000 - Math.random() * 60000,
    label: l, reason: reasons[l],
    instrument: instruments[i % instruments.length],
    surface: ['crypto', 'ibkr', 'polymarket'][i % 3],
    confidence: (0.8 + Math.random() * 0.2).toFixed(3),
  }));
}

function genPositions() {
  return [
    { jobId: '19091', surface: 'crypto', instrument: 'BTC/USD', status: 'completed', sizing: 5.0, pnl: '+12.44', txHash: '0xee545e...' },
    { jobId: '17884', surface: 'polymarket', instrument: 'ERCOT grid', status: 'completed', sizing: 2.0, pnl: '+3.21', txHash: '0x05bc9a...' },
    { jobId: '19102', surface: 'crypto', instrument: 'ETH/USD', status: 'submitted', sizing: 3.0, pnl: '-', txHash: '0xab12cd...' },
  ];
}

function genOracleResults() {
  return { scanned: 1301, energyClassified: 122, aiInfra: { n: 70, wr: 97.1, pnl: 68.654 }, geopolitics: { n: 52, wr: 92.3, pnl: -12.224 }, gateKept: 99, gatePnl: 152.026 };
}

/* ── Dashboard Components ── */

const StatCard = ({ label, value, suffix, prefix, change, sparkData, color, valueSize = 28 }) => (
  <Card style={{ padding: '20px' }} title={typeof value === 'string' ? value : undefined}>
    <div style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.muted, marginBottom: '8px' }}>{label}</div>
    <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between' }}>
      <div style={{ minWidth: 0 }}>
        <span style={{
          fontFamily: THEME.font.heading, fontSize: valueSize, fontWeight: 800,
          color: THEME.text.primary, letterSpacing: 0, lineHeight: 1.05,
          overflowWrap: 'anywhere',
        }}>
          {prefix}{typeof value === 'number' ? <AnimatedNumber value={value} decimals={value > 10 ? 2 : 4} /> : value}{suffix}
        </span>
        {change !== undefined && (
          <span style={{ fontFamily: THEME.font.mono, fontSize: '12px', marginLeft: '8px', color: change >= 0 ? THEME.primary[400] : THEME.red[400] }}>
            {change >= 0 ? '↑' : '↓'} {Math.abs(change).toFixed(2)}%
          </span>
        )}
      </div>
      {sparkData && <Sparkline data={sparkData} width={80} height={28} color={color || THEME.primary[400]} />}
    </div>
  </Card>
);

const SignalPanel = ({ data }) => {
  const zColor = Math.abs(data.z) > 2 ? THEME.red[400] : Math.abs(data.z) > 1 ? THEME.amber[400] : THEME.primary[400];
  const isNarrow = useIsMobile(560);
  return (
    <Card glow>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: isNarrow ? 'stretch' : 'flex-start',
        gap: '10px',
        flexDirection: isNarrow ? 'column' : 'row',
        marginBottom: '16px',
      }}>
        <div>
          <SectionLabel>Spread Signal</SectionLabel>
          <div style={{ fontFamily: THEME.font.heading, fontSize: '14px', color: THEME.text.secondary }}>
            S_t = compute − k × (elec/1000) × kWh
          </div>
        </div>
        <Badge color={data.direction === 'compute_expensive' ? 'blue' : 'amber'}>
          {data.direction.replace('_', ' ')}
        </Badge>
      </div>
      <div style={{
        display: 'grid',
        gridTemplateColumns: isNarrow ? 'repeat(2, minmax(0, 1fr))' : 'repeat(4, minmax(0, 1fr))',
        gap: isNarrow ? '10px' : '16px',
        marginBottom: '20px',
        minWidth: 0,
      }}>
        <div>
          <div style={{ fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.muted }}>Electricity</div>
          <MonoText style={{ fontSize: '18px', fontWeight: 700, color: THEME.amber[400] }}>${data.spread.elec}/MWh</MonoText>
        </div>
        <div>
          <div style={{ fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.muted }}>Compute</div>
          <MonoText style={{ fontSize: '18px', fontWeight: 700, color: THEME.blue[400] }}>${data.spread.compute}/GPU-hr</MonoText>
        </div>
        <div>
          <div style={{ fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.muted }}>Spread S_t</div>
          <MonoText style={{ fontSize: '18px', fontWeight: 700 }}>${data.spread.st}</MonoText>
        </div>
        <div>
          <div style={{ fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.muted }}>Z-Score</div>
          <MonoText style={{ fontSize: '18px', fontWeight: 700, color: zColor }}>
            {data.z.toFixed(3)}
          </MonoText>
        </div>
      </div>
      <div style={{ height: '80px', position: 'relative', width: '100%', maxWidth: '100%', overflow: 'hidden', minWidth: 0 }}>
        <Sparkline data={data.history} width={600} height={80} color={THEME.primary[400]} style={{ width: '100%', height: '80px' }} />
        {/* threshold lines */}
        <div style={{ position: 'absolute', top: '20%', left: 0, right: 0, borderTop: `1px dashed ${THEME.red[400]}40`, pointerEvents: 'none' }}>
          <span style={{ position: 'absolute', right: 0, top: '-14px', fontFamily: THEME.font.mono, fontSize: '9px', color: THEME.red[400] }}>+σ</span>
        </div>
        <div style={{ position: 'absolute', top: '80%', left: 0, right: 0, borderTop: `1px dashed ${THEME.red[400]}40`, pointerEvents: 'none' }}>
          <span style={{ position: 'absolute', right: 0, top: '-14px', fontFamily: THEME.font.mono, fontSize: '9px', color: THEME.red[400] }}>-σ</span>
        </div>
      </div>
    </Card>
  );
};

const verdictColor = (label) => ({ EXECUTE: 'primary', REJECT: 'red', DEFER: 'amber', CHALLENGE: 'purple', WATCHLIST: 'blue' }[label] || 'muted');
const surfaceIcon = (s) => ({ crypto: '₿', ibkr: '📊', ibkr_prediction: '◈', polymarket: '◎' }[s] || '·');

const PackageLegRow = ({ leg }) => (
  <div style={{
    padding: '10px', borderRadius: '6px', background: THEME.bg.elevated,
    border: `1px solid ${THEME.border.subtle}`,
  }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '10px', alignItems: 'flex-start' }}>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.primary, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {surfaceIcon(leg.surface)} {leg.displayName || leg.instrument}
        </div>
        <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.muted, marginTop: '2px' }}>
          {leg.surface} · {leg.directPairRole || leg.role || roleLabel('', leg.surface)} · {leg.direction || leg.dir || 'pending'}
          {leg.repeatCount > 1 ? ` · seen ${leg.repeatCount} scans` : ''}
        </div>
        {(leg.slug || leg.endDate) && (
          <div style={{ fontFamily: THEME.font.mono, fontSize: '10px', color: THEME.text.faint, marginTop: '3px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {leg.slug || leg.instrument}{leg.endDate ? ` · resolves ${formatEventDate(leg.endDate)}` : ''}
          </div>
        )}
      </div>
      <div style={{ textAlign: 'right', flexShrink: 0 }}>
        {leg.label && <Badge color={verdictColor(leg.label)}>{leg.label}</Badge>}
        <MonoText style={{ display: 'block', fontSize: '11px', marginTop: '4px', color: numberOr(leg.estPnl) < 0 ? THEME.red[400] : THEME.primary[400] }}>
          {leg.estPnl
            ? `${leg.estPnl} $/$`
            : (hasExternalProxyPrice(leg)
              ? `proxy ${leg.externalProxySymbol} $${Number(leg.externalProxyLastPrice).toFixed(2)}`
              : (leg.pricingStatusLabel || pricingStatusLabel(leg.pricingStatus) || 'watchlist'))}
        </MonoText>
        {hasExternalProxyPrice(leg) && (
          <MonoText style={{ display: 'block', fontSize: '10px', marginTop: '2px', color: THEME.text.faint }}>
            {proxySourceLabel(leg.externalProxySource, leg.externalProxyStale)}
          </MonoText>
        )}
      </div>
    </div>
    {hasExternalProxyPrice(leg) && (
      <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.muted, marginTop: '6px', lineHeight: 1.35 }}>
        IBKR identified the event contract; external proxy mark is {leg.externalProxyTitle || leg.externalProxySymbol}. {proxyMarkMeta(leg)}
      </div>
    )}
    {leg.reason && (
      <div style={{ fontFamily: THEME.font.mono, fontSize: '10px', color: THEME.text.muted, marginTop: '6px' }}>
        reason: {leg.reasonLabel || pricingStatusLabel(leg.reason)}
      </div>
    )}
  </div>
);

const PackageBundlePanel = ({ bundle, direction }) => {
  const directLegs = bundle?.directLegs || [];
  const proxyLegs = bundle?.proxyLegs || [];
  const status = bundle?.label || 'PENDING';
  return (
    <Card glow>
      <SectionLabel>Research Legs Snapshot</SectionLabel>
      {bundle ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginTop: '4px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', alignItems: 'flex-start' }}>
            <div>
              <div style={{ fontFamily: THEME.font.heading, fontSize: '22px', fontWeight: 800, color: THEME.text.primary }}>
                {String(bundle.direction || direction || 'no_signal').replace('_', ' ')}
              </div>
              <div style={{ fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.muted, marginTop: '3px' }}>
                Research-only venue legs. The mock contract above is the main product surface.
              </div>
            </div>
            <Badge color={verdictColor(status)}>{status}</Badge>
          </div>
          {bundle.reason && (
            <div style={{ fontFamily: THEME.font.mono, fontSize: '11px', color: THEME.text.muted, padding: '8px 10px', borderRadius: '6px', background: THEME.bg.elevated }}>
              package verdict: {bundle.reason}{bundle.repeatCount > 1 ? ` · ${bundle.repeatCount} scan rows collapsed` : ''}
            </div>
          )}
          <div>
            <div style={{ fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.secondary, fontWeight: 700, marginBottom: '6px' }}>
              Research watchlist legs
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {directLegs.length ? directLegs.map((leg, i) => <PackageLegRow key={`${leg.id || leg.instrument}-d-${i}`} leg={leg} />) : (
                <div style={{ fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.muted, padding: '9px 10px', borderRadius: '6px', background: THEME.bg.elevated }}>
                  {bundle.directBlockedSummary || 'No venue research leg is currently promoted into the mock contract.'}
                </div>
              )}
            </div>
          </div>
          <div>
            <div style={{ fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.secondary, fontWeight: 700, marginBottom: '6px' }}>
              Proxy legs
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {proxyLegs.length ? proxyLegs.map((leg, i) => <PackageLegRow key={`${leg.id || leg.instrument}-p-${i}`} leg={leg} />) : (
                <div style={{ fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.muted, padding: '9px 10px', borderRadius: '6px', background: THEME.bg.elevated }}>
                  No proxy leg routed for this signal. BTC/ETH are only miner-margin proxies on electricity-expensive signals; IBKR stocks are equity proxies, not direct claims.
                </div>
              )}
            </div>
          </div>
        </div>
      ) : (
        <div style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.muted, marginTop: '12px' }}>
          No package legs have reached the judge yet.
        </div>
      )}
    </Card>
  );
};

const PrimaryExposurePanel = ({ exposure }) => (
  <Card glow>
    <SectionLabel>Spread Exposure Package</SectionLabel>
    {exposure ? (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', marginTop: '4px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px' }}>
          <div>
            <div style={{ fontFamily: THEME.font.heading, fontSize: '26px', fontWeight: 800, color: THEME.text.primary }}>
              {exposure.displayName || exposure.instrument}
            </div>
            <div style={{ fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.muted, marginTop: '2px' }}>
              {surfaceIcon(exposure.surface)} {exposure.surface} · {exposure.role}
            </div>
            {(exposure.slug || exposure.endDate) && (
              <div style={{ fontFamily: THEME.font.mono, fontSize: '11px', color: THEME.text.faint, marginTop: '4px' }}>
                {exposure.slug || exposure.instrument}{exposure.endDate ? ` · resolves ${formatEventDate(exposure.endDate)}` : ''}
              </div>
            )}
          </div>
          <Badge color={exposure.direction === 'short' ? 'amber' : exposure.direction === 'long' ? 'primary' : 'muted'}>
            {exposure.direction}
          </Badge>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '6px' }}>
          {['1 Score electricity minus compute', '2 Build canonical package', '3 Select direct/proxy legs', '4 Judge then Arc wrap'].map((step, i) => (
            <div key={i} style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.muted, padding: '6px 8px', borderRadius: '6px', background: THEME.bg.elevated }}>
              {step}
            </div>
          ))}
        </div>
        {exposure.description && (
          <div style={{
            fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.secondary,
            lineHeight: 1.45, maxHeight: '52px', overflow: 'hidden',
          }}>
            {exposure.description}
          </div>
        )}
        {exposure.connection && (
          <div style={{
            fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.muted,
            lineHeight: 1.45, padding: '10px', borderRadius: '6px', background: THEME.bg.elevated,
          }}>
            {exposure.connection}
          </div>
        )}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
          {[
            { label: 'Notional', value: `${Number(exposure.sizing || 0).toFixed(2)} USDC`, color: THEME.text.primary },
            { label: 'Judge', value: exposure.verdict || 'pending', color: verdictColor(exposure.verdict) === 'red' ? THEME.red[400] : THEME.primary[400] },
            { label: 'Arc job', value: exposure.jobId ? `#${exposure.jobId}` : exposure.jobStatus || 'not wrapped', color: THEME.amber[400] },
            { label: 'Est. edge', value: exposure.estPnl ? `${exposure.estPnl} $/$` : '-', color: THEME.primary[400] },
          ].map((item, i) => (
            <div key={i} style={{ padding: '10px', borderRadius: '6px', background: THEME.bg.elevated }}>
              <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.muted }}>{item.label}</div>
              <MonoText style={{ fontSize: '15px', fontWeight: 700, color: item.color }}>{item.value}</MonoText>
            </div>
          ))}
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: '2px' }}>
          <span style={{ fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.muted }}>Arc status</span>
          <Badge color={exposure.jobStatus === 'completed' || exposure.jobStatus === 'wrapped' ? 'primary' : 'amber'}>
            {exposure.jobStatus || 'pending'}
          </Badge>
        </div>
      </div>
    ) : (
      <div style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.muted, marginTop: '12px' }}>
        No package leg has passed through the judge yet.
      </div>
    )}
  </Card>
);

const CandidatesPanel = ({ candidates, title = 'Liquid Proxy Legs', emptyText = 'No active liquid proxy legs.' }) => (
  <Card>
    <SectionLabel>{title}</SectionLabel>
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '12px' }}>
      {candidates.length === 0 && (
        <div style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.muted }}>
          {emptyText}
        </div>
      )}
      {candidates.slice(0, 5).map((c, i) => (
        <div key={i} style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px',
          padding: '10px 12px', borderRadius: '8px', background: THEME.bg.elevated,
        }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', minWidth: 0 }}>
            <span style={{ fontSize: '16px' }}>{surfaceIcon(c.surface)}</span>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.primary, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {c.displayName || c.instrument}
              </div>
              <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.muted }}>
                {c.surface} · {c.directPairRole || c.role || roleLabel('', c.surface)} · {c.dir || c.direction || 'pending'}
                {c.repeatCount > 1 ? ` · seen ${c.repeatCount} scans` : ''}
              </div>
              {(c.slug || c.endDate) && (
                <div style={{ fontFamily: THEME.font.mono, fontSize: '10px', color: THEME.text.faint, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {c.slug || c.instrument}{c.endDate ? ` · resolves ${formatEventDate(c.endDate)}` : ''}
                </div>
              )}
              {c.description && (
                <div style={{
                  fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.muted,
                  lineHeight: 1.35, marginTop: '4px', display: '-webkit-box',
                  WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden',
                }}>
                  {c.description}
                </div>
              )}
              {c.connection && (
                <div style={{ fontFamily: THEME.font.body, fontSize: '10px', color: THEME.text.faint, lineHeight: 1.35, marginTop: '4px' }}>
                  {c.connection}
                </div>
              )}
              {c.reason && (
                <div style={{ fontFamily: THEME.font.mono, fontSize: '10px', color: THEME.text.muted, marginTop: '4px' }}>
                  reason: {c.reasonLabel || pricingStatusLabel(c.reason)}
                </div>
              )}
            </div>
          </div>
          <div style={{ textAlign: 'right', flexShrink: 0, display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '4px' }}>
            {c.label && <Badge color={verdictColor(c.label)}>{c.label}</Badge>}
            <MonoText style={{ fontSize: '12px' }}>
              {c.estPnl
                ? `${c.estPnl} $/$`
                : (hasExternalProxyPrice(c)
                  ? `proxy ${c.externalProxySymbol} $${Number(c.externalProxyLastPrice).toFixed(2)}`
                  : (c.pricingStatusLabel || pricingStatusLabel(c.pricingStatus) || 'watchlist'))}
            </MonoText>
            {hasExternalProxyPrice(c) && (
              <div style={{ fontFamily: THEME.font.mono, fontSize: '10px', color: THEME.text.faint }}>
                {proxySourceLabel(c.externalProxySource, c.externalProxyStale)}
              </div>
            )}
            <div style={{ fontFamily: THEME.font.mono, fontSize: '10px', color: THEME.text.muted }}>{c.sizing} USDC</div>
          </div>
        </div>
      ))}
    </div>
  </Card>
);

const mockContractStorageKey = (proposal = {}) => (
  `botozen:mock-contract:${proposal.proposal_id || proposal.reference_package_id || proposal.instrument_name || 'current'}`
);

const buildMockTicket = (proposal, construction, status = 'open') => ({
  status,
  proposalId: proposal?.proposal_id || '',
  instrumentName: proposal?.instrument_name || 'Compute/energy mock contract',
  enteredAt: Date.now(),
  entryNotional: Number(construction?.hedge_notional_usdc || 0),
  entryCircleAsk: Number(construction?.circle_testnet_usdc_request || 0),
  entryLegs: (construction?.weighted_legs || []).map(leg => ({
    slug: leg.slug,
    side: leg.side,
    weight: Number(leg.weight || 0),
    units: Number(leg.units || 0),
    entryPrice: Number(leg.last_price || 0),
    description: leg.description || '',
    sellReason: leg.sell_reason || '',
  })),
});

const computeMockPnl = (ticket, weightedLegs) => {
  if (!ticket?.entryLegs?.length) {
    return { total: 0, pct: 0, legs: [], worst: null, isUnprofitable: false };
  }
  const liveBySlug = new Map((weightedLegs || []).map(leg => [leg.slug, leg]));
  const legs = ticket.entryLegs.map(entry => {
    const live = liveBySlug.get(entry.slug) || {};
    const currentPrice = Number(live.last_price || entry.entryPrice || 0);
    const entryPrice = Number(entry.entryPrice || currentPrice || 0);
    const units = Number(entry.units || live.units || 0);
    const pnl = entry.side === 'short'
      ? (entryPrice - currentPrice) * units
      : (currentPrice - entryPrice) * units;
    return {
      ...entry,
      ...live,
      entryPrice,
      currentPrice,
      units,
      pnl,
      movePct: entryPrice ? ((currentPrice - entryPrice) / entryPrice) * 100 : 0,
    };
  });
  const total = legs.reduce((sum, leg) => sum + leg.pnl, 0);
  const entryNotional = Number(ticket.entryNotional || 0) || 1;
  const worst = legs.length ? [...legs].sort((a, b) => a.pnl - b.pnl)[0] : null;
  return {
    total,
    pct: (total / entryNotional) * 100,
    legs,
    worst,
    isUnprofitable: total < -Math.max(1, entryNotional * 0.002),
  };
};

const useMockContractTicket = (proposal, construction, weightedLegs) => {
  const key = React.useMemo(() => mockContractStorageKey(proposal), [proposal?.proposal_id, proposal?.instrument_name]);
  const [ticket, setTicket] = React.useState(null);

  React.useEffect(() => {
    try {
      const raw = window.localStorage.getItem(key);
      setTicket(raw ? JSON.parse(raw) : null);
    } catch (_err) {
      setTicket(null);
    }
  }, [key]);

  const saveTicket = React.useCallback((next) => {
    setTicket(next);
    try {
      if (next) window.localStorage.setItem(key, JSON.stringify(next));
      else window.localStorage.removeItem(key);
    } catch (_err) {
      /* local demo state is best-effort only */
    }
  }, [key]);

  const buy = React.useCallback(() => saveTicket(buildMockTicket(proposal, construction, 'open')), [proposal, construction, saveTicket]);
  const monitor = React.useCallback(() => saveTicket(buildMockTicket(proposal, construction, 'watching')), [proposal, construction, saveTicket]);
  const sell = React.useCallback(() => {
    const marked = computeMockPnl(ticket, weightedLegs);
    saveTicket({
      ...ticket,
      status: 'closed',
      exitedAt: Date.now(),
      exitPnl: marked.total,
      exitPct: marked.pct,
      exitReason: marked.worst?.sell_reason || marked.worst?.sellReason || 'Closed from dashboard mock monitor.',
    });
  }, [ticket, weightedLegs, saveTicket]);
  const reset = React.useCallback(() => saveTicket(null), [saveTicket]);

  return { ticket, marked: computeMockPnl(ticket, weightedLegs), buy, monitor, sell, reset };
};

const MockContractSummaryPanel = ({ proposal }) => {
  const construction = proposal?.outputs?.mock_hedge_construction || {};
  const sourceSummary = quoteSourceSummary(construction.quote_sources || []);
  const score = Number(construction.entry_signal_score ?? construction.profitability_score ?? 0);
  const label = construction.recommendation_label || (construction.recommended_action === 'BUY_CONTRACT' ? 'Hedge now' : 'Monitor');
  const reason = construction.recommendation_reason || 'Recommendation refreshes from the latest spread, quote, and leg state.';
  const judgeVerdict = construction.judge_verdict || {};
  const color = construction.recommended_action === 'BUY_CONTRACT' ? THEME.primary[400] : THEME.amber[400];
  return (
    <Card glow>
      <SectionLabel>Mock Contract Control</SectionLabel>
      {proposal ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div>
            <div style={{ fontFamily: THEME.font.heading, fontSize: '22px', color: THEME.text.primary, fontWeight: 800, lineHeight: 1.15 }}>
              {proposal.instrument_name || 'Compute/energy hedge contract'}
            </div>
            <div style={{ fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.muted, marginTop: '4px' }}>
              Real-price mock · {sourceSummary || 'public quotes'} · updates with backend refresh
            </div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
            <div style={{ padding: '10px', borderRadius: '6px', background: THEME.bg.elevated }}>
              <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.muted }}>Notional</div>
              <MonoText style={{ fontSize: '18px', fontWeight: 800 }}>{Number(construction.hedge_notional_usdc || 0).toLocaleString(undefined, { style: 'currency', currency: 'USD' })}</MonoText>
            </div>
            <div style={{ padding: '10px', borderRadius: '6px', background: THEME.bg.elevated }}>
              <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.muted }}>Circle ask</div>
              <MonoText style={{ fontSize: '18px', fontWeight: 800, color: THEME.amber[400] }}>
                {Number(construction.circle_testnet_usdc_request || 0).toLocaleString()} USDC
              </MonoText>
            </div>
          </div>
          <div style={{ padding: '10px', borderRadius: '6px', background: `${color}12`, border: `1px solid ${color}30` }}>
            <div style={{ fontFamily: THEME.font.mono, fontSize: '12px', color, fontWeight: 800 }}>
              Recommended: {label}
            </div>
            <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.muted, lineHeight: 1.35, marginTop: '4px' }}>
              Edge strength {Math.round(score)}/100 · {reason}
            </div>
            {construction.decision_basis_hash && (
              <div style={{ fontFamily: THEME.font.mono, fontSize: '10px', color: THEME.text.faint, lineHeight: 1.35, marginTop: '5px' }}>
                decision refresh: {construction.decision_basis_hash}
              </div>
            )}
            {judgeVerdict.label && (
              <div style={{ fontFamily: THEME.font.mono, fontSize: '10px', color: judgeVerdict.label === 'EXECUTE' ? THEME.primary[400] : THEME.amber[400], lineHeight: 1.35, marginTop: '5px' }}>
                judge: {judgeVerdict.label}/{judgeVerdict.reason_code || 'checked'}
              </div>
            )}
            <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.muted, lineHeight: 1.35, marginTop: '5px' }}>
              Buy freezes a local entry ticket only; Arc stays gated by judge.classify().
            </div>
          </div>
        </div>
      ) : (
        <div style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.muted }}>
          Waiting for priced public hedge legs.
        </div>
      )}
    </Card>
  );
};

const SyntheticInstrumentPanel = ({ proposal }) => {
  if (!proposal) return null;
  const hedge = proposal.outputs?.priced_hedge_basket || [];
  const actions = proposal.outputs?.agent_next_actions || [];
  const structure = proposal.structure || {};
  const inputs = proposal.inputs || {};
  const searchPlan = proposal.outputs?.agent_search_plan || [];
  const mockConstruction = proposal.outputs?.mock_hedge_construction || null;
  const weightedLegs = mockConstruction?.weighted_legs || [];
  const tooling = mockConstruction?.agent_tooling || [];
  const { ticket, marked, buy, monitor, sell, reset } = useMockContractTicket(proposal, mockConstruction, weightedLegs);
  const fmtMoney = value => `$${Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
  const fmtPct = value => `${Number(value || 0).toFixed(2)}%`;
  const monitorColor = marked.isUnprofitable ? THEME.red[400] : marked.total > 0 ? THEME.primary[400] : THEME.amber[400];
  return (
    <Card glow style={{ marginBottom: '16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', alignItems: 'flex-start', marginBottom: '12px' }}>
        <div style={{ minWidth: 0 }}>
          <SectionLabel>Dynamic Mock Contract</SectionLabel>
          <div style={{ fontFamily: THEME.font.heading, fontSize: '22px', fontWeight: 800, color: THEME.text.primary, marginTop: '3px', overflowWrap: 'anywhere' }}>
            {proposal.instrument_name || 'Compute/energy spread note'}
          </div>
          <div style={{ fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.muted, marginTop: '3px' }}>
            {proposal.proposal_type || 'compute receivable hedge note'} · {proposal.region || 'multi-region'}
          </div>
        </div>
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          <Badge color="primary">LIVE-PRICED MOCK</Badge>
          <Badge color="amber">LOCAL TICKET</Badge>
        </div>
      </div>
      <div style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.secondary, lineHeight: 1.45, marginBottom: '12px' }}>
        {proposal.thesis}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '10px' }}>
        <div style={{ padding: '10px', borderRadius: '6px', background: THEME.bg.elevated }}>
          <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.muted, marginBottom: '5px' }}>Real-world inputs</div>
          <div style={{ fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.secondary, lineHeight: 1.4 }}>
            {(inputs.energy_stack || []).join(', ') || 'regional power mix'}
          </div>
          <MonoText style={{ display: 'block', fontSize: '11px', marginTop: '6px', color: THEME.text.faint }}>
            z={Number(inputs.z || proposal.z || 0).toFixed(2)} · elec ${Number(inputs.electricity_per_mwh || 0).toFixed(2)}/MWh · compute ${Number(inputs.compute_per_gpu_hr || 0).toFixed(4)}/GPU-hr
          </MonoText>
        </div>
        <div style={{ padding: '10px', borderRadius: '6px', background: THEME.bg.elevated }}>
          <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.muted, marginBottom: '5px' }}>Securitization shape</div>
          <div style={{ fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.secondary, lineHeight: 1.4 }}>
            {structure.securitization_style || 'synthetic reference package'}
          </div>
          <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.muted, lineHeight: 1.35, marginTop: '6px' }}>
            {structure.settlement_rail || 'Judge then Arc wrap'}
          </div>
        </div>
        <div style={{ padding: '10px', borderRadius: '6px', background: THEME.bg.elevated }}>
          <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.muted, marginBottom: '5px' }}>Priced hedge basket</div>
          <div style={{ fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.secondary, lineHeight: 1.45 }}>
            {hedge.length ? hedge.map(leg => `${leg.slug || leg.title}${leg.last_price ? ` ${Number(leg.last_price).toFixed(2)}${leg.currency ? ` ${leg.currency}` : ''}` : ''}`).slice(0, 3).join(', ') : 'needs live prices'}
          </div>
          <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.muted, lineHeight: 1.35, marginTop: '6px' }}>
            Sources: {quoteSourceSummary(mockConstruction?.quote_sources || []) || 'public quote adapter'}.
          </div>
        </div>
        <div style={{ padding: '10px', borderRadius: '6px', background: THEME.bg.elevated }}>
          <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.muted, marginBottom: '5px' }}>Agent action loop</div>
          <div style={{ fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.secondary, lineHeight: 1.4 }}>
            {mockConstruction?.recommendation_reason || mockConstruction?.profitability_note || actions[0] || 'Refresh quotes, monitor spread confirmation, then recommend buy or sell.'}
          </div>
          <div style={{ fontFamily: THEME.font.mono, fontSize: '11px', color: THEME.primary[400], lineHeight: 1.35, marginTop: '6px' }}>
            {mockConstruction?.recommendation_label
              ? `agent says: ${mockConstruction.recommendation_label.toLowerCase()}`
              : (mockConstruction?.recommended_action === 'BUY_CONTRACT' ? 'agent says: hedge now' : 'agent says: monitor until edge improves')}
          </div>
          {mockConstruction?.judge_verdict?.label && (
            <div style={{ fontFamily: THEME.font.mono, fontSize: '10px', color: THEME.text.faint, lineHeight: 1.35, marginTop: '4px' }}>
              spread judge: {mockConstruction.judge_verdict.label}/{mockConstruction.judge_verdict.reason_code || 'checked'}
            </div>
          )}
        </div>
      </div>
      {mockConstruction && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '10px', marginTop: '10px' }}>
          <div style={{ padding: '10px', borderRadius: '6px', background: THEME.bg.elevated, border: `1px solid ${THEME.primary[400]}20` }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'flex-start', marginBottom: '8px' }}>
              <div>
                <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.muted, marginBottom: '3px' }}>Mock hedge construction</div>
                <div style={{ fontFamily: THEME.font.heading, fontSize: '18px', color: THEME.text.primary, fontWeight: 800 }}>
                  {fmtMoney(mockConstruction.hedge_notional_usdc)} notional
                </div>
              </div>
              <Badge color="amber">TESTNET MOCK</Badge>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginBottom: '8px' }}>
              {[
                ['GPU-hours', Number(mockConstruction.demo_gpu_hours || 0).toLocaleString()],
                ['Receivable', fmtMoney(mockConstruction.receivable_usdc)],
                ['Power cost', fmtMoney(mockConstruction.estimated_power_cost_usdc)],
                ['Margin', fmtMoney(mockConstruction.estimated_compute_margin_usdc)],
              ].map(([label, value]) => (
                <div key={label} style={{ padding: '7px', borderRadius: '6px', background: THEME.bg.surface }}>
                  <div style={{ fontFamily: THEME.font.body, fontSize: '10px', color: THEME.text.muted }}>{label}</div>
                  <div style={{ fontFamily: THEME.font.mono, fontSize: '12px', color: THEME.text.primary, marginTop: '2px' }}>{value}</div>
                </div>
              ))}
            </div>
            <div style={{ padding: '9px', borderRadius: '6px', background: THEME.amber[400] + '10', border: `1px solid ${THEME.amber[400]}25` }}>
              <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.muted }}>Circle test USDC request</div>
              <div style={{ fontFamily: THEME.font.heading, fontSize: '20px', color: THEME.amber[400], fontWeight: 800 }}>
                {fmtMoney(mockConstruction.circle_testnet_usdc_request)}
              </div>
              <div style={{ fontFamily: THEME.font.body, fontSize: '10px', color: THEME.text.muted, lineHeight: 1.35, marginTop: '3px' }}>
                Hedge + liquidity buffer + Arc settlement buffer. No transfer before EXECUTE.
              </div>
            </div>
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginTop: '10px' }}>
              <GlowButton size="sm" onClick={buy}>▸ Buy Contract</GlowButton>
              <GlowButton size="sm" variant="secondary" onClick={monitor}>◎ Monitor Price</GlowButton>
              {ticket?.status === 'open' && (
                <GlowButton size="sm" variant="secondary" onClick={sell} style={{ color: THEME.red[400], borderColor: THEME.red[400] + '40' }}>□ Sell Mock</GlowButton>
              )}
              {ticket && (
                <GlowButton size="sm" variant="secondary" onClick={reset}>↺ Reset</GlowButton>
              )}
            </div>
            {ticket && (
              <div style={{
                marginTop: '10px',
                padding: '10px',
                borderRadius: '6px',
                background: monitorColor + '12',
                border: `1px solid ${monitorColor}35`,
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '10px', alignItems: 'center' }}>
                  <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.muted }}>
                    {ticket.status === 'closed' ? 'Closed mock ticket' : ticket.status === 'watching' ? 'Monitoring from entry marks' : 'Open mock ticket'}
                  </div>
                  <MonoText style={{ color: monitorColor, fontWeight: 800 }}>
                    {fmtMoney(ticket.status === 'closed' ? ticket.exitPnl : marked.total)} · {fmtPct(ticket.status === 'closed' ? ticket.exitPct : marked.pct)}
                  </MonoText>
                </div>
                <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.secondary, lineHeight: 1.35, marginTop: '6px' }}>
                  {marked.isUnprofitable && marked.worst
                    ? `Unprofitable because ${marked.worst.slug} moved against the ${marked.worst.side} leg: ${fmtMoney(marked.worst.entryPrice)} entry to ${fmtMoney(marked.worst.currentPrice)} now. ${marked.worst.sell_reason || marked.worst.sellReason || ''}`
                    : ticket.status === 'closed'
                      ? (ticket.exitReason || 'Ticket closed.')
                      : 'Tracking live leg marks against the frozen entry prices. Sell appears when a ticket is open.'}
                </div>
              </div>
            )}
          </div>
          <div style={{ padding: '10px', borderRadius: '6px', background: THEME.bg.elevated }}>
            <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.muted, marginBottom: '8px' }}>Real-price mock weights</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {weightedLegs.slice(0, 7).map((leg, i) => (
                <div key={`${leg.slug}-${i}`} style={{
                  display: 'grid',
                  gridTemplateColumns: '58px minmax(0, 1fr) 92px',
                  gap: '9px',
                  alignItems: 'start',
                  padding: '8px',
                  borderRadius: '6px',
                  background: THEME.bg.surface,
                }}>
                  <Badge color={leg.side === 'short' ? 'amber' : 'primary'}>{leg.side}</Badge>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.primary, fontWeight: 800, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {leg.slug} · {Number(leg.weight || 0).toLocaleString(undefined, { style: 'percent', maximumFractionDigits: 1 })}
                    </div>
                    <div style={{ fontFamily: THEME.font.mono, fontSize: '10px', color: THEME.text.muted }}>
                      {Number(leg.units || 0).toLocaleString(undefined, { maximumFractionDigits: 6 })} units @ {fmtMoney(leg.last_price)}
                    </div>
                    <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.secondary, lineHeight: 1.35, marginTop: '4px' }}>
                      {leg.description}
                    </div>
                    <div style={{ fontFamily: THEME.font.body, fontSize: '10px', color: THEME.text.muted, lineHeight: 1.35, marginTop: '3px' }}>
                      Driver: {leg.risk_driver} · source: {leg.source || 'public quote'}
                    </div>
                  </div>
                  <div style={{ fontFamily: THEME.font.mono, fontSize: '11px', color: THEME.text.secondary, textAlign: 'right', whiteSpace: 'nowrap' }}>
                    {fmtMoney(leg.notional_usdc)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
      {(tooling.length > 0 || searchPlan.length > 0) && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '10px', marginTop: '10px' }}>
          {tooling.length > 0 && (
            <div style={{ padding: '10px', borderRadius: '6px', background: THEME.bg.elevated }}>
              <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.muted, marginBottom: '8px' }}>Agent tools</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '7px' }}>
                {tooling.map((tool, i) => (
                  <div key={`${tool.name}-${i}`} style={{ display: 'grid', gridTemplateColumns: '92px 1fr', gap: '8px', alignItems: 'start' }}>
                    <Badge color={i === 0 ? 'primary' : i === 1 ? 'blue' : 'amber'}>{tool.name}</Badge>
                    <div>
                      <div style={{ fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.primary, fontWeight: 700 }}>{tool.uses}</div>
                      <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.muted, lineHeight: 1.35 }}>{tool.job}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          {searchPlan.length > 0 && (
            <div style={{ padding: '10px', borderRadius: '6px', background: THEME.bg.elevated }}>
              <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.muted, marginBottom: '8px' }}>Agent scouting queue</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '7px' }}>
                {searchPlan.slice(0, 4).map((item, i) => (
                  <div key={`${item.surface}-${i}`} style={{ paddingBottom: i === Math.min(searchPlan.length, 4) - 1 ? 0 : '7px', borderBottom: i === Math.min(searchPlan.length, 4) - 1 ? 'none' : `1px solid ${THEME.border.subtle}` }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'center' }}>
                      <div style={{ fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.primary, fontWeight: 700 }}>{item.target}</div>
                      <Badge color="blue">{item.surface}</Badge>
                    </div>
                    <div style={{ fontFamily: THEME.font.mono, fontSize: '10px', color: THEME.text.muted, lineHeight: 1.35, marginTop: '4px', overflowWrap: 'anywhere' }}>
                      {item.query}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </Card>
  );
};

const OraclePanel = ({ oracle }) => (
  <Card>
    <SectionLabel>Oracle Backtest — 280K Sources · 200 Languages</SectionLabel>
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginTop: '12px' }}>
      {[
        { label: 'News Sources', value: '280,000', color: THEME.text.primary },
        { label: 'Languages', value: '200', color: THEME.amber[400] },
        { label: 'AI-Infra WR', value: `${oracle.aiInfra.wr}%`, color: THEME.primary[400] },
        { label: 'AI-Infra PnL', value: `+${oracle.aiInfra.pnl.toFixed(3)}`, color: THEME.primary[400] },
        { label: 'Frontier Model WR', value: `${oracle.geopolitics.wr}%`, color: THEME.amber[400] },
        { label: 'Gate-Kept PnL', value: `+${oracle.gatePnl.toFixed(3)}`, color: THEME.primary[400] },
      ].map((item, i) => (
        <div key={i} style={{ padding: '10px', borderRadius: '6px', background: THEME.bg.elevated }}>
          <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.muted, marginBottom: '4px' }}>{item.label}</div>
          <MonoText style={{ fontSize: '16px', fontWeight: 700, color: item.color }}>{item.value}</MonoText>
        </div>
      ))}
    </div>
  </Card>
);

const DashboardPage = ({ refreshRate }) => {
  const data = useLiveData(refreshRate);
  const isMobile = useIsMobile(820);
  const isNarrow = useIsMobile(520);
  const construction = data.syntheticInstrument?.outputs?.mock_hedge_construction || {};
  const quoteSourceText = quoteSourceSummary(construction.quote_sources || []);
  const recommendation = construction.recommendation_label || (construction.recommended_action === 'BUY_CONTRACT' ? 'Hedge now' : 'Monitor');

  return (
    <div style={{ padding: isMobile ? '18px 14px 32px' : '24px 32px', maxWidth: '1200px', margin: '0 auto' }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: isMobile ? 'flex-start' : 'center',
        flexDirection: isMobile ? 'column' : 'row', gap: '12px', marginBottom: '24px',
      }}>
        <div>
          <h1 style={{ fontFamily: THEME.font.heading, fontSize: '28px', fontWeight: 800, color: THEME.text.primary, margin: 0, letterSpacing: 0 }}>
            Dashboard
          </h1>
          <p style={{ fontFamily: THEME.font.body, fontSize: '14px', color: THEME.text.muted, margin: '4px 0 0' }}>
            Canonical compute/energy spread packages · Arc Testnet
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', maxWidth: '100%' }}>
          <div style={{
            width: 8, height: 8, borderRadius: '50%', background: data.connection.status === 'live' ? THEME.primary[400] : THEME.amber[400],
            animation: 'pulse 2s ease infinite',
          }}></div>
          <MonoText style={{ fontSize: '12px', color: THEME.text.muted }}>
            {data.connection.status === 'live' ? 'Backend live' : 'Backend offline'} · Refresh: {(refreshRate / 1000).toFixed(1)}s
          </MonoText>
        </div>
      </div>

      {/* Top mock contract stats */}
      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? (isNarrow ? '1fr' : 'repeat(2, minmax(0, 1fr))') : 'repeat(4, 1fr)', gap: '12px', marginBottom: '16px' }}>
        <StatCard label="Mock Notional" value={construction.hedge_notional_usdc ? `$${Number(construction.hedge_notional_usdc).toLocaleString()}` : 'Pending'} />
        <StatCard label="Circle Ask" value={construction.circle_testnet_usdc_request ? `${Number(construction.circle_testnet_usdc_request).toLocaleString()} USDC` : 'Pending'} color={THEME.amber[400]} />
        <StatCard label="Agent Recommendation" value={recommendation} color={construction.recommended_action === 'BUY_CONTRACT' ? THEME.primary[400] : THEME.amber[400]} />
        <StatCard label="Quote Source" value={quoteSourceText || 'Pending'} valueSize={16} />
      </div>

      {/* Signal + Candidates */}
      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '2fr 1fr', gap: '12px', marginBottom: '16px', alignItems: 'start' }}>
        <SignalPanel data={data} />
        <MockContractSummaryPanel proposal={data.syntheticInstrument} />
      </div>

      <SyntheticInstrumentPanel proposal={data.syntheticInstrument} />

      {/* Oracle */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '12px' }}>
        <OraclePanel oracle={data.oracleResults} />
      </div>
    </div>
  );
};

Object.assign(window, { DashboardPage, mapSnapshotToDashboardData, emptyDashboardData, derivePrimaryExposure, formatEventDate, roleLabel });
