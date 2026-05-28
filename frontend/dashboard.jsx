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
  spread: {
    elec: '0.00', compute: '0.0000', st: '0.0000',
    k: 0.5, kwh: 0.7, powerCost: '0.0000', powerSharePct: null,
    source: '', sourceStatus: '',
  },
  spreadFamilies: { families: [], archetypeScoreboard: [], primaryFamily: null, entryGatePass: false },
  proxyBaskets: { baskets: [], primaryBasket: null, entryGatePass: false },
  venueEvidence: { rows: [], summary: {}, guardrail: '' },
  telegramCampaign: { posts: [], total_posts: 0, posted_count: 0, pending_count: 0, status: 'READY_TO_POST' },
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
    status: 'UNKNOWN', statusLabel: 'Pending', note: '',
  },
  oracleResults: { status: 'NO_RECEIPTS', row_count: 0 },
  connection: { status, error, updatedAt: Date.now() },
});

const selectProxyBasketForDirection = (proxyBaskets, direction) => {
  const validation = proxyBaskets || {};
  if (validation.active_basket) {
    return {
      selected: validation.active_basket,
      entryGatePass: Boolean(validation.active_entry_gate_pass),
    };
  }
  const primary = validation.primary_basket || null;
  const baskets = Array.isArray(validation.baskets) ? [...validation.baskets] : [];
  if (primary && !baskets.some(basket => basket?.basket_id === primary.basket_id)) baskets.push(primary);
  const cleanDirection = String(direction || '').trim();
  const matched = cleanDirection && cleanDirection !== 'no_signal'
    ? baskets.find(basket => String(basket?.direction || '').trim() === cleanDirection)
    : null;
  const selected = matched || primary || baskets[0] || null;
  const entryGatePass = selected
    ? Boolean(selected.is_promotable || selected.status === 'PROMOTABLE')
    : Boolean(validation.entry_gate_pass);
  return { selected, entryGatePass };
};

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
  const selectedProxyBasket = selectProxyBasketForDirection(snapshot?.proxy_baskets, signal.direction || 'no_signal');
  const selectedProxy = selectedProxyBasket.selected || {};
  const selectedProxyTrailing = selectedProxy.trailing_returns || {};
  return {
    spread: {
      elec: numberOr(spreadLatest.electricity_per_mwh).toFixed(2),
      compute: numberOr(spreadLatest.compute_per_gpu_hr).toFixed(4),
      st: numberOr(spreadLatest.S_t).toFixed(4),
      k: numberOr(spreadLatest.k, 0.5),
      kwh: numberOr(spreadLatest.kwh_per_gpu_hr, 0.7),
      powerCost: numberOr(spreadLatest.power_cost_per_gpu_hr).toFixed(4),
      powerSharePct: spreadLatest.power_cost_share_pct === '' || spreadLatest.power_cost_share_pct === undefined
        ? (spreadLatest.power_cost_share === '' || spreadLatest.power_cost_share === undefined
          ? null
          : numberOr(spreadLatest.power_cost_share) * 100)
        : numberOr(spreadLatest.power_cost_share_pct),
      source: spreadLatest.electricity_source || '',
      sourceStatus: spreadLatest.electricity_source_status || '',
      baseElec: spreadLatest.electricity_base_per_mwh === '' || spreadLatest.electricity_base_per_mwh === undefined
        ? null
        : numberOr(spreadLatest.electricity_base_per_mwh, null),
      proxyMovePct: spreadLatest.electricity_proxy_weighted_return_pct === '' || spreadLatest.electricity_proxy_weighted_return_pct === undefined
        ? null
        : numberOr(spreadLatest.electricity_proxy_weighted_return_pct, null),
      proxySymbols: spreadLatest.electricity_proxy_symbols || [],
      proxyUsedQuotes: numberOr(spreadLatest.electricity_proxy_used_quotes, 0),
      eiaPeriod: spreadLatest.eia_period || '',
      computeSource: spreadLatest.compute_source || '',
      computeInstance: spreadLatest.compute_instance || '',
    },
    spreadFamilies: {
      entryGatePass: Boolean(snapshot?.spread_families?.entry_gate_pass),
      primaryFamily: snapshot?.spread_families?.primary_family || null,
      families: snapshot?.spread_families?.families || [],
      archetypeScoreboard: snapshot?.spread_families?.archetype_scoreboard || [],
      policy: snapshot?.spread_families?.policy || '',
      caveat: snapshot?.spread_families?.caveat || '',
      primarySource: snapshot?.spread_families?.primary_source || '',
      sourceStatus: snapshot?.spread_families?.source_status || '',
      indexCatalog: snapshot?.spread_families?.index_catalog || { electricity: [], compute: [] },
    },
    proxyBaskets: {
      entryGatePass: selectedProxyBasket.entryGatePass,
      primaryBasket: selectedProxyBasket.selected,
      baskets: snapshot?.proxy_baskets?.baskets || [],
      policy: snapshot?.proxy_baskets?.policy || '',
      caveat: snapshot?.proxy_baskets?.caveat || '',
      statusReason: snapshot?.proxy_baskets?.status_reason || '',
      fetchEnabled: Boolean(snapshot?.proxy_baskets?.fetch_enabled),
    },
    venueEvidence: {
      rows: snapshot?.venue_evidence?.rows || [],
      summary: snapshot?.venue_evidence?.summary || {},
      guardrail: snapshot?.venue_evidence?.guardrail || '',
    },
    telegramCampaign: snapshot?.telegram_campaign || { posts: [], total_posts: 0, posted_count: 0, pending_count: 0, status: 'READY_TO_POST' },
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
      totalDisplay: pnl.display_total || (hasReconciled ? `$${numberOr(pnl.total).toFixed(4)}` : 'No settled PnL'),
      winRate: numberOr(pnl.win_rate),
      trades: reconciledTrades,
      tradesDisplay: pnl.display_trades || (hasReconciled ? String(reconciledTrades) : '0 settled'),
      wrappedJobs,
      executes,
      hasReconciled,
      status: pnl.status || '',
      statusLabel: pnl.status_label || '',
      note: pnl.mark_to_market_note || '',
      spreadReplayStatus: pnl.spread_replay_status || '',
      spreadMarkChanges: numberOr(pnl.spread_mark_changes, 0),
      spreadRawObservations: numberOr(pnl.spread_raw_observations, 0),
      spreadCollapsedPolls: numberOr(pnl.spread_collapsed_polls, 0),
      proxyLatestSignal: selectedProxy.latest_signal || pnl.proxy_latest_signal || '',
      proxyReplayStatus: selectedProxy.status || pnl.proxy_replay_status || '',
      proxy5dReturnPct: selectedProxyTrailing['5d']?.return_pct === undefined
        ? ((pnl.proxy_5d_return_pct === '' || pnl.proxy_5d_return_pct === undefined || pnl.proxy_5d_return_pct === null) ? null : numberOr(pnl.proxy_5d_return_pct))
        : numberOr(selectedProxyTrailing['5d']?.return_pct),
      proxy1mReturnPct: selectedProxyTrailing['1m']?.return_pct === undefined
        ? ((pnl.proxy_1m_return_pct === '' || pnl.proxy_1m_return_pct === undefined || pnl.proxy_1m_return_pct === null) ? null : numberOr(pnl.proxy_1m_return_pct))
        : numberOr(selectedProxyTrailing['1m']?.return_pct),
    },
    oracleResults: snapshot?.oracle || { status: 'NO_RECEIPTS', row_count: 0 },
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
  const families = data.spreadFamilies?.families || [];
  const archetypes = data.spreadFamilies?.archetypeScoreboard || [];
  const primaryFamily = data.spreadFamilies?.primaryFamily || families[0] || null;
  const sourceLabel = data.spread.source === 'eia_plus_power_proxy'
    ? 'EIA anchor + public power/fuel proxy'
    : (data.spread.source === 'eia_retail_sales' ? 'EIA monthly retail anchor' : 'Source pending');
  const proxyLine = data.spread.baseElec && data.spread.proxyMovePct !== null && data.spread.proxyMovePct !== undefined
    ? `base $${Number(data.spread.baseElec).toFixed(2)} · proxy ${Number(data.spread.proxyMovePct) >= 0 ? '+' : ''}${Number(data.spread.proxyMovePct).toFixed(2)}%`
    : '';
  const powerShare = data.spread.powerSharePct;
  const powerShareWeak = powerShare !== null && powerShare !== undefined && Number(powerShare) < 2.5;
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
          <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.faint, marginTop: '3px' }}>
            {sourceLabel}{data.spread.sourceStatus ? ` · ${String(data.spread.sourceStatus).replaceAll('_', ' ')}` : ''}
          </div>
        </div>
        <Badge color={data.direction === 'compute_expensive' ? 'blue' : 'amber'}>
          {data.direction.replace('_', ' ')}
        </Badge>
      </div>
      <div style={{
        display: 'grid',
        gridTemplateColumns: isNarrow ? 'repeat(2, minmax(0, 1fr))' : 'repeat(5, minmax(0, 1fr))',
        gap: isNarrow ? '10px' : '16px',
        marginBottom: '20px',
        minWidth: 0,
      }}>
        <div>
          <div style={{ fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.muted }}>Electricity</div>
          <MonoText style={{ fontSize: '18px', fontWeight: 700, color: THEME.amber[400] }}>${data.spread.elec}/MWh</MonoText>
          {proxyLine && (
            <div style={{ fontFamily: THEME.font.body, fontSize: '10px', color: THEME.text.faint, lineHeight: 1.3, marginTop: '2px' }}>
              {proxyLine}
            </div>
          )}
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
          <div style={{ fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.muted }}>Power Share</div>
          <MonoText style={{ fontSize: '18px', fontWeight: 700, color: powerShareWeak ? THEME.amber[400] : THEME.primary[400] }}>
            {powerShare === null || powerShare === undefined ? '-' : `${Number(powerShare).toFixed(2)}%`}
          </MonoText>
          <div style={{ fontFamily: THEME.font.body, fontSize: '10px', color: THEME.text.faint, lineHeight: 1.3, marginTop: '2px' }}>
            ${data.spread.powerCost}/GPU-hr modeled power
          </div>
        </div>
        <div>
          <div style={{ fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.muted }}>Z-Score</div>
          <MonoText style={{ fontSize: '18px', fontWeight: 700, color: zColor }}>
            {data.z.toFixed(3)}
          </MonoText>
        </div>
      </div>
      {powerShareWeak && (
        <div style={{ padding: '9px 10px', borderRadius: '6px', background: `${THEME.amber[400]}10`, border: `1px solid ${THEME.amber[400]}25`, marginBottom: '12px' }}>
          <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.secondary, lineHeight: 1.4 }}>
            Energy materiality is weak in this live cloud mark. Treat the signal as compute-led unless the direction-matched proxy basket and direct event legs confirm the power thesis.
          </div>
        </div>
      )}
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
      {archetypes.length > 0 && (
        <div style={{ marginTop: '14px' }}>
          <div style={{ fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.muted, marginBottom: '7px' }}>
            Oil-style spread archetypes
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: isNarrow ? '1fr' : 'repeat(3, minmax(0, 1fr))', gap: '8px' }}>
            {archetypes.slice(0, 6).map(item => {
              const color = item.is_promotable ? THEME.primary[400] : (item.evidence_level === 'planned' ? THEME.text.faint : THEME.amber[400]);
              return (
                <div key={item.archetype_id} style={{ padding: '9px', borderRadius: '6px', background: THEME.bg.elevated, border: `1px solid ${THEME.border.subtle}`, minWidth: 0 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '6px', alignItems: 'flex-start' }}>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.primary, fontWeight: 800, overflowWrap: 'anywhere' }}>
                        {item.label}
                      </div>
                      <div style={{ fontFamily: THEME.font.body, fontSize: '10px', color: THEME.text.faint, lineHeight: 1.3, marginTop: '2px' }}>
                        {item.oil_analogy}
                      </div>
                    </div>
                    <MonoText style={{ fontSize: '10px', color, fontWeight: 800, textAlign: 'right' }}>
                      {String(item.replay_status || '').replaceAll('_', ' ')}
                    </MonoText>
                  </div>
                  <div style={{ fontFamily: THEME.font.mono, fontSize: '10px', color: THEME.text.faint, marginTop: '6px', overflowWrap: 'anywhere' }}>
                    {item.formula}
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '5px', marginTop: '7px' }}>
                    {[
                      ['z', Number(item.latest_z || 0).toFixed(2)],
                      ['trades', item.tested_trades || 0],
                      ['WR', `${Number(item.win_rate || 0).toFixed(0)}%`],
                    ].map(([label, value]) => (
                      <div key={label} style={{ padding: '5px', borderRadius: '5px', background: THEME.bg.surface }}>
                        <div style={{ fontFamily: THEME.font.body, fontSize: '9px', color: THEME.text.muted }}>{label}</div>
                        <MonoText style={{ fontSize: '10px', color: THEME.text.secondary }}>{value}</MonoText>
                      </div>
                    ))}
                  </div>
                  {item.evidence_level === 'planned' && (
                    <div style={{ fontFamily: THEME.font.body, fontSize: '10px', color: THEME.text.muted, lineHeight: 1.3, marginTop: '6px' }}>
                      needs: {(item.required_indexes || []).join(', ')}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
      {families.length > 0 && (
        <div style={{ marginTop: '14px' }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            gap: '10px', marginBottom: '8px',
          }}>
            <div>
              <div style={{ fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.muted }}>Spread-family replay</div>
              <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.faint, lineHeight: 1.35 }}>
                Walk-forward, no lookahead. Flat marks do not promote a buy signal.
                {data.spreadFamilies?.primarySource ? ` Source: ${String(data.spreadFamilies.primarySource).replaceAll('_', ' ')}.` : ''}
              </div>
            </div>
            {primaryFamily?.status && (
              <Badge color={primaryFamily.is_promotable ? 'primary' : 'amber'}>{String(primaryFamily.status).replaceAll('_', ' ')}</Badge>
            )}
          </div>
          <div style={{
            display: 'grid',
            gridTemplateColumns: isNarrow ? '1fr' : 'repeat(2, minmax(0, 1fr))',
            gap: '8px',
          }}>
            {families.slice(0, 4).map(family => (
              <div key={`${family.family_id}-${family.strategy_id || 'default'}`} style={{ padding: '9px', borderRadius: '6px', background: THEME.bg.elevated, border: `1px solid ${THEME.border.subtle}` }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'flex-start' }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.primary, fontWeight: 800, overflowWrap: 'anywhere' }}>
                      {family.label}
                    </div>
                    {family.strategy_label && (
                      <div style={{ fontFamily: THEME.font.body, fontSize: '10px', color: THEME.text.muted, marginTop: '2px' }}>
                        {family.strategy_label}
                      </div>
                    )}
                    <div style={{ fontFamily: THEME.font.mono, fontSize: '10px', color: THEME.text.faint, marginTop: '3px', overflowWrap: 'anywhere' }}>
                      {family.formula}
                    </div>
                  </div>
                  <MonoText style={{ fontSize: '11px', color: family.is_promotable ? THEME.primary[400] : THEME.amber[400], fontWeight: 800 }}>
                    {String(family.status || '').replaceAll('_', ' ')}
                  </MonoText>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '6px', marginTop: '8px' }}>
                  {[
                    ['z', Number(family.latest_z || 0).toFixed(2)],
                    ['trades', family.tested_trades || 0],
                    ['WR', `${Number(family.win_rate || 0).toFixed(0)}%`],
                  ].map(([label, value]) => (
                    <div key={label} style={{ padding: '6px', borderRadius: '6px', background: THEME.bg.surface }}>
                      <div style={{ fontFamily: THEME.font.body, fontSize: '9px', color: THEME.text.muted }}>{label}</div>
                      <MonoText style={{ fontSize: '11px', color: THEME.text.secondary }}>{value}</MonoText>
                    </div>
                  ))}
                </div>
                <div style={{ fontFamily: THEME.font.body, fontSize: '10px', color: THEME.text.muted, lineHeight: 1.35, marginTop: '6px' }}>
                  {family.status_reason}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
};

