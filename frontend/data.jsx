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
  { id: 'locational_power_compute_basis', name: 'Locational basis', desc: 'Regional compute capacity versus grid hub pricing' },
  { id: 'grid_event_hazard_spread', name: 'Grid-event hazard', desc: 'Scarcity, outage, and siting-event exposure' },
  { id: 'miner_margin_power_pair', name: 'Miner-margin pair', desc: 'Proof-of-work revenue beta versus electricity cost' },
];

const normalizeArray = (value) => Array.isArray(value) ? value : [];
const num = (value, fallback = 0) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
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
  const resp = await fetch(path, {
    credentials: 'same-origin',
    cache: 'no-store',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  const body = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(body.error || `HTTP ${resp.status}`);
  return body;
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

const normalizeIndexCatalog = (snapshot) => {
  const rows = normalizeArray(readPath(snapshot, ['synthetic_instrument', 'outputs', 'spread_archetype_trade_map'], []));
  const spreadForms = rows.length
    ? rows.map(row => ({
        id: row.archetype_id,
        name: row.label || formName(row.archetype_id),
        desc: row.formula || row.oil_analogy || row.tradability_reason || '',
        headline: row.rank === 1 || row.tradability_action === 'PAPER_BUY_ONLY',
        status: row.tradability_action || 'MONITOR',
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
  return { spreadForms, publicHedges, direct };
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
    refreshedAt: null,
  });

  const refresh = React.useCallback(async () => {
    try {
      const [snapshot, accountBody, portfolio] = await Promise.all([
        apiJson('/api/snapshot'),
        apiJson('/api/account'),
        apiJson('/api/account/portfolio'),
      ]);
      const account = accountBody.account || null;
      if (typeof emitOperatorAccount === 'function') emitOperatorAccount(account, accountBody.mode);
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
        refreshedAt: new Date().toISOString(),
      });
    } catch (err) {
      setStateValue(prev => ({ ...prev, loading: false, error: String(err.message || err) }));
    }
  }, []);

  React.useEffect(() => {
    refresh();
    const iv = setInterval(refresh, Math.max(2000, Number(refreshRate || 5000)));
    return () => clearInterval(iv);
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
  formName, apiJson, normalizeNotes, usePowerDeskData,
  openPaperPosition, closePaperPosition,
});
