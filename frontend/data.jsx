/* Power by Botozen - backend-backed data adapters */

const fmtUsd = (n, d = 2) => `$${Number(n || 0).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d })}`;
const fmtSigned = (n, d = 2) => `${Number(n || 0) >= 0 ? '+' : '-'}$${Math.abs(Number(n || 0)).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d })}`;
const fmtPct = (n, d = 2) => `${Number(n || 0) >= 0 ? '+' : '-'}${Math.abs(Number(n || 0)).toFixed(d)}%`;
const fmtNav = (n) => Number(n || 0).toFixed(4);

const SIGNAL_META = {
  ENTER: { color: 'primary', label: 'BUY / PAPER ENTRY' },
  HOLD: { color: 'amber', label: 'HOLD / WATCH' },
  CLOSE_OR_AVOID: { color: 'red', label: 'CLOSE / AVOID' },
};

const REGIME_META = {
  CLOSE_OR_AVOID: { color: 'red', label: 'CLOSE / AVOID', note: 'The marked expression is rich or selling; do not add fresh paper exposure.' },
  RICH: { color: 'amber', label: 'RICH', note: 'Spread is above the recent mean. Trim or wait for confirmation.' },
  NEUTRAL: { color: 'muted', label: 'NEUTRAL', note: 'Spread is near fair value. No fresh entry edge.' },
  CHEAP: { color: 'blue', label: 'CHEAP', note: 'Spread is below the recent mean. Monitor for a buyable setup.' },
  ENTER_WINDOW: { color: 'primary', label: 'ENTER WINDOW', note: 'Spread and replay evidence are constructive for paper entry.' },
};

const FORM_LABELS = {
  compute_spark_spread: 'Compute spark spread',
  fuel_stack_compute_spread: 'Fuel-stack compute spread',
  compute_power_calendar_basis: 'Compute-power calendar basis',
  electricity_calendar_spread: 'Electricity calendar spread',
  compute_calendar_spread: 'Compute calendar spread',
  regional_compute_basis: 'Regional compute basis',
  regional_power_basis: 'Regional power basis',
  locational_power_compute_basis: 'Locational power/compute basis',
  grid_event_hazard_spread: 'Grid-event hazard spread',
  miner_margin_power_pair: 'Miner-margin power pair',
};

const DEFAULT_SPREAD_FORMS = [
  { id: 'compute_spark_spread', name: 'Compute spark spread', desc: 'Compute revenue net of delivered electricity cost', headline: true },
  { id: 'fuel_stack_compute_spread', name: 'Fuel-stack compute spread', desc: 'AI/miner demand versus gas and merchant power' },
  { id: 'compute_power_calendar_basis', name: 'Compute-power calendar basis', desc: 'Front compute tenor versus forward power tenor' },
  { id: 'electricity_calendar_spread', name: 'Electricity calendar spread', desc: 'Prompt power scarcity versus later delivery' },
  { id: 'compute_calendar_spread', name: 'Compute calendar spread', desc: 'Prompt GPU-hour price versus forward compute' },
  { id: 'regional_compute_basis', name: 'Regional compute basis', desc: 'Region A GPU rental versus Region B GPU rental' },
  { id: 'regional_power_basis', name: 'Regional power basis', desc: 'Region A power price versus Region B power price' },
  { id: 'locational_power_compute_basis', name: 'Locational basis', desc: 'Regional compute capacity versus grid hub pricing' },
  { id: 'grid_event_hazard_spread', name: 'Grid-event hazard', desc: 'Scarcity, outage, and siting-event exposure' },
  { id: 'miner_margin_power_pair', name: 'Miner-margin pair', desc: 'Proof-of-work revenue beta versus electricity cost' },
];