const ProxyBasketReplayPanel = ({ data }) => {
  const baskets = data.proxyBaskets?.baskets || [];
  const primary = data.proxyBaskets?.primaryBasket || baskets[0] || {};
  const isNarrow = useIsMobile(560);
  if (!primary || !Object.keys(primary).length) return null;
  const status = String(primary.status || 'MONITOR').replaceAll('_', ' ');
  const recommendation = String(primary.recommendation || 'MONITOR_ONLY').replaceAll('_', ' ');
  const latestSignal = String(primary.latest_signal || 'MONITOR').replaceAll('_', ' ');
  const signalColor = primary.latest_signal === 'SELL'
    ? THEME.red[400]
    : (primary.latest_signal === 'BUY' ? THEME.primary[400] : THEME.amber[400]);
  const trailing = primary.trailing_returns || {};
  const ret = (label) => trailing[label]?.return_pct;
  const color = primary.is_promotable ? THEME.primary[400] : (primary.recommendation === 'SELL_OR_AVOID' ? THEME.red[400] : THEME.amber[400]);
  return (
    <Card glow>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '10px', alignItems: 'flex-start', marginBottom: '10px' }}>
        <div style={{ minWidth: 0 }}>
          <SectionLabel>Proxy Basket Replay</SectionLabel>
          <div style={{ fontFamily: THEME.font.heading, fontSize: '18px', color: THEME.text.primary, fontWeight: 800, lineHeight: 1.2, overflowWrap: 'anywhere' }}>
            {primary.label || 'Public proxy basket'}
          </div>
          <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.faint, marginTop: '3px', lineHeight: 1.35 }}>
            Yahoo/IBKR/crypto close-history validation for the liquid expression, separate from the spread-index replay.
          </div>
        </div>
        <Badge color={primary.is_promotable ? 'primary' : (primary.recommendation === 'SELL_OR_AVOID' ? 'red' : 'amber')}>{status}</Badge>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: isNarrow ? 'repeat(2, minmax(0, 1fr))' : 'repeat(3, minmax(0, 1fr))', gap: '8px', marginBottom: '10px' }}>
        {[
          ['Signal', latestSignal, signalColor],
          ['5d', ret('5d') === undefined ? '-' : `${Number(ret('5d') || 0).toFixed(2)}%`, Number(ret('5d') || 0) >= 0 ? THEME.primary[400] : THEME.red[400]],
          ['1m', ret('1m') === undefined ? '-' : `${Number(ret('1m') || 0).toFixed(2)}%`, Number(ret('1m') || 0) >= 0 ? THEME.primary[400] : THEME.red[400]],
          ['Total', `${Number(primary.total_return_pct || 0).toFixed(2)}%`, Number(primary.total_return_pct || 0) >= 0 ? THEME.primary[400] : THEME.red[400]],
          ['WR', `${Number(primary.win_rate || 0).toFixed(0)}%`, THEME.text.secondary],
          ['Max DD', `${Number(primary.max_drawdown_pct || 0).toFixed(2)}%`, THEME.amber[400]],
        ].map(([label, value, itemColor]) => (
          <div key={label} style={{ padding: '8px', borderRadius: '6px', background: THEME.bg.elevated, minWidth: 0 }}>
            <div style={{ fontFamily: THEME.font.body, fontSize: '10px', color: THEME.text.muted }}>{label}</div>
            <MonoText style={{ fontSize: label === 'Signal' ? '11px' : '13px', color: itemColor, fontWeight: 800, overflowWrap: 'anywhere' }}>{value}</MonoText>
          </div>
        ))}
      </div>
      <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.secondary, lineHeight: 1.4, marginBottom: '8px' }}>
        {primary.signal_reason || primary.status_reason || data.proxyBaskets?.statusReason || 'Run proxy replay before promoting a syndicated basket.'}
        <span style={{ color: THEME.text.faint }}> Recommendation: {recommendation}.</span>
      </div>
      {baskets.length > 1 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
          {baskets.slice(1, 4).map(basket => (
            <div key={basket.basket_id} style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 54px 54px 62px', gap: '8px', alignItems: 'center', fontSize: '11px', color: THEME.text.muted }}>
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{basket.label}</span>
              <MonoText style={{ color: basket.latest_signal === 'SELL' ? THEME.red[400] : (basket.latest_signal === 'BUY' ? THEME.primary[400] : THEME.text.faint) }}>{basket.latest_signal || 'MONITOR'}</MonoText>
              <MonoText style={{ color: Number(basket.trailing_returns?.['5d']?.return_pct || 0) >= 0 ? THEME.primary[400] : THEME.red[400] }}>{Number(basket.trailing_returns?.['5d']?.return_pct || 0).toFixed(1)}%</MonoText>
              <MonoText style={{ color: basket.is_promotable ? THEME.primary[400] : THEME.text.faint }}>{Number(basket.total_return_pct || 0).toFixed(1)}%</MonoText>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
};

const SyndicatedInstrumentMenuPanel = ({ proposal }) => {
  const menu = proposal?.outputs?.syndicated_instrument_menu || [];
  if (!menu.length) return null;
  const signalColor = (signal) => signal === 'SELL' ? THEME.red[400] : (signal === 'BUY' ? THEME.primary[400] : THEME.amber[400]);
  const statusColor = (status) => status === 'PAPER_BUY_ONLY' || status === 'READY_FOR_JUDGE'
    ? 'primary'
    : (status === 'AVOID_OR_SELL' ? 'red' : 'amber');
  return (
    <Card glow style={{ marginBottom: '16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', alignItems: 'flex-start', marginBottom: '10px' }}>
        <div style={{ minWidth: 0 }}>
          <SectionLabel>Syndicated Instrument Menu</SectionLabel>
          <div style={{ fontFamily: THEME.font.heading, fontSize: '20px', color: THEME.text.primary, fontWeight: 800 }}>
            Spread-copying structures
          </div>
          <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.faint, marginTop: '3px', lineHeight: 1.35 }}>
            These are synthetic expressions of the compute/energy spread. They become asset-backed only after collateral is attached and the judge gate clears.
          </div>
        </div>
        <Badge color="amber">NOT ABS YET</Badge>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '8px' }}>
        {menu.slice(0, 5).map(item => {
          const trailing = item.trailing_returns || {};
          const ret5 = trailing['5d']?.return_pct;
          const ret1 = trailing['1m']?.return_pct;
          return (
            <div key={item.instrument_type} style={{ padding: '10px', borderRadius: '6px', background: THEME.bg.elevated, border: `1px solid ${THEME.border.subtle}`, minWidth: 0 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'flex-start', marginBottom: '6px' }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.primary, fontWeight: 800, lineHeight: 1.2, overflowWrap: 'anywhere' }}>
                    {item.title}
                  </div>
                  <div style={{ fontFamily: THEME.font.mono, fontSize: '10px', color: THEME.text.faint, marginTop: '3px' }}>
                    {item.spread_archetype} · {String(item.basket_direction || 'unmapped').replaceAll('_', ' ')}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '5px', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                  {item.direction_aligned && <Badge color="primary">ACTIVE</Badge>}
                  <Badge color={statusColor(item.status)}>{String(item.status || '').replaceAll('_', ' ')}</Badge>
                </div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '6px', marginBottom: '6px' }}>
                {[
                  ['Signal', item.latest_signal || 'MONITOR', signalColor(item.latest_signal)],
                  ['5d', ret5 === undefined ? '-' : `${Number(ret5 || 0).toFixed(1)}%`, Number(ret5 || 0) >= 0 ? THEME.primary[400] : THEME.red[400]],
                  ['1m', ret1 === undefined ? '-' : `${Number(ret1 || 0).toFixed(1)}%`, Number(ret1 || 0) >= 0 ? THEME.primary[400] : THEME.red[400]],
                ].map(([label, value, color]) => (
                  <div key={label} style={{ padding: '6px', borderRadius: '6px', background: THEME.bg.surface, minWidth: 0 }}>
                    <div style={{ fontFamily: THEME.font.body, fontSize: '9px', color: THEME.text.muted }}>{label}</div>
                    <MonoText style={{ fontSize: '11px', color, fontWeight: 800, overflowWrap: 'anywhere' }}>{value}</MonoText>
                  </div>
                ))}
              </div>
              <div style={{ fontFamily: THEME.font.body, fontSize: '10px', color: THEME.text.muted, lineHeight: 1.35 }}>
                {item.status_reason}
              </div>
              <div style={{ fontFamily: THEME.font.mono, fontSize: '10px', color: THEME.text.faint, marginTop: '5px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                priced: {(item.priced_symbols || []).slice(0, 5).join(', ') || 'none'}
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
};

const SpreadTradeMapPanel = ({ proposal }) => {
  const rows = proposal?.outputs?.spread_archetype_trade_map || [];
  if (!rows.length) return null;
  const actionColor = (action, signal) => {
    const text = String(action || '').toUpperCase();
    if (text.includes('AVOID') || text.includes('SELL') || signal === 'SELL') return THEME.red[400];
    if (text.includes('BUY') || text.includes('READY')) return THEME.primary[400];
    if (text.includes('REPLAY')) return THEME.blue[400];
    return THEME.amber[400];
  };
  return (
    <Card glow style={{ marginBottom: '16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', alignItems: 'flex-start', marginBottom: '10px' }}>
        <div style={{ minWidth: 0 }}>
          <SectionLabel>Spread Trade Map</SectionLabel>
          <div style={{ fontFamily: THEME.font.heading, fontSize: '20px', color: THEME.text.primary, fontWeight: 800 }}>
            Index replay to tradable expression
          </div>
          <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.faint, marginTop: '3px', lineHeight: 1.35 }}>
            Each oil-style spread is mapped to the basket or event structure that can copy it. Arc stays locked until judge EXECUTE.
          </div>
        </div>
        <Badge color="blue">MULTI-SPREAD</Badge>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '8px' }}>
        {rows.slice(0, 6).map(row => {
          const selected = row.selected_expression || {};
          const signal = selected.latest_signal || 'MONITOR';
          const color = actionColor(row.tradability_action, signal);
          const ret5 = selected.return_5d_pct;
          const ret1 = selected.return_1m_pct;
          return (
            <div key={row.archetype_id} style={{ padding: '10px', borderRadius: '6px', background: THEME.bg.elevated, border: `1px solid ${THEME.border.subtle}`, minWidth: 0 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'flex-start', marginBottom: '6px' }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.primary, fontWeight: 800, lineHeight: 1.2, overflowWrap: 'anywhere' }}>
                    {row.label}
                  </div>
                  <div style={{ fontFamily: THEME.font.body, fontSize: '10px', color: THEME.text.faint, lineHeight: 1.3, marginTop: '2px' }}>
                    {row.oil_analogy} · {String(row.evidence_level || 'planned').replaceAll('_', ' ')}
                  </div>
                </div>
                <MonoText style={{ fontSize: '10px', color, fontWeight: 800, textAlign: 'right' }}>
                  {String(row.tradability_action || 'MONITOR').replaceAll('_', ' ')}
                </MonoText>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '6px', marginBottom: '6px' }}>
                {[
                  ['Replay', String(row.replay_status || 'NO_REPLAY').replaceAll('_', ' '), row.replay_promotable ? THEME.primary[400] : THEME.amber[400]],
                  ['Signal', signal, signal === 'SELL' ? THEME.red[400] : (signal === 'BUY' ? THEME.primary[400] : THEME.amber[400])],
                  ['5d/1m', `${ret5 === undefined || ret5 === '' ? '-' : Number(ret5).toFixed(1) + '%'} / ${ret1 === undefined || ret1 === '' ? '-' : Number(ret1).toFixed(1) + '%'}`, THEME.text.secondary],
                ].map(([label, value, itemColor]) => (
                  <div key={label} style={{ padding: '6px', borderRadius: '6px', background: THEME.bg.surface, minWidth: 0 }}>
                    <div style={{ fontFamily: THEME.font.body, fontSize: '9px', color: THEME.text.muted }}>{label}</div>
                    <MonoText style={{ fontSize: '10px', color: itemColor, fontWeight: 800, overflowWrap: 'anywhere' }}>{value}</MonoText>
                  </div>
                ))}
              </div>
              <div style={{ fontFamily: THEME.font.body, fontSize: '10px', color: THEME.text.secondary, lineHeight: 1.35, overflowWrap: 'anywhere' }}>
                {selected.title || selected.basket_label || 'No mapped basket yet'}
                {selected.basket_id ? ` · ${selected.basket_id}` : ''}
              </div>
              <div style={{ fontFamily: THEME.font.body, fontSize: '10px', color: THEME.text.muted, lineHeight: 1.35, marginTop: '4px' }}>
                {row.tradability_reason}
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
};

const IndexCatalogPanel = ({ data }) => {
  const catalog = data.spreadFamilies?.indexCatalog || {};
  const electricity = catalog.electricity || [];
  const compute = catalog.compute || [];
  const archetypes = catalog.spread_archetypes || [];
  if (!electricity.length && !compute.length && !archetypes.length) return null;
  const statusColor = (status) => {
    const text = String(status || '').toLowerCase();
    if (text.includes('active')) return THEME.primary[400];
    if (text.includes('proxy') || text.includes('derived')) return THEME.blue[400];
    if (text.includes('watchlist')) return THEME.amber[400];
    return THEME.text.faint;
  };
  const Column = ({ title, rows }) => (
    <div style={{ minWidth: 0 }}>
      <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.muted, marginBottom: '7px', textTransform: 'uppercase', fontWeight: 800 }}>
        {title}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        {rows.slice(0, 8).map(item => (
          <div key={item.id} style={{ padding: '8px', borderRadius: '6px', background: THEME.bg.elevated, border: `1px solid ${THEME.border.subtle}`, minWidth: 0 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'flex-start' }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.primary, fontWeight: 800, overflowWrap: 'anywhere' }}>{item.label}</div>
                <div style={{ fontFamily: THEME.font.body, fontSize: '10px', color: THEME.text.faint, lineHeight: 1.35, marginTop: '2px' }}>{item.venue || item.formula || ''}</div>
              </div>
              <MonoText style={{ fontSize: '9px', color: statusColor(item.status), fontWeight: 800, textAlign: 'right' }}>
                {String(item.status || 'planned').replaceAll('_', ' ')}
              </MonoText>
            </div>
            <div style={{ fontFamily: THEME.font.body, fontSize: '10px', color: THEME.text.muted, lineHeight: 1.35, marginTop: '4px' }}>
              {item.role || item.oil_analogy || ''}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
  return (
    <Card glow style={{ marginBottom: '16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', alignItems: 'flex-start', marginBottom: '10px' }}>
        <div>
          <SectionLabel>Index Catalog</SectionLabel>
          <div style={{ fontFamily: THEME.font.heading, fontSize: '20px', color: THEME.text.primary, fontWeight: 800 }}>
            Electricity and compute surfaces
          </div>
          <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.faint, lineHeight: 1.35, marginTop: '3px' }}>
            Active marks, derived curve proxies, watchlist direct events, and planned physical indexes used to build the spread menu.
          </div>
        </div>
        <Badge color="blue">{electricity.length + compute.length} INDEXES</Badge>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '10px' }}>
        <Column title={`Electricity (${electricity.length})`} rows={electricity} />
        <Column title={`Compute (${compute.length})`} rows={compute} />
        <Column title={`Spread Forms (${archetypes.length})`} rows={archetypes} />
      </div>
    </Card>
  );
};

