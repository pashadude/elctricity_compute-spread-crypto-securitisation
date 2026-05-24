/* Botozen Power - Server Operator Account */

const DEMO_OPERATOR_WALLET = '0x7a3B4C6D8E9F1029384756aBcDEF1234567890aB';
const DEMO_OPERATOR_TX = '0x3fbd4a19e88c0e2bf98d4c0f6134a946a3e22f19ea2346e8076bb4ac9f789678';

window.__operatorAccount = null;
window.__operatorAccountMode = null;

const maskAccountValue = (value, head = 8, tail = 6) => {
  const s = String(value || '');
  if (!s || s.length <= head + tail + 3) return s || 'not set';
  return `${s.slice(0, head)}...${s.slice(-tail)}`;
};

const formatAccountDate = (value) => {
  if (!value) return 'Pending';
  try {
    return new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  } catch {
    return 'Pending';
  }
};

const emitOperatorAccount = (account, mode) => {
  window.__operatorAccount = account || null;
  if (mode) window.__operatorAccountMode = mode;
  window.dispatchEvent(new CustomEvent('botozen:account', { detail: account || null }));
};

const readDemoOperatorAccount = () => window.__operatorAccount || null;

const accountRequest = async (path, options = {}) => {
  const resp = await fetch(path, {
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  const body = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(body.error || `HTTP ${resp.status}`);
  if (Object.prototype.hasOwnProperty.call(body, 'account')) {
    emitOperatorAccount(body.account, body.mode);
  }
  return body;
};

const refreshOperatorAccount = async () => {
  const body = await accountRequest('/api/account');
  return body.account || null;
};

const createDemoOperatorAccount = async ({ plan, wallet, txHash } = {}) => {
  const body = await accountRequest('/api/account/operator/demo-payment', {
    method: 'POST',
    body: JSON.stringify({
      plan_id: plan?.id || 'operator',
      wallet_address: wallet || DEMO_OPERATOR_WALLET,
      tx_hash: txHash || DEMO_OPERATOR_TX,
    }),
  });
  return body.account || null;
};

const clearDemoOperatorAccount = async () => {
  await accountRequest('/api/account/logout', { method: 'POST', body: '{}' });
  emitOperatorAccount(null);
  return null;
};

refreshOperatorAccount().catch(() => emitOperatorAccount(null));

const AccountMetric = ({ label, value, accent = THEME.primary[400] }) => (
  <div style={{
    padding: '16px',
    background: THEME.bg.elevated,
    border: `1px solid ${THEME.border.subtle}`,
    borderRadius: '10px',
    minWidth: 0,
  }}>
    <div style={{ fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.muted, marginBottom: '6px' }}>{label}</div>
    <div style={{
      fontFamily: THEME.font.mono,
      fontSize: '15px',
      fontWeight: 700,
      color: accent,
      overflowWrap: 'anywhere',
    }}>{value}</div>
  </div>
);

const AccountPage = ({ setPage }) => {
  const [account, setAccount] = React.useState(readDemoOperatorAccount);
  const [mode, setMode] = React.useState(window.__operatorAccountMode);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState('');
  const isMobile = useIsMobile(700);

  React.useEffect(() => {
    const refresh = (event) => {
      if (event?.type === 'botozen:account') {
        setAccount(event.detail || null);
        setMode(window.__operatorAccountMode || null);
      } else {
        setAccount(readDemoOperatorAccount());
      }
    };
    window.addEventListener('storage', refresh);
    window.addEventListener('botozen:account', refresh);
    refreshOperatorAccount()
      .catch(err => setError(String(err.message || err)))
      .finally(() => setLoading(false));
    return () => {
      window.removeEventListener('storage', refresh);
      window.removeEventListener('botozen:account', refresh);
    };
  }, []);

  if (loading) {
    return (
      <main style={{ padding: isMobile ? '38px 16px' : '72px 32px', minHeight: 'calc(100vh - 64px)' }}>
        <div style={{ maxWidth: '880px', margin: '0 auto' }}>
          <Card glow style={{ padding: isMobile ? '24px' : '36px' }}>
            <SectionLabel>Operator Account</SectionLabel>
            <h1 style={{ fontFamily: THEME.font.heading, fontSize: '34px', color: THEME.text.primary, margin: '0 0 10px' }}>Loading account...</h1>
            <p style={{ fontFamily: THEME.font.body, color: THEME.text.secondary, margin: 0 }}>Checking the signed server session.</p>
          </Card>
        </div>
      </main>
    );
  }

  if (!account) {
    return (
      <main style={{ padding: isMobile ? '38px 16px' : '72px 32px', minHeight: 'calc(100vh - 64px)' }}>
        <div style={{ maxWidth: '880px', margin: '0 auto' }}>
          <SectionLabel>Operator Account</SectionLabel>
          <Card glow style={{ padding: isMobile ? '24px' : '36px' }}>
            <Badge color="amber" style={{ marginBottom: '16px' }}>No paid server account</Badge>
            <h1 style={{
              fontFamily: THEME.font.heading,
              fontSize: isMobile ? '30px' : '38px',
              lineHeight: 1.1,
              fontWeight: 800,
              letterSpacing: 0,
              color: THEME.text.primary,
              margin: '0 0 14px',
            }}>
              Pay 5 test USDC to create your Operator workspace
            </h1>
            <p style={{ fontFamily: THEME.font.body, fontSize: '16px', lineHeight: 1.7, color: THEME.text.secondary, maxWidth: '650px', margin: '0 0 14px' }}>
              Paid access is now owned by the backend: it persists the account, sets a signed HttpOnly session cookie, and exposes account status through <MonoText>/api/account</MonoText>.
            </p>
            {error && <p style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.amber[400], margin: '0 0 18px' }}>{error}</p>}
            {mode?.demo_payments_enabled === false && (
              <p style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.amber[400], margin: '0 0 18px' }}>
                Demo payments are disabled. Use the Circle webhook path to activate Operator access.
              </p>
            )}
            <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
              <GlowButton onClick={() => {
                setPage('landing');
                setTimeout(() => document.getElementById('pricing-section')?.scrollIntoView?.({ behavior: 'smooth', block: 'start' }), 120);
              }}>Choose Operator</GlowButton>
              <GlowButton variant="ghost" onClick={() => setPage('dashboard')}>Open Read-only Dashboard</GlowButton>
            </div>
          </Card>
        </div>
      </main>
    );
  }

  const entitlementLabels = {
    package_dashboard: 'Package dashboard',
    actionable_alerts: 'Actionable package alerts',
    telegram_scan_commands: 'Telegram scan commands',
    oracle_backtest_view: 'Saved oracle backtest view',
    arc_testnet_wrap_controls: 'Arc Testnet wrap controls',
  };
  const payment = account.payment || {};
  const productionReady = Boolean(mode?.session_secret_configured && mode?.secure_cookie);

  return (
    <main style={{ padding: isMobile ? '32px 16px 48px' : '56px 32px 72px', minHeight: 'calc(100vh - 64px)' }}>
      <div style={{ maxWidth: '1080px', margin: '0 auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '16px', alignItems: 'flex-start', marginBottom: '22px', flexWrap: 'wrap' }}>
          <div>
            <SectionLabel>Operator Account</SectionLabel>
            <h1 style={{
              fontFamily: THEME.font.heading,
              fontSize: isMobile ? '32px' : '44px',
              lineHeight: 1.05,
              fontWeight: 800,
              letterSpacing: 0,
              color: THEME.text.primary,
              margin: '0 0 10px',
            }}>
              Personal Operator workspace
            </h1>
            <p style={{ fontFamily: THEME.font.body, fontSize: '15px', color: THEME.text.secondary, lineHeight: 1.6, margin: 0, maxWidth: '650px' }}>
              This account is persisted by the backend and restored with a signed HttpOnly session cookie. The frontend no longer grants paid access from local browser storage.
            </p>
          </div>
          <Badge color={account.status === 'active' ? 'primary' : 'amber'} style={{ marginTop: '6px' }}>{String(account.status || 'pending').toUpperCase()}</Badge>
        </div>

        <Card glow style={{ marginBottom: '18px' }}>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))',
            gap: '12px',
          }}>
            <AccountMetric label="Account ID" value={account.id} />
            <AccountMetric label="Plan" value={`${account.planName} - $${account.priceUsd}/mo`} />
            <AccountMetric label="Paid" value={`${account.testUsdc} test USDC`} accent={THEME.amber[400]} />
            <AccountMetric label="Renews" value={formatAccountDate(account.renewsAt)} />
          </div>
        </Card>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '18px', alignItems: 'start' }}>
          <Card>
            <SectionLabel>Access</SectionLabel>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {(account.entitlements || []).map(item => (
                <div key={item} style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  gap: '14px',
                  alignItems: 'center',
                  padding: '12px 0',
                  borderBottom: `1px solid ${THEME.border.subtle}`,
                }}>
                  <span style={{ fontFamily: THEME.font.body, fontSize: '14px', color: THEME.text.secondary }}>
                    {entitlementLabels[item] || item}
                  </span>
                  <Badge color="primary">enabled</Badge>
                </div>
              ))}
            </div>
            <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', marginTop: '22px' }}>
              <GlowButton onClick={() => setPage('dashboard')}>Open Dashboard</GlowButton>
              <GlowButton variant="ghost" onClick={() => setPage('telegram')}>Open Telegram Demo</GlowButton>
            </div>
          </Card>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
            <Card>
              <SectionLabel>Wallet</SectionLabel>
              <div style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.muted, marginBottom: '8px' }}>Payer address</div>
              <MonoText style={{ display: 'block', overflowWrap: 'anywhere', fontSize: '13px' }}>{account.walletAddress}</MonoText>
              <Divider style={{ margin: '16px 0' }} />
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px' }}>
                <span style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.secondary }}>Network</span>
                <Badge color="primary">{account.network}</Badge>
              </div>
            </Card>

            <Card>
              <SectionLabel>Payment Receipt</SectionLabel>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', marginBottom: '10px' }}>
                <span style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.secondary }}>Provider</span>
                <Badge color={payment.source === 'circle_webhook' ? 'primary' : 'amber'}>{payment.source === 'circle_webhook' ? 'Circle webhook' : 'Demo testnet'}</Badge>
              </div>
              <div style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.muted, marginBottom: '8px' }}>Transaction</div>
              <MonoText style={{ display: 'block', overflowWrap: 'anywhere', fontSize: '13px' }}>{maskAccountValue(account.txHash, 10, 8)}</MonoText>
              <div style={{ fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.muted, lineHeight: 1.5, marginTop: '12px' }}>
                Production mode should disable demo payments and activate accounts only from verified Circle webhook events.
              </div>
            </Card>

            <Card>
              <SectionLabel>Production Readiness</SectionLabel>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px' }}>
                  <span style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.secondary }}>Session secret</span>
                  <Badge color={mode?.session_secret_configured ? 'primary' : 'amber'}>{mode?.session_secret_configured ? 'set' : 'missing'}</Badge>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px' }}>
                  <span style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.secondary }}>Secure cookie</span>
                  <Badge color={mode?.secure_cookie ? 'primary' : 'amber'}>{mode?.secure_cookie ? 'on' : 'off'}</Badge>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px' }}>
                  <span style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.secondary }}>Circle signatures</span>
                  <Badge color={mode?.circle_webhook_signature_required ? 'primary' : 'amber'}>{mode?.circle_webhook_signature_required ? 'required' : 'disabled'}</Badge>
                </div>
                <Divider />
                <Badge color={productionReady ? 'primary' : 'amber'}>{productionReady ? 'ready for HTTPS' : 'finish env setup'}</Badge>
              </div>
            </Card>

            <GlowButton variant="ghost" style={{ justifyContent: 'center' }} onClick={() => clearDemoOperatorAccount()}>
              Sign Out
            </GlowButton>
          </div>
        </div>
      </div>
    </main>
  );
};

Object.assign(window, {
  DEMO_OPERATOR_WALLET,
  DEMO_OPERATOR_TX,
  readDemoOperatorAccount,
  refreshOperatorAccount,
  createDemoOperatorAccount,
  clearDemoOperatorAccount,
  AccountPage,
});