const normalizeArray = (value) => Array.isArray(value) ? value : [];
const num = (value, fallback = 0) => {
  if (value === null || value === undefined || value === '') return fallback;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

const prettyLabel = (value, fallback = 'unknown') => String(value || fallback)
  .replace(/[_-]+/g, ' ')
  .replace(/\s+/g, ' ')
  .trim();

const sourceLabel = (value) => {
  const low = String(value || '').toLowerCase();
  if (low === 'yahoo_finance_chart') return 'Yahoo public quote';
  if (low === 'yahoo_close_history') return 'Yahoo replay history';
  if (low === 'ibkr_energy_history_csv') return 'IBKR paper CSV';
  if (low === 'ibkr_tws_front_future') return 'IBKR TWS future';
  if (low === 'ibkr_tws_stock') return 'IBKR TWS stock';
  if (low === 'ibkr_forecast_inventory') return 'IBKR ForecastTrader inventory';
  if (low === 'polymarket_direct_watchlist') return 'Polymarket Gamma';
  if (low === 'kalshi_direct_ai_watchlist') return 'Kalshi public API';
  if (low === 'alpaca_market_data') return 'Alpaca market data';
  return value || '';
};

const surfaceIcon = (surface) => ({
  polymarket: 'PM',
  ibkr_prediction: 'IB',
  ibkr: 'IB',
  kalshi: 'K',
  crypto: 'C',
  public_market: '$',
  mock_contract: 'MC',
}[String(surface || '').toLowerCase()] || 'S');

const formatEventDate = (value) => {
  if (!value) return '';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
};

const readPath = (obj, path, fallback) => {
  let cur = obj;
  for (const part of path) {
    if (!cur || typeof cur !== 'object') return fallback;
    cur = cur[part];
  }
  return cur === undefined || cur === null ? fallback : cur;
};

const formName = (id) => FORM_LABELS[id] || DEFAULT_SPREAD_FORMS.find(f => f.id === id)?.name || id || 'Spread';

const apiJson = async (path, options = {}) => {
  const timeoutMs = Number(options.timeoutMs || 12000);
  const controller = options.signal ? null : new AbortController();
  const timeout = controller ? setTimeout(() => controller.abort(), timeoutMs) : null;
  try {
    const resp = await fetch(path, {
      credentials: 'same-origin',
      cache: options.cache || (path === '/api/snapshot' ? 'default' : 'no-store'),
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      ...options,
      signal: options.signal || controller?.signal,
    });
    const body = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(body.error || `HTTP ${resp.status}`);
    return body;
  } catch (err) {
    if (err?.name === 'AbortError') throw new Error(`HTTP timeout reading ${path}`);
    throw err;
  } finally {
    if (timeout) clearTimeout(timeout);
  }
};

const noteSignalFromBackend = (note) => {
  const signal = String(note.signal || note.latestSignal || '').toUpperCase();
  if (signal.includes('ENTER') || signal === 'BUY') return 'ENTER';
  if (signal.includes('SELL') || signal.includes('CLOSE') || signal.includes('AVOID')) return 'CLOSE_OR_AVOID';
  return 'HOLD';
};

const buildMarks = (notes) => {
  const marks = {};
  normalizeArray(notes).forEach(note => {
    const hist = normalizeArray(note.hist).map(v => num(v)).filter(v => v > 0);
    const markNav = num(note.markNav, hist.length ? hist[hist.length - 1] : 1);
    marks[note.id] = { nav: markNav, hist: hist.length >= 2 ? hist : [1, markNav] };
  });
  return marks;
};

const normalizeNotes = (portfolioPayload, snapshot) => {
  const backendNotes = normalizeArray(portfolioPayload?.instruments);
  if (backendNotes.length) {
    return backendNotes.map(note => ({
      ...note,
      signal: noteSignalFromBackend(note),
      name: note.name || note.title || note.instrumentType || 'Spread note',
      form: note.form || note.spreadArchetype || note.instrumentType || 'spread',
      thesis: note.thesis || note.copyingSpread || note.statusReason || 'Backend generated compute/energy spread expression.',
      tenor: note.tenor || 'rolling paper basket',
      replay: note.replay || {},
      legs: normalizeArray(note.legs),
      directLegs: normalizeArray(note.directLegs),
      collateralNeeded: normalizeArray(note.collateralNeeded),
      pricedSymbols: normalizeArray(note.pricedSymbols),
      missingSymbols: normalizeArray(note.missingSymbols),
      assetBacked: Boolean(note.assetBacked),
    }));
  }
  const menu = normalizeArray(readPath(snapshot, ['synthetic_instrument', 'outputs', 'syndicated_instrument_menu'], []));
  return menu.map((row, idx) => ({
    id: `${row.instrument_type || 'spread-note'}-${idx}`,
    instrumentType: row.instrument_type || '',
    basketId: row.basket_id || '',
    name: row.title || row.instrument_type || 'Spread note',
    form: row.spread_archetype || row.instrument_type || 'spread',
    signal: noteSignalFromBackend(row),
    latestSignal: row.latest_signal || 'MONITOR',
    status: row.status || 'MONITOR_ONLY',
    statusReason: row.status_reason || '',
    thesis: row.payoff || row.copying_spread || '',
    copyingSpread: row.copying_spread || '',
    tenor: row.direct_leg_target || 'rolling paper basket',
    assetBacked: Boolean(row.asset_backed),
    collateralStatus: row.collateral_status || 'not_asset_backed_v0',
    collateralNeeded: normalizeArray(row.collateral_needed),
    circleAskUsdc: num(row.circle_testnet_ask_usdc),
    markNav: 1 + num(row.total_return_pct) / 100,
    hist: [1, 1 + num(row.total_return_pct) / 100],
    totalReturnPct: num(row.total_return_pct),
    return5dPct: num(readPath(row, ['trailing_returns', '5d', 'return_pct'], 0)),
    return1mPct: num(readPath(row, ['trailing_returns', '1m', 'return_pct'], 0)),
    winRate: num(row.win_rate),
    maxDrawdownPct: num(row.max_drawdown_pct),
    replay: row.paper_trade_replay || {},
    legs: normalizeArray(row.priced_symbols).map(symbol => ({ sym: symbol, name: symbol, side: 'basket', role: 'priced hedge leg' })),
    directLegs: [],
    pricedSymbols: normalizeArray(row.priced_symbols),
    missingSymbols: normalizeArray(row.missing_symbols),
    arcGate: row.arc_gate || 'LOCKED_UNTIL_JUDGE_EXECUTE',
  }));
};

const normalizeSpread = (snapshot, notes) => {
  const spreadLatest = readPath(snapshot, ['spread', 'latest'], {});
  const signalLatest = readPath(snapshot, ['signal', 'latest'], {});
  const best = normalizeArray(notes).find(n => n.signal === 'ENTER') || normalizeArray(notes)[0] || {};
  const hist = normalizeArray(best.hist).map(v => num(v)).filter(v => v > 0);
  const history = hist.length >= 2 ? hist : [1, num(best.markNav, 1)];
  const mean = history.reduce((a, b) => a + b, 0) / history.length;
  const variance = history.reduce((a, b) => a + (b - mean) ** 2, 0) / Math.max(history.length - 1, 1);
  const std = Math.sqrt(variance) || 0.001;
  const cur = history[history.length - 1] || 1;
  const z = num(signalLatest.z, (cur - mean) / std);
  let regime = 'NEUTRAL';
  if ((best.signal || '') === 'ENTER') regime = 'ENTER_WINDOW';
  else if ((best.signal || '') === 'CLOSE_OR_AVOID') regime = 'CLOSE_OR_AVOID';
  else if (z > 1.5) regime = 'RICH';
  else if (z < -1.5) regime = 'CHEAP';
  return {
    spread: {
      k: num(spreadLatest.k, 0.5),
      kwh: num(spreadLatest.kwh, 0.7),
      history,
      latest: spreadLatest,
      signal: signalLatest,
      bestInstrumentId: best.id || '',
    },
    stats: {
      mean,
      std,
      cur,
      z,
      regime,
      electricity: num(spreadLatest.electricity_per_mwh, 0),
      compute: num(spreadLatest.compute_per_gpu_hr, 0),
    },
  };
};

const normalizeIndexRows = (rows, kind) => normalizeArray(rows).map((row, idx) => ({
  ...row,
  id: row.id || row.archetype_id || row.family_id || `${kind}-${idx}`,
  label: row.label || row.name || formName(row.archetype_id || row.id) || `${kind} index`,
  status: row.status || row.evidence_level || 'planned',
  family: row.family || '',
  tradeability: row.tradeability || '',
  tradeabilityLabel: row.tradeability_label || '',
  copyRole: row.copy_role || '',
  canMarkToMarket: Boolean(row.can_mark_to_market),
  canBeDirectLeg: Boolean(row.can_be_direct_leg),
  requiresPremiumGate: Boolean(row.requires_premium_gate),
  requiresJudge: Boolean(row.requires_judge),
  role: row.role || row.formula || row.oil_analogy || row.venue || row.source || '',
  source: row.source || row.venue || row.provider || '',
  description: row.description || row.desc || row.trade_rule || row.formula || '',
}));

const normalizeDirectInventory = (rows) => normalizeArray(rows).map(row => ({
  ...row,
  surface: row.surface || '',
  instrument: row.instrument || '',
  slug: row.leg_slug || row.slug || row.instrument || '',
  displayName: row.leg_title || row.display_label || row.title || row.instrument || 'research leg',
  description: row.leg_description || row.description || '',
  directPairRole: row.direct_pair_role || row.pair_role || row.leg_role || row.role || '',
  direction: row.direction || '',
  pricingStatus: row.pricing_status || row.label || '',
  pricingStatusLabel: row.pricing_status_label || row.external_proxy_status_label || row.pricing_status || row.label || 'watchlist',
  endDate: row.leg_end_date || row.end_date || row.endDate || '',
  externalProxySymbol: row.external_proxy_symbol || '',
  externalProxyTitle: row.external_proxy_title || '',
  externalProxyLastPrice: row.external_proxy_last_price === '' || row.external_proxy_last_price === undefined ? null : num(row.external_proxy_last_price, null),
  externalProxySource: row.external_proxy_source || '',
  externalProxyStale: Boolean(row.external_proxy_stale),
  externalProxyRole: row.external_proxy_role || '',
  externalProxyRegularMarketTime: row.external_proxy_regular_market_time || '',
  connection: row.leg_connection || '',
}));

const normalizeProfitabilityRows = (rows) => normalizeArray(rows).map(row => ({
  ...row,
  id: row.archetype_id || row.basket_id || row.label || '',
  label: row.label || formName(row.archetype_id),
  status: row.profitability_status || row.tradability_action || 'MONITOR',
  action: row.latest_signal || row.current_action || 'MONITOR',
  replayStatus: row.spread_replay_status || '',
  oosStatus: row.oos_status || row.spread_oos_status || '',
  paper5d: num(row.paper_5d_return_pct, 0),
  paper1m: num(row.paper_1m_return_pct, 0),
  paperTotal: num(row.paper_total_return_pct, 0),
  latestPnl: row.latest_paper_pnl_usdc === '' || row.latest_paper_pnl_usdc === undefined ? null : num(row.latest_paper_pnl_usdc, 0),
  ticketPnl: row.paper_trade_total_pnl_usdc === '' || row.paper_trade_total_pnl_usdc === undefined ? null : num(row.paper_trade_total_pnl_usdc, 0),
  winRate: num(row.paper_win_rate || row.spread_replay_win_rate, 0),
  reason: row.signal_reason || row.current_action_reason || row.reason || '',
  pricedSymbols: normalizeArray(row.priced_symbols),
  missingSymbols: normalizeArray(row.missing_symbols),
  supportsFreshBuy: Boolean(row.supports_fresh_buy),
  requiresClose: Boolean(row.requires_close_or_avoid),
}));

const normalizePnl = (snapshot) => {
  const pnl = snapshot?.pnl || {};
  return {
    ...pnl,
    hasReconciled: Boolean(pnl.has_reconciled),
    statusLabel: pnl.status_label || (pnl.has_reconciled ? 'Settled PnL' : 'No settled PnL'),
    totalDisplay: pnl.display_total || fmtSigned(pnl.total || 0, 4),
    tradesDisplay: pnl.display_trades || `${pnl.trades || 0} settled`,
    paperTicketTotalDisplay: pnl.paper_ticket_total_pnl_usdc === '' || pnl.paper_ticket_total_pnl_usdc === undefined
      ? 'No paper tickets'
      : fmtSigned(pnl.paper_ticket_total_pnl_usdc),
  };
};

const normalizeIndexCatalog = (snapshot) => {
  const rows = normalizeArray(readPath(snapshot, ['synthetic_instrument', 'outputs', 'spread_archetype_trade_map'], []));
  const spreadFamilies = snapshot?.spread_families || {};
  const rawCatalog = spreadFamilies.index_catalog || {};
  const profitabilityLedger = snapshot?.profitability_ledger || readPath(snapshot, ['synthetic_instrument', 'outputs', 'spread_profitability_ledger'], {});
  const spreadForms = rows.length
    ? rows.map(row => ({
        id: row.archetype_id,
        name: row.label || formName(row.archetype_id),
        desc: row.formula || row.oil_analogy || row.tradability_reason || '',
        headline: row.rank === 1 || row.tradability_action === 'PAPER_BUY_ONLY',
        status: row.tradability_action || 'MONITOR',
        oilAnalogy: row.oil_analogy || '',
        replayStatus: row.replay_status || '',
        tradabilityReason: row.tradability_reason || '',
        selectedExpression: row.selected_expression || {},
      }))
    : DEFAULT_SPREAD_FORMS;
  const publicHedges = normalizeArray(snapshot?.public_hedges).map(row => ({
    sym: row.instrument || row.leg_slug || '',
    name: row.leg_title || row.title || row.instrument || '',
    unit: row.source || row.pricing_status || '',
    value: num(row.last_price),
    changePct: num(row.day_change_pct || row.change_pct),
  })).filter(row => row.sym);
  const direct = normalizeArray(snapshot?.direct_inventory).map(row => ({
    sym: row.leg_slug || row.slug || row.surface || '',
    name: row.leg_title || row.title || '',
    unit: row.surface || '',
    value: row.pricing_status || row.label || 'watch',
    changePct: 0,
  })).filter(row => row.sym);
  return {
    spreadForms,
    publicHedges,
    direct,
    electricityIndexes: normalizeIndexRows(rawCatalog.electricity, 'electricity'),
    computeIndexes: normalizeIndexRows(rawCatalog.compute, 'compute'),
    spreadArchetypes: normalizeIndexRows(rawCatalog.spread_archetypes || spreadFamilies.archetype_scoreboard, 'spread'),
    archetypeScoreboard: normalizeIndexRows(spreadFamilies.archetype_scoreboard, 'spread-score'),
    coverage: spreadFamilies.index_coverage || null,
    tradeMap: rows,
    profitabilityLedger,
    profitabilityRows: normalizeProfitabilityRows(profitabilityLedger.rows),
    venueCopyMatrix: readPath(snapshot, ['synthetic_instrument', 'outputs', 'real_venue_copy_matrix'], {}),
  };
};

const emptyDashboardData = () => {
  const indexCatalog = normalizeIndexCatalog({});
  return {
    connection: { status: 'loading' },
    syntheticInstrument: null,
    directInventory: [],
    publicHedges: [],
    indexCatalog,
    spreadFamilies: {
      families: [],
      archetypeScoreboard: [],
      indexCoverage: null,
      indexCatalog: {
        electricity: indexCatalog.electricityIndexes,
        compute: indexCatalog.computeIndexes,
        spread_archetypes: indexCatalog.spreadArchetypes,
      },
      entryGatePass: false,
    },
    proxyBaskets: { baskets: [], entryGatePass: false },
    venueEvidence: { rows: [] },
    oracleResults: {},
    goalCoverage: { overall_status: 'NEEDS_WORK', overall_score: 0, items: [], summary: '' },
    telegramCampaign: { posts: [], posted_count: 0, total_posts: 0, pending_count: 0 },
    telegramMiniappRelease: { posts: [], posted_count: 0, total_posts: 0, pending_count: 0 },
    pnl: normalizePnl({ pnl: {} }),
    spread: { elec: '0.00', compute: '0.0000', st: '0.0000', source: '', baseElec: null, proxyMovePct: null, powerSharePct: null },
    z: 0,
    direction: 'no_signal',
    verdicts: [],
    positions: [],
    candidates: [],
  };
};

const mapSnapshotToDashboardData = (snapshot) => {
  const spreadLatest = readPath(snapshot, ['spread', 'latest'], {});
  const signalLatest = readPath(snapshot, ['signal', 'latest'], {});
  const elec = num(spreadLatest.electricity_per_mwh, 0);
  const compute = num(spreadLatest.compute_per_gpu_hr, 0);
  const st = num(spreadLatest.S_t, compute - num(spreadLatest.power_cost_per_gpu_hr, 0));
  const directInventory = normalizeDirectInventory(snapshot?.direct_inventory);
  const proxyBaskets = snapshot?.proxy_baskets || {};
  const indexCatalog = normalizeIndexCatalog(snapshot);
  return {
    connection: { status: snapshot?.ok === false ? 'offline' : 'live', generatedAt: snapshot?.generated_at || null },
    syntheticInstrument: snapshot?.synthetic_instrument || null,
    directInventory,
    publicHedges: normalizeArray(snapshot?.public_hedges),
    indexCatalog,
    spreadFamilies: {
      ...(snapshot?.spread_families || {}),
      families: normalizeArray(snapshot?.spread_families?.families),
      archetypeScoreboard: normalizeArray(snapshot?.spread_families?.archetype_scoreboard),
      indexCoverage: snapshot?.spread_families?.index_coverage || null,
      indexCatalog: {
        ...(snapshot?.spread_families?.index_catalog || {}),
        electricity: normalizeArray(snapshot?.spread_families?.index_catalog?.electricity).length
          ? normalizeIndexRows(snapshot?.spread_families?.index_catalog?.electricity, 'electricity')
          : indexCatalog.electricityIndexes,
        compute: normalizeArray(snapshot?.spread_families?.index_catalog?.compute).length
          ? normalizeIndexRows(snapshot?.spread_families?.index_catalog?.compute, 'compute')
          : indexCatalog.computeIndexes,
        spread_archetypes: normalizeArray(snapshot?.spread_families?.index_catalog?.spread_archetypes).length
          ? normalizeIndexRows(snapshot?.spread_families?.index_catalog?.spread_archetypes, 'spread')
          : indexCatalog.spreadArchetypes,
      },
      entryGatePass: Boolean(snapshot?.spread_families?.entry_gate_pass),
      primarySource: snapshot?.spread_families?.primary_source || '',
    },
    proxyBaskets: {
      ...proxyBaskets,
      baskets: normalizeArray(proxyBaskets.baskets),
      entryGatePass: Boolean(proxyBaskets.entry_gate_pass),
    },
    venueEvidence: snapshot?.venue_evidence || { rows: [] },
    oracleResults: snapshot?.oracle || {},
    goalCoverage: snapshot?.goal_coverage || { overall_status: 'NEEDS_WORK', overall_score: 0, items: [], summary: '' },
    telegramCampaign: snapshot?.telegram_campaign || { posts: [], posted_count: 0, total_posts: 0, pending_count: 0 },
    telegramMiniappRelease: snapshot?.telegram_miniapp_release || { posts: [], posted_count: 0, total_posts: 0, pending_count: 0 },
    pnl: normalizePnl(snapshot),
    spread: {
      elec: elec.toFixed(2),
      compute: compute.toFixed(4),
      st: st.toFixed(4),
      source: spreadLatest.electricity_source || spreadLatest.compute_source || '',
      baseElec: spreadLatest.electricity_base_per_mwh === '' || spreadLatest.electricity_base_per_mwh === undefined ? null : num(spreadLatest.electricity_base_per_mwh, null),
      proxyMovePct: spreadLatest.electricity_proxy_weighted_return_pct === '' || spreadLatest.electricity_proxy_weighted_return_pct === undefined ? null : num(spreadLatest.electricity_proxy_weighted_return_pct, null),
      powerSharePct: spreadLatest.power_cost_share_pct === '' || spreadLatest.power_cost_share_pct === undefined ? null : num(spreadLatest.power_cost_share_pct, null),
    },
    z: num(signalLatest.z, 0),
    direction: signalLatest.direction || 'no_signal',
    verdicts: normalizeArray(snapshot?.verdicts),
    positions: normalizeArray(snapshot?.positions),
    candidates: directInventory,
  };
};

function usePowerDeskData(refreshRate) {
  const [stateValue, setStateValue] = React.useState({
    loading: true,
    error: '',
    snapshot: null,
    account: window.__operatorAccount || null,
    accountMode: window.__operatorAccountMode || null,
    portfolio: null,
    notes: [],
    marks: {},
    spread: { k: 0.5, kwh: 0.7, history: [1, 1], latest: {}, signal: {} },
    stats: { mean: 1, std: 0.001, cur: 1, z: 0, regime: 'NEUTRAL', electricity: 0, compute: 0 },
    indexCatalog: { spreadForms: DEFAULT_SPREAD_FORMS, publicHedges: [], direct: [] },
    goalCoverage: { overall_status: 'NEEDS_WORK', overall_score: 0, items: [], summary: '' },
    refreshedAt: null,
  });

  const refresh = React.useCallback(async () => {
    if (document.visibilityState === 'hidden') return;
    try {
      const [snapshot, accountBody] = await Promise.all([
        apiJson('/api/snapshot'),
        apiJson('/api/account'),
      ]);
      const account = accountBody.account || null;
      if (typeof emitOperatorAccount === 'function') emitOperatorAccount(account, accountBody.mode);
      let portfolio = null;
      if (account) {
        try {
          portfolio = await apiJson('/api/account/portfolio', { timeoutMs: 5000 });
        } catch (_portfolioErr) {
          portfolio = null;
        }
      }
      const notes = normalizeNotes(portfolio, snapshot);
      const marks = buildMarks(notes);
      const spreadState = normalizeSpread(snapshot, notes);
      setStateValue({
        loading: false,
        error: '',
        snapshot,
        account,
        accountMode: accountBody.mode || null,
        portfolio,
        notes,
        marks,
        spread: spreadState.spread,
        stats: spreadState.stats,
        indexCatalog: normalizeIndexCatalog(snapshot),
        goalCoverage: snapshot?.goal_coverage || { overall_status: 'NEEDS_WORK', overall_score: 0, items: [], summary: '' },
        refreshedAt: new Date().toISOString(),
      });
    } catch (err) {
      setStateValue(prev => ({ ...prev, loading: false, error: String(err.message || err) }));
    }
  }, []);

  React.useEffect(() => {
    refresh();
    const iv = setInterval(refresh, Math.max(10000, Number(refreshRate || 10000)));
    const onVisible = () => {
      if (document.visibilityState === 'visible') refresh();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      clearInterval(iv);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [refresh, refreshRate]);

  React.useEffect(() => {
    const onAccount = () => refresh();
    window.addEventListener('botozen:account', onAccount);
    return () => window.removeEventListener('botozen:account', onAccount);
  }, [refresh]);

  return { ...stateValue, refresh };
}

const openPaperPosition = async ({ instrumentId, notionalUsdc }) => apiJson('/api/account/portfolio/open', {
  method: 'POST',
  body: JSON.stringify({ instrument_id: instrumentId, notional_usdc: notionalUsdc }),
});

const closePaperPosition = async ({ positionId }) => apiJson('/api/account/portfolio/close', {
  method: 'POST',
  body: JSON.stringify({ position_id: positionId }),
});

Object.assign(window, {
  fmtUsd, fmtSigned, fmtPct, fmtNav,
  SIGNAL_META, REGIME_META, DEFAULT_SPREAD_FORMS,
  formName, prettyLabel, sourceLabel, surfaceIcon, formatEventDate,
  apiJson, normalizeNotes, normalizeIndexCatalog, normalizeDirectInventory,
  normalizeProfitabilityRows, emptyDashboardData, mapSnapshotToDashboardData,
  usePowerDeskData,
  openPaperPosition, closePaperPosition,
});