const SpreadProfitabilityLedgerPanel = ({ proposal }) => {
  const ledger = proposal?.outputs?.spread_profitability_ledger || null;
  const rows = ledger?.rows || [];
  if (!rows.length) return null;
  const statusColor = (status) => {
    const text = String(status || '').toUpperCase();
    if (text === 'PAPER_BUY') return THEME.primary[400];
    if (text.includes('SELL') || text.includes('AVOID')) return THEME.red[400];
    if (text.includes('WAIT')) return THEME.blue[400];
    return THEME.amber[400];
  };
  const fmtMaybeMoney = (value) => (
    value === '' || value === undefined || value === null
      ? '-'
      : Number(value).toLocaleString(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 2 })
  );
  const fmtMaybePct = (value) => (
    value === '' || value === undefined || value === null
      ? '-'
      : `${Number(value).toFixed(2)}%`
  );
  return (
    <Card glow style={{ marginBottom: '16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', alignItems: 'flex-start', marginBottom: '10px' }}>
        <div style={{ minWidth: 0 }}>
          <SectionLabel>Profitability Ledger</SectionLabel>
          <div style={{ fontFamily: THEME.font.heading, fontSize: '20px', color: THEME.text.primary, fontWeight: 800 }}>
            Ranked paper spread PnL
          </div>
          <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.faint, lineHeight: 1.35, marginTop: '3px' }}>
            {ledger.realized_note || 'Replay and local tickets are separate from realized PnL.'}
            {ledger.paper_notional_usdc ? ` Paper notional: ${fmtMaybeMoney(ledger.paper_notional_usdc)}.` : ''}
          </div>
        </div>
        <Badge color="amber">PAPER</Badge>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '8px' }}>
        {rows.slice(0, 6).map(row => {
          const color = statusColor(row.profitability_status);
          const recentMarks = row.recent_paper_marks || [];
          const tradeReplay = row.paper_trade_replay || {};
          const recentTrades = tradeReplay.closed_trades || [];
          const openTrade = tradeReplay.open_trade || null;
          const latestPnl = Number(row.latest_paper_pnl_usdc || 0);
          const tradePnl = Number(row.paper_trade_total_pnl_usdc || 0);
          const pnlColor = row.latest_paper_pnl_usdc === '' || row.latest_paper_pnl_usdc === undefined
            ? THEME.text.secondary
            : latestPnl < 0 ? THEME.red[400] : THEME.primary[400];
          const tradePnlColor = row.paper_trade_total_pnl_usdc === '' || row.paper_trade_total_pnl_usdc === undefined
            ? THEME.text.secondary
            : tradePnl < 0 ? THEME.red[400] : THEME.primary[400];
          return (
            <div key={row.archetype_id} style={{ padding: '10px', borderRadius: '6px', background: THEME.bg.elevated, border: `1px solid ${THEME.border.subtle}`, minWidth: 0 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'flex-start', marginBottom: '6px' }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.primary, fontWeight: 800, overflowWrap: 'anywhere' }}>
                    #{row.rank} {row.label}
                  </div>
                  <div style={{ fontFamily: THEME.font.body, fontSize: '10px', color: THEME.text.faint, lineHeight: 1.3, marginTop: '2px' }}>
                    {row.expression_title || row.basket_id || 'No expression'} · {row.latest_signal || 'MONITOR'}
                  </div>
                </div>
                <MonoText style={{ fontSize: '10px', color, fontWeight: 800, textAlign: 'right' }}>
                  {String(row.profitability_status || 'MONITOR').replaceAll('_', ' ')}
                </MonoText>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '6px', marginBottom: '6px' }}>
                {[
                  ['Mark PnL', fmtMaybeMoney(row.latest_paper_pnl_usdc), pnlColor],
                  ['Ticket PnL', fmtMaybeMoney(row.paper_trade_total_pnl_usdc), tradePnlColor],
                  ['Mark %', fmtMaybePct(row.latest_paper_return_pct), pnlColor],
                  ['Ticket hit', row.paper_trade_hit_rate === '' || row.paper_trade_hit_rate === undefined ? '-' : `${Number(row.paper_trade_hit_rate).toFixed(0)}%`, THEME.text.secondary],
                ].map(([label, value, itemColor]) => (
                  <div key={label} style={{ padding: '6px', borderRadius: '6px', background: THEME.bg.surface }}>
                    <div style={{ fontFamily: THEME.font.body, fontSize: '9px', color: THEME.text.muted }}>{label}</div>
                    <MonoText style={{ fontSize: '11px', color: itemColor, fontWeight: 800 }}>{value}</MonoText>
                  </div>
                ))}
              </div>
              {recentMarks.length > 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '3px', marginBottom: '6px' }}>
                  {recentMarks.slice(-3).map(mark => (
                    <div key={`${row.archetype_id}-${mark.date}`} style={{ display: 'grid', gridTemplateColumns: '72px 1fr 72px', gap: '6px', fontFamily: THEME.font.mono, fontSize: '10px', color: THEME.text.faint }}>
                      <span>{mark.date || '-'}</span>
                      <span>close {Number(mark.index_close || 0).toFixed(2)}</span>
                      <span style={{ textAlign: 'right', color: Number(mark.paper_pnl_usdc || 0) < 0 ? THEME.red[400] : THEME.primary[400] }}>
                        {fmtMaybeMoney(mark.paper_pnl_usdc)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
              {(openTrade || recentTrades.length > 0) && (
                <div style={{ marginBottom: '6px', padding: '7px', borderRadius: '6px', background: THEME.bg.surface, border: `1px solid ${THEME.border.subtle}` }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'center', marginBottom: '4px' }}>
                    <div style={{ fontFamily: THEME.font.body, fontSize: '9px', color: THEME.text.muted, textTransform: 'uppercase', fontWeight: 800 }}>Paper ticket replay</div>
                    <MonoText style={{ fontSize: '9px', color: tradePnlColor, fontWeight: 800 }}>{row.paper_trade_action || 'WAIT'}</MonoText>
                  </div>
                  {openTrade && (
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 72px', gap: '6px', fontFamily: THEME.font.mono, fontSize: '10px', color: THEME.text.faint, marginBottom: '3px' }}>
                      <span>open {openTrade.entry_date} → {openTrade.mark_date}</span>
                      <span style={{ textAlign: 'right', color: Number(openTrade.pnl_usdc || 0) < 0 ? THEME.red[400] : THEME.primary[400] }}>{fmtMaybeMoney(openTrade.pnl_usdc)}</span>
                    </div>
                  )}
                  {recentTrades.slice(-2).map((trade, idx) => (
                    <div key={`${row.archetype_id}-ticket-${trade.entry_date}-${trade.exit_date}-${idx}`} style={{ display: 'grid', gridTemplateColumns: '1fr 72px', gap: '6px', fontFamily: THEME.font.mono, fontSize: '10px', color: THEME.text.faint, marginBottom: '3px' }}>
                      <span>{trade.entry_date} → {trade.exit_date}</span>
                      <span style={{ textAlign: 'right', color: Number(trade.pnl_usdc || 0) < 0 ? THEME.red[400] : THEME.primary[400] }}>{fmtMaybeMoney(trade.pnl_usdc)}</span>
                    </div>
                  ))}
                  <div style={{ fontFamily: THEME.font.body, fontSize: '9px', color: THEME.text.muted, lineHeight: 1.35 }}>
                    {tradeReplay.latest_trade_reason || 'Prior-close ticket replay; not a fill ledger.'}
                  </div>
                </div>
              )}
              <div style={{ fontFamily: THEME.font.body, fontSize: '10px', color: THEME.text.muted, lineHeight: 1.35 }}>
                {row.reason}
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
};

const statusBadgeColor = (status) => {
  const text = String(status || '').toUpperCase();
  if (['LIVE_PRICED', 'EVIDENCE_LOGGED', 'SETTLED_PNL'].includes(text)) return 'primary';
  if (['PROXY_PRICED', 'NO_SETTLED_PNL', 'NEEDS_PRICE', 'NEEDS_QUOTES', 'NEEDS_EVENT_MATCH'].includes(text)) return 'amber';
  if (['FAILED', 'ERROR'].some(part => text.includes(part))) return 'red';
  return 'blue';
};

const PnlStatusPanel = ({ pnl }) => {
  if (!pnl) return null;
  const proxyBits = [];
  if (pnl.proxyLatestSignal) proxyBits.push(`${pnl.proxyLatestSignal}/${pnl.proxyReplayStatus || 'replay'}`);
  if (pnl.proxy5dReturnPct !== null && pnl.proxy5dReturnPct !== undefined) proxyBits.push(`5d ${Number(pnl.proxy5dReturnPct).toFixed(2)}%`);
  if (pnl.proxy1mReturnPct !== null && pnl.proxy1mReturnPct !== undefined) proxyBits.push(`1m ${Number(pnl.proxy1mReturnPct).toFixed(2)}%`);
  return (
    <Card style={{ marginBottom: '16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', alignItems: 'flex-start', marginBottom: '10px' }}>
        <div>
          <SectionLabel>Profitability Ledger</SectionLabel>
          <div style={{ fontFamily: THEME.font.heading, fontSize: '18px', color: THEME.text.primary, fontWeight: 800 }}>
            {pnl.statusLabel || 'PnL status'}
          </div>
          <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.faint, lineHeight: 1.35, marginTop: '3px' }}>
            Settled PnL is shown only after reconciliation. Replay and local tickets stay labelled separately.
          </div>
        </div>
        <Badge color={statusBadgeColor(pnl.status)}>{String(pnl.status || 'UNKNOWN').replaceAll('_', ' ')}</Badge>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '8px' }}>
        {[
          ['Settled PnL', pnl.totalDisplay || 'No settled PnL', pnl.hasReconciled ? THEME.primary[400] : THEME.amber[400]],
          ['Trades', pnl.tradesDisplay || '0 settled', THEME.text.secondary],
          ['Wrapped Jobs', pnl.wrappedJobs || 0, THEME.text.secondary],
          ['Judge EXECUTEs', pnl.executes || 0, THEME.text.secondary],
        ].map(([label, value, color]) => (
          <div key={label} style={{ padding: '8px', borderRadius: '6px', background: THEME.bg.elevated, minWidth: 0 }}>
            <div style={{ fontFamily: THEME.font.body, fontSize: '10px', color: THEME.text.muted }}>{label}</div>
            <MonoText style={{ fontSize: '13px', color, fontWeight: 800, overflowWrap: 'anywhere' }}>{value}</MonoText>
          </div>
        ))}
      </div>
      <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.secondary, lineHeight: 1.4, marginTop: '9px' }}>
        {pnl.note || 'No reconciled PnL note available.'}
      </div>
      <div style={{ fontFamily: THEME.font.mono, fontSize: '10px', color: THEME.text.faint, lineHeight: 1.35, marginTop: '5px' }}>
        spread replay: {pnl.spreadReplayStatus || 'unknown'} · {pnl.spreadMarkChanges || 0}/{pnl.spreadRawObservations || 0} mark changes · {pnl.spreadCollapsedPolls || 0} repeated polls collapsed
        {proxyBits.length ? ` · proxy replay: ${proxyBits.join(' · ')}` : ''}
      </div>
    </Card>
  );
};

const VenueEvidencePanel = ({ evidence }) => {
  const rows = evidence?.rows || [];
  if (!rows.length) return null;
  return (
    <Card glow style={{ marginBottom: '16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', alignItems: 'flex-start', marginBottom: '10px' }}>
        <div style={{ minWidth: 0 }}>
          <SectionLabel>Venue Evidence Matrix</SectionLabel>
          <div style={{ fontFamily: THEME.font.heading, fontSize: '20px', color: THEME.text.primary, fontWeight: 800 }}>
            Real feeds, proxy feeds, and evidence gaps
          </div>
          <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.faint, marginTop: '3px', lineHeight: 1.35 }}>
            Polymarket, Kalshi, IBKR, public quotes, crypto, and Opoint/Nebius are labelled by role before any judge or Arc action.
          </div>
        </div>
        <Badge color="amber">EVIDENCE ONLY</Badge>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))', gap: '8px' }}>
        {rows.map(row => (
          <div key={row.surface} style={{ padding: '10px', borderRadius: '6px', background: THEME.bg.elevated, border: `1px solid ${THEME.border.subtle}`, minWidth: 0 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'flex-start', marginBottom: '6px' }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.primary, fontWeight: 800, overflowWrap: 'anywhere' }}>
                  {row.label}
                </div>
                <div style={{ fontFamily: THEME.font.body, fontSize: '10px', color: THEME.text.faint, lineHeight: 1.35, marginTop: '2px' }}>
                  {row.role}
                </div>
              </div>
              <Badge color={statusBadgeColor(row.status)}>{String(row.status || '').replaceAll('_', ' ')}</Badge>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '6px', marginBottom: '7px' }}>
              {[
                ['Rows', row.row_count || 0],
                ['Priced', row.priced_count || 0],
                ['Proxy', row.external_proxy_count || 0],
              ].map(([label, value]) => (
                <div key={label} style={{ padding: '6px', borderRadius: '6px', background: THEME.bg.surface }}>
                  <div style={{ fontFamily: THEME.font.body, fontSize: '9px', color: THEME.text.muted }}>{label}</div>
                  <MonoText style={{ fontSize: '11px', color: THEME.text.secondary }}>{value}</MonoText>
                </div>
              ))}
            </div>
            {(row.latest_title || row.latest_pricing_status) && (
              <div style={{ fontFamily: THEME.font.body, fontSize: '10px', color: THEME.text.secondary, lineHeight: 1.35, overflowWrap: 'anywhere' }}>
                {row.latest_title || row.latest_slug}{row.latest_pricing_status ? ` · ${row.latest_pricing_status}` : ''}
              </div>
            )}
            {(row.gaps || []).slice(0, 1).map(gap => (
              <div key={gap} style={{ fontFamily: THEME.font.body, fontSize: '10px', color: THEME.text.muted, lineHeight: 1.35, marginTop: '5px' }}>
                {gap}
              </div>
            ))}
            <div style={{ fontFamily: THEME.font.mono, fontSize: '9px', color: THEME.text.faint, marginTop: '5px' }}>
              judge required · Arc ready: {row.can_drive_arc ? 'yes' : 'no'}
            </div>
          </div>
        ))}
      </div>
      {evidence.guardrail && (
        <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.muted, lineHeight: 1.35, marginTop: '9px' }}>
          {evidence.guardrail}
        </div>
      )}
    </Card>
  );
};

const RealVenueCopyMatrixPanel = ({ proposal }) => {
  const matrix = proposal?.outputs?.real_venue_copy_matrix || {};
  const rows = matrix.rows || [];
  if (!rows.length) return null;
  const roleColor = (role, status) => {
    const text = `${role || ''} ${status || ''}`.toUpperCase();
    if (text.includes('DIRECT')) return THEME.blue[400];
    if (text.includes('PROXY')) return THEME.primary[400];
    if (text.includes('EVIDENCE')) return THEME.amber[400];
    return THEME.text.secondary;
  };
  return (
    <Card glow style={{ marginBottom: '16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', alignItems: 'flex-start', marginBottom: '10px' }}>
        <div style={{ minWidth: 0 }}>
          <SectionLabel>Real Venue Copy Matrix</SectionLabel>
          <div style={{ fontFamily: THEME.font.heading, fontSize: '20px', color: THEME.text.primary, fontWeight: 800 }}>
            How real surfaces copy the spread
          </div>
          <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.faint, marginTop: '3px', lineHeight: 1.35 }}>
            Direct events, liquid proxy hedges, miner-margin proxies, and LLM/news evidence are separated before judge and Arc.
          </div>
        </div>
        <Badge color="blue">{matrix.summary?.surfaces || rows.length} SURFACES</Badge>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '8px' }}>
        {rows.map(row => {
          const color = roleColor(row.copy_role, row.copy_status);
          const sample = row.sample_legs || [];
          const links = row.spread_links || [];
          return (
            <div key={row.surface} style={{ padding: '10px', borderRadius: '6px', background: THEME.bg.elevated, border: `1px solid ${THEME.border.subtle}`, minWidth: 0 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'flex-start', marginBottom: '6px' }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.primary, fontWeight: 800, overflowWrap: 'anywhere' }}>
                    {row.label || row.surface}
                  </div>
                  <div style={{ fontFamily: THEME.font.body, fontSize: '10px', color: THEME.text.faint, lineHeight: 1.35, marginTop: '2px' }}>
                    {String(row.copy_role || '').replaceAll('_', ' ')}
                  </div>
                </div>
                <MonoText style={{ fontSize: '10px', color, fontWeight: 800, textAlign: 'right' }}>
                  {String(row.copy_status || '').replaceAll('_', ' ')}
                </MonoText>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '6px', marginBottom: '7px' }}>
                {[
                  ['Priced', row.priced_count || 0],
                  ['Watch', row.watchlist_count || 0],
                  ['Proxy', row.external_proxy_count || 0],
                ].map(([label, value]) => (
                  <div key={label} style={{ padding: '6px', borderRadius: '6px', background: THEME.bg.surface }}>
                    <div style={{ fontFamily: THEME.font.body, fontSize: '9px', color: THEME.text.muted }}>{label}</div>
                    <MonoText style={{ fontSize: '11px', color: THEME.text.secondary }}>{value}</MonoText>
                  </div>
                ))}
              </div>
              {links.length > 0 && (
                <div style={{ fontFamily: THEME.font.body, fontSize: '10px', color: THEME.text.secondary, lineHeight: 1.35, marginBottom: '5px' }}>
                  Copies: {links.slice(0, 3).map(link => `${link.label || link.archetype_id}:${String(link.action || 'MONITOR').replaceAll('_', ' ')}`).join('; ')}
                </div>
              )}
              {sample.length > 0 && (
                <div style={{ fontFamily: THEME.font.body, fontSize: '10px', color: THEME.text.faint, lineHeight: 1.35, marginBottom: '5px', overflowWrap: 'anywhere' }}>
                  Legs: {sample.slice(0, 3).map(leg => leg.slug || leg.title).join(', ')}
                </div>
              )}
              <div style={{ fontFamily: THEME.font.body, fontSize: '10px', color: THEME.text.muted, lineHeight: 1.35 }}>
                {row.action}
              </div>
            </div>
          );
        })}
      </div>
      {matrix.guardrail && (
        <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.muted, lineHeight: 1.35, marginTop: '9px' }}>
          {matrix.guardrail}
        </div>
      )}
    </Card>
  );
};

const verdictColor = (label) => ({ EXECUTE: 'primary', REJECT: 'red', DEFER: 'amber', CHALLENGE: 'purple', WATCHLIST: 'blue' }[label] || 'muted');
const surfaceIcon = (s) => ({ crypto: '₿', ibkr: '📊', ibkr_prediction: '◈', polymarket: '◎', kalshi: 'K' }[s] || '·');

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
  const threshold = Number(construction.entry_threshold_score ?? 70);
  const judgeVerdict = construction.judge_verdict || {};
  const canOpen = construction.recommended_action === 'BUY_CONTRACT' && score >= threshold && judgeVerdict.label === 'EXECUTE';
  const label = canOpen
    ? (construction.recommendation_label || 'Open paper hedge')
    : (construction.recommendation_label || 'Monitor');
  const reason = construction.recommendation_reason || 'Recommendation refreshes from the latest spread, quote, and leg state.';
  const color = canOpen ? THEME.primary[400] : THEME.amber[400];
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
              Entry score {Math.round(score)}/100 · buy threshold {Math.round(threshold)}/100 · {reason}
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
              {canOpen
                ? 'Open paper hedge freezes a local entry ticket only; Arc stays gated by judge.classify().'
                : 'No user-facing buy at this score; monitor until the entry threshold and judge gate both clear.'}
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
  const oracleEvidence = proposal.outputs?.oracle_judge_evidence || {};
  const collateralProfiles = proposal.outputs?.collateral_profile_candidates || [];
  const weightedLegs = mockConstruction?.weighted_legs || [];
  const tooling = mockConstruction?.agent_tooling || [];
  const { ticket, marked, buy, monitor, sell, reset } = useMockContractTicket(proposal, mockConstruction, weightedLegs);
  const entryScore = Number(mockConstruction?.entry_signal_score ?? mockConstruction?.profitability_score ?? 0);
  const entryThreshold = Number(mockConstruction?.entry_threshold_score ?? 70);
  const canBuyMock = mockConstruction?.recommended_action === 'BUY_CONTRACT'
    && entryScore >= entryThreshold
    && mockConstruction?.judge_verdict?.label === 'EXECUTE';
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
        <div style={{ padding: '10px', borderRadius: '6px', background: THEME.bg.elevated }}>
          <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.muted, marginBottom: '5px' }}>LLM / news evidence</div>
          <div style={{ fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.secondary, lineHeight: 1.4 }}>
            {oracleEvidence.status
              ? `${String(oracleEvidence.status).replaceAll('_', ' ')} · ${oracleEvidence.row_count || 0} receipts · ${oracleEvidence.filtered_articles || 0}/${oracleEvidence.raw_articles || 0} articles`
              : 'No Opoint/Nebius receipt attached.'}
          </div>
          <div style={{ fontFamily: THEME.font.mono, fontSize: '10px', color: THEME.text.faint, lineHeight: 1.35, marginTop: '6px', overflowWrap: 'anywhere' }}>
            {oracleEvidence.latest_verdict ? `latest: ${oracleEvidence.latest_verdict}/${oracleEvidence.latest_reason_code || 'checked'} · ` : ''}
            hash {oracleEvidence.oracle_evidence_hash || 'none'}
          </div>
          <div style={{ fontFamily: THEME.font.body, fontSize: '10px', color: THEME.text.muted, lineHeight: 1.35, marginTop: '5px' }}>
            Evidence only; scorer and judge gates remain mandatory.
          </div>
        </div>
      </div>
      {collateralProfiles.length > 0 && (
        <div style={{ marginTop: '10px', padding: '10px', borderRadius: '6px', background: THEME.bg.elevated }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '10px', alignItems: 'flex-start', marginBottom: '8px' }}>
            <div>
              <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.muted }}>Collateral profile candidates</div>
              <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.faint, lineHeight: 1.35 }}>
                Shows whether the cashflow is actually power-sensitive enough to syndicate.
              </div>
            </div>
            <Badge color="blue">MATERIALITY GATE</Badge>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: '8px' }}>
            {collateralProfiles.slice(0, 4).map(profile => {
              const pass = profile.materiality_gate === 'PASS';
              const actionColor = profile.action === 'PAPER_BUY_CANDIDATE'
                ? THEME.primary[400]
                : (String(profile.action || '').includes('AVOID') ? THEME.red[400] : THEME.amber[400]);
              return (
                <div key={profile.profile_id} style={{ padding: '9px', borderRadius: '6px', background: THEME.bg.surface, border: `1px solid ${pass ? THEME.primary[400] + '25' : THEME.border.subtle}` }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'flex-start' }}>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.primary, fontWeight: 800, overflowWrap: 'anywhere' }}>{profile.label}</div>
                      <div style={{ fontFamily: THEME.font.body, fontSize: '10px', color: THEME.text.faint, lineHeight: 1.3, marginTop: '3px' }}>{profile.cashflow}</div>
                    </div>
                    <Badge color={pass ? 'primary' : 'amber'}>{profile.materiality_gate || 'MONITOR'}</Badge>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '5px', marginTop: '7px' }}>
                    {[
                      ['Power', `${Number(profile.modeled_power_cost_share_pct || 0).toFixed(1)}%`, pass ? THEME.primary[400] : THEME.amber[400]],
                      ['Margin', `${Number(profile.margin_pct || 0).toFixed(0)}%`, Number(profile.margin_pct || 0) > 0 ? THEME.primary[400] : THEME.red[400]],
                      ['Score', Math.round(Number(profile.entry_score || 0)), actionColor],
                    ].map(([label, value, color]) => (
                      <div key={label} style={{ padding: '5px', borderRadius: '5px', background: THEME.bg.elevated }}>
                        <div style={{ fontFamily: THEME.font.body, fontSize: '9px', color: THEME.text.muted }}>{label}</div>
                        <MonoText style={{ fontSize: '10px', color, fontWeight: 800 }}>{value}</MonoText>
                      </div>
                    ))}
                  </div>
                  <div style={{ fontFamily: THEME.font.body, fontSize: '10px', color: THEME.text.muted, lineHeight: 1.35, marginTop: '6px' }}>
                    {profile.action}: {profile.status_reason}
                  </div>
                  <div style={{ fontFamily: THEME.font.mono, fontSize: '9px', color: THEME.text.faint, marginTop: '5px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    needs: {(profile.collateral_needed || []).join(', ')}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
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
              <GlowButton
                size="sm"
                onClick={buy}
                disabled={!canBuyMock}
                title={canBuyMock ? 'Freeze a local paper/testnet entry ticket.' : `Entry score must clear ${Math.round(entryThreshold)}/100 and judge must return EXECUTE.`}
              >
                ▸ Open Paper Hedge
              </GlowButton>
              <GlowButton size="sm" variant="secondary" onClick={monitor}>◎ Monitor Price</GlowButton>
              {ticket?.status === 'open' && (
                <GlowButton size="sm" variant="secondary" onClick={sell} style={{ color: THEME.red[400], borderColor: THEME.red[400] + '40' }}>□ Sell Mock</GlowButton>
              )}
              {ticket && (
                <GlowButton size="sm" variant="secondary" onClick={reset}>↺ Reset</GlowButton>
              )}
            </div>
            {!canBuyMock && (
              <div style={{ fontFamily: THEME.font.body, fontSize: '10px', color: THEME.text.muted, lineHeight: 1.35, marginTop: '6px' }}>
                Buy is disabled because entry score is {Math.round(entryScore)}/100 and the user-facing threshold is {Math.round(entryThreshold)}/100 with judge EXECUTE required.
              </div>
            )}
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

const OraclePanel = ({ oracle = {} }) => {
  const isReceiptState = oracle.status || oracle.row_count !== undefined;
  const verdictCounts = oracle.verdict_counts || {};
  const verdictText = Object.entries(verdictCounts).map(([k, v]) => `${k}:${v}`).join(' · ') || 'none';
  if (!isReceiptState && oracle.aiInfra) {
    return (
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
  }
  return (
    <Card>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', alignItems: 'flex-start', marginBottom: '10px' }}>
        <div>
          <SectionLabel>LLM / News Judge Evidence</SectionLabel>
          <div style={{ fontFamily: THEME.font.heading, fontSize: '20px', color: THEME.text.primary, fontWeight: 800 }}>
            Opoint + Nebius receipts
          </div>
          <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.faint, lineHeight: 1.35, marginTop: '3px' }}>
            Evidence only. Missing or DEFER receipts cannot bypass premium scoring or judge.classify().
          </div>
        </div>
        <Badge color={oracle.status === 'EVIDENCE_LOGGED' ? 'primary' : 'amber'}>{String(oracle.status || 'NO_RECEIPTS').replaceAll('_', ' ')}</Badge>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '8px' }}>
        {[
          ['Receipts', oracle.row_count || 0, THEME.text.secondary],
          ['Verdicts', verdictText, THEME.primary[400]],
          ['Raw articles', oracle.raw_articles || 0, THEME.text.secondary],
          ['Filtered', oracle.filtered_articles || 0, THEME.amber[400]],
          ['Latest reason', oracle.latest_reason_code || 'none', THEME.text.secondary],
          ['Model', oracle.latest_model || 'not run', THEME.text.secondary],
        ].map(([label, value, color]) => (
          <div key={label} style={{ padding: '10px', borderRadius: '6px', background: THEME.bg.elevated, minWidth: 0 }}>
            <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.muted, marginBottom: '4px' }}>{label}</div>
            <MonoText style={{ fontSize: '13px', fontWeight: 700, color, overflowWrap: 'anywhere' }}>{value}</MonoText>
          </div>
        ))}
      </div>
      {(oracle.latest_title || oracle.latest_slug) && (
        <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.secondary, lineHeight: 1.35, marginTop: '9px', overflowWrap: 'anywhere' }}>
          Latest: {oracle.latest_title || oracle.latest_slug}
        </div>
      )}
    </Card>
  );
};

const OperatorSignalSheetPanel = ({ proposal }) => {
  const sheet = proposal?.outputs?.operator_signal_sheet || null;
  if (!sheet) return null;
  const actionColor = sheet.overall_action === 'PAPER_BUY_CANDIDATE' || sheet.overall_action === 'STRUCTURE_THEN_JUDGE'
    ? THEME.primary[400]
    : (String(sheet.overall_action || '').includes('AVOID') ? THEME.red[400] : THEME.amber[400]);
  const rows = sheet.rows || [];
  return (
    <Card glow style={{ marginBottom: '16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', alignItems: 'flex-start', marginBottom: '10px' }}>
        <div style={{ minWidth: 0 }}>
          <SectionLabel>Operator Signal Sheet</SectionLabel>
          <div style={{ fontFamily: THEME.font.heading, fontSize: '20px', color: THEME.text.primary, fontWeight: 800, lineHeight: 1.2 }}>
            {sheet.headline || 'Monitor current package'}
          </div>
          <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.faint, lineHeight: 1.35, marginTop: '4px' }}>
            {sheet.reason || 'No operator reason available.'}
          </div>
        </div>
        <Badge color={String(sheet.overall_action || '').includes('AVOID') ? 'red' : (sheet.overall_action === 'MONITOR' ? 'amber' : 'primary')}>
          {String(sheet.overall_action || 'MONITOR').replaceAll('_', ' ')}
        </Badge>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(185px, 1fr))', gap: '8px' }}>
        {rows.slice(0, 6).map(row => {
          const rowAction = String(row.action || 'MONITOR');
          const color = rowAction.includes('AVOID') || row.signal === 'SELL'
            ? THEME.red[400]
            : (rowAction.includes('BUY') || rowAction === 'PROMOTABLE' ? THEME.primary[400] : THEME.amber[400]);
          return (
            <div key={row.key} style={{ padding: '9px', borderRadius: '6px', background: THEME.bg.elevated, border: `1px solid ${THEME.border.subtle}`, minWidth: 0 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'flex-start' }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.primary, fontWeight: 800, overflowWrap: 'anywhere' }}>{row.label}</div>
                  <div style={{ fontFamily: THEME.font.mono, fontSize: '10px', color, marginTop: '3px', overflowWrap: 'anywhere' }}>{rowAction.replaceAll('_', ' ')}</div>
                </div>
                {row.signal && <MonoText style={{ fontSize: '10px', color, fontWeight: 800 }}>{String(row.signal).replaceAll('_', ' ')}</MonoText>}
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '5px', marginTop: '7px' }}>
                {[
                  ['score', row.score ?? '-'],
                  ['5d', row.return_5d_pct === undefined || row.return_5d_pct === '' ? '-' : `${Number(row.return_5d_pct).toFixed(2)}%`],
                  ['power', row.power_share_pct === undefined || row.power_share_pct === '' ? '-' : `${Number(row.power_share_pct).toFixed(1)}%`],
                ].map(([label, value]) => (
                  <div key={label} style={{ padding: '5px', borderRadius: '5px', background: THEME.bg.surface }}>
                    <div style={{ fontFamily: THEME.font.body, fontSize: '9px', color: THEME.text.muted }}>{label}</div>
                    <MonoText style={{ fontSize: '10px', color: THEME.text.secondary, fontWeight: 700 }}>{value}</MonoText>
                  </div>
                ))}
              </div>
              <div style={{ fontFamily: THEME.font.body, fontSize: '10px', color: THEME.text.muted, lineHeight: 1.35, marginTop: '6px' }}>
                {row.reason}
              </div>
            </div>
          );
        })}
      </div>
      <div style={{ fontFamily: THEME.font.body, fontSize: '10px', color: THEME.text.faint, lineHeight: 1.35, marginTop: '8px' }}>
        {sheet.guardrail}
      </div>
    </Card>
  );
};

const TelegramCampaignPanel = ({ campaign }) => {
  if (!campaign || !Array.isArray(campaign.posts) || campaign.posts.length === 0) return null;
  const posted = Number(campaign.posted_count || 0);
  const total = Number(campaign.total_posts || campaign.posts.length || 0);
  const pending = Number(campaign.pending_count || Math.max(0, total - posted));
  const allPosted = pending === 0 && total > 0;
  return (
    <Card glow style={{ marginBottom: '16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', alignItems: 'flex-start', marginBottom: '10px' }}>
        <div style={{ minWidth: 0 }}>
          <SectionLabel>Telegram Campaign</SectionLabel>
          <div style={{ fontFamily: THEME.font.heading, fontSize: '20px', color: THEME.text.primary, fontWeight: 800 }}>
            {allPosted ? 'Campaign posted' : 'Campaign ready to post'}
          </div>
          <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.faint, lineHeight: 1.35, marginTop: '3px' }}>
            {campaign.note || 'Status is read from the local sent-key ledger.'}
          </div>
        </div>
        <Badge color={allPosted ? 'primary' : 'amber'}>{posted}/{total} POSTED</Badge>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(185px, 1fr))', gap: '8px', marginBottom: '8px' }}>
        {(campaign.posts || []).map(post => (
          <div key={post.key} style={{ padding: '9px', borderRadius: '6px', background: THEME.bg.elevated, border: `1px solid ${THEME.border.subtle}`, minWidth: 0 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'flex-start' }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.primary, fontWeight: 800, overflowWrap: 'anywhere' }}>{post.title}</div>
                <div style={{ fontFamily: THEME.font.body, fontSize: '10px', color: THEME.text.muted, lineHeight: 1.35, marginTop: '3px' }}>{post.description}</div>
              </div>
              <MonoText style={{ fontSize: '9px', color: post.posted ? THEME.primary[400] : THEME.amber[400], fontWeight: 800, textAlign: 'right' }}>
                {String(post.status || (post.posted ? 'POSTED' : 'READY')).replaceAll('_', ' ')}
              </MonoText>
            </div>
          </div>
        ))}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '8px' }}>
        {[
          ['Draft', campaign.draft_command || 'npm run telegram:campaign-draft'],
          ['Post', campaign.post_command || 'npm run telegram:campaign-post'],
          ['Channel', campaign.channel_configured ? 'configured' : 'missing TELEGRAM_CHANNEL_ID'],
        ].map(([label, value]) => (
          <div key={label} style={{ padding: '7px', borderRadius: '6px', background: THEME.bg.surface, minWidth: 0 }}>
            <div style={{ fontFamily: THEME.font.body, fontSize: '9px', color: THEME.text.muted, textTransform: 'uppercase', fontWeight: 800 }}>{label}</div>
            <MonoText style={{ fontSize: '10px', color: THEME.text.secondary, fontWeight: 700, overflowWrap: 'anywhere' }}>{value}</MonoText>
          </div>
        ))}
      </div>
    </Card>
  );
};

const DashboardPage = ({ refreshRate }) => {
  const data = useLiveData(refreshRate);
  const isMobile = useIsMobile(820);
  const isNarrow = useIsMobile(520);
  const construction = data.syntheticInstrument?.outputs?.mock_hedge_construction || {};
  const quoteSourceText = quoteSourceSummary(construction.quote_sources || []);
  const topEntryScore = Number(construction.entry_signal_score ?? construction.profitability_score ?? 0);
  const topEntryThreshold = Number(construction.entry_threshold_score ?? 70);
  const topCanBuy = construction.recommended_action === 'BUY_CONTRACT'
    && topEntryScore >= topEntryThreshold
    && construction.judge_verdict?.label === 'EXECUTE';
  const recommendation = topCanBuy ? (construction.recommendation_label || 'Open paper hedge') : (construction.recommendation_label || 'Monitor');

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
        <StatCard label="Agent Recommendation" value={recommendation} color={topCanBuy ? THEME.primary[400] : THEME.amber[400]} />
        <StatCard label="Quote Source" value={quoteSourceText || 'Pending'} valueSize={16} />
      </div>

      <PnlStatusPanel pnl={data.pnl} />
      <SpreadProfitabilityLedgerPanel proposal={data.syntheticInstrument} />
      <OperatorSignalSheetPanel proposal={data.syntheticInstrument} />
      <TelegramCampaignPanel campaign={data.telegramCampaign} />

      {/* Signal + Candidates */}
      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '2fr 1fr', gap: '12px', marginBottom: '16px', alignItems: 'start' }}>
        <SignalPanel data={data} />
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <MockContractSummaryPanel proposal={data.syntheticInstrument} />
          <ProxyBasketReplayPanel data={data} />
        </div>
      </div>

      <SyndicatedInstrumentMenuPanel proposal={data.syntheticInstrument} />
      <IndexCatalogPanel data={data} />
      <SpreadTradeMapPanel proposal={data.syntheticInstrument} />

      <RealVenueCopyMatrixPanel proposal={data.syntheticInstrument} />
      <VenueEvidencePanel evidence={data.venueEvidence} />

      <SyntheticInstrumentPanel proposal={data.syntheticInstrument} />

      {/* Oracle */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '12px' }}>
        <OraclePanel oracle={data.oracleResults} />
      </div>
    </div>
  );
};

Object.assign(window, { DashboardPage, mapSnapshotToDashboardData, emptyDashboardData, derivePrimaryExposure, formatEventDate, roleLabel });
