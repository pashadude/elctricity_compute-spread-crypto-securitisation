/* Arc Compute Sec — Theme & Shared Components */

const THEME = {
  bg: { deep: '#060a08', base: '#0B0F0E', surface: '#111916', elevated: '#172119', hover: '#1E2D25' },
  border: { subtle: '#1a2a21', default: '#1E2D25', strong: '#2a3d32' },
  primary: { 50: '#EFFDF5', 100: '#D9FBE8', 200: '#B3F5D1', 300: '#75EDAE', 400: '#00DC82', 500: '#00C16A', 600: '#00A155', 700: '#007F45', 800: '#016538', 900: '#0A5331' },
  amber: { 400: '#F59E0B', 500: '#D97706' },
  red: { 400: '#EF4444', 500: '#DC2626' },
  blue: { 400: '#60A5FA', 500: '#3B82F6' },
  purple: { 400: '#A78BFA', 500: '#8B5CF6' },
  text: { primary: '#FFFFFF', secondary: '#A1B5AB', muted: '#6B8578', faint: '#3D5548' },
  font: { heading: "'Space Grotesk', sans-serif", body: "'DM Sans', sans-serif", mono: "'JetBrains Mono', monospace" },
  radius: { sm: '6px', md: '10px', lg: '16px', xl: '24px' },
};

const useViewport = () => {
  const read = () => ({
    width: window.innerWidth || document.documentElement.clientWidth || 1024,
    height: window.innerHeight || document.documentElement.clientHeight || 768,
  });
  const [viewport, setViewport] = React.useState(read);

  React.useEffect(() => {
    const onResize = () => setViewport(read());
    window.addEventListener('resize', onResize);
    window.addEventListener('orientationchange', onResize);
    return () => {
      window.removeEventListener('resize', onResize);
      window.removeEventListener('orientationchange', onResize);
    };
  }, []);

  return viewport;
};

const useIsMobile = (breakpoint = 760) => useViewport().width <= breakpoint;

/* ── Shared tiny components ── */

const Badge = ({ children, color = 'primary', style, ...props }) => {
  const colors = {
    primary: { bg: THEME.primary[400] + '18', text: THEME.primary[400], border: THEME.primary[400] + '30' },
    amber: { bg: THEME.amber[400] + '18', text: THEME.amber[400], border: THEME.amber[400] + '30' },
    red: { bg: THEME.red[400] + '18', text: THEME.red[400], border: THEME.red[400] + '30' },
    blue: { bg: THEME.blue[400] + '18', text: THEME.blue[400], border: THEME.blue[400] + '30' },
    purple: { bg: THEME.purple[400] + '18', text: THEME.purple[400], border: THEME.purple[400] + '30' },
    muted: { bg: '#ffffff08', text: THEME.text.secondary, border: '#ffffff12' },
  };
  const c = colors[color] || colors.primary;
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: '4px',
      padding: '3px 10px', borderRadius: '100px', fontSize: '11px', fontWeight: 600,
      fontFamily: THEME.font.mono, letterSpacing: '0.03em',
      background: c.bg, color: c.text, border: `1px solid ${c.border}`,
      ...style
    }} {...props}>{children}</span>
  );
};

const Card = ({ children, style, glow, hoverable, ...props }) => {
  const [hovered, setHovered] = React.useState(false);
  return (
    <div
      onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}
      style={{
        background: THEME.bg.surface,
        border: `1px solid ${hovered && hoverable ? THEME.border.strong : THEME.border.subtle}`,
        borderRadius: THEME.radius.lg,
        padding: '24px',
        transition: 'all 0.3s ease',
        position: 'relative',
        overflow: 'hidden',
        ...(glow && { boxShadow: `0 0 60px ${THEME.primary[400]}08` }),
        ...(hovered && hoverable && { transform: 'translateY(-2px)', boxShadow: `0 8px 32px ${THEME.primary[400]}10` }),
        ...style
      }} {...props}>{children}</div>
  );
};

const GlowButton = ({ children, onClick, variant = 'primary', size = 'md', style, disabled, ...props }) => {
  const [hovered, setHovered] = React.useState(false);
  const sizes = { sm: { px: 16, py: 8, fs: 13 }, md: { px: 24, py: 12, fs: 14 }, lg: { px: 32, py: 16, fs: 16 } };
  const s = sizes[size];
  const isPrimary = variant === 'primary';
  return (
    <button
      onClick={onClick} disabled={disabled}
      onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: '8px',
        padding: `${s.py}px ${s.px}px`, borderRadius: '10px',
        fontSize: `${s.fs}px`, fontWeight: 600, fontFamily: THEME.font.body,
        cursor: disabled ? 'not-allowed' : 'pointer', border: 'none',
        transition: 'all 0.25s ease', letterSpacing: 0,
        opacity: disabled ? 0.5 : 1,
        ...(isPrimary ? {
          background: hovered ? THEME.primary[300] : THEME.primary[400],
          color: '#000', boxShadow: hovered ? `0 0 32px ${THEME.primary[400]}40` : 'none',
        } : {
          background: hovered ? THEME.bg.hover : THEME.bg.elevated,
          color: THEME.text.primary, border: `1px solid ${THEME.border.default}`,
        }),
        ...style
      }} {...props}>{children}</button>
  );
};

const MonoText = ({ children, style }) => (
  <span style={{ fontFamily: THEME.font.mono, fontSize: '13px', color: THEME.primary[400], ...style }}>{children}</span>
);

const SectionLabel = ({ children, style }) => (
  <div style={{
    fontFamily: THEME.font.mono, fontSize: '11px', fontWeight: 600,
    letterSpacing: '0.12em', textTransform: 'uppercase',
    color: THEME.primary[400], marginBottom: '12px', ...style
  }}>{children}</div>
);

const Divider = ({ style }) => (
  <div style={{ height: '1px', background: THEME.border.subtle, width: '100%', ...style }}></div>
);

/* ── Nav ── */
const readNavOperatorAccount = () => window.readDemoOperatorAccount?.() || window.__operatorAccount || null;

const Nav = ({ page, setPage }) => {
  const [scrolled, setScrolled] = React.useState(false);
  const [account, setAccount] = React.useState(readNavOperatorAccount);
  const isMobile = useIsMobile(760);

  React.useEffect(() => {
    const el = document.getElementById('app-scroll');
    if (!el) return;
    const h = () => setScrolled(el.scrollTop > 20);
    el.addEventListener('scroll', h);
    return () => el.removeEventListener('scroll', h);
  }, []);

  React.useEffect(() => {
    const refresh = (event) => {
      if (event?.type === 'botozen:account') setAccount(event.detail || null);
      else setAccount(readNavOperatorAccount());
    };
    window.addEventListener('storage', refresh);
    window.addEventListener('botozen:account', refresh);
    return () => {
      window.removeEventListener('storage', refresh);
      window.removeEventListener('botozen:account', refresh);
    };
  }, []);

  const links = [
    { id: 'landing', label: 'Home' },
    { id: 'dashboard', label: 'Dashboard' },
    { id: 'telegram', label: 'Telegram App' },
    ...(account ? [{ id: 'account', label: 'Account' }] : []),
  ];

  return (
    <nav style={{
      position: 'sticky', top: 0, zIndex: 100,
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      gap: isMobile ? '10px' : '16px',
      flexWrap: isMobile ? 'wrap' : 'nowrap',
      padding: isMobile ? '10px 14px' : '0 32px',
      minHeight: '64px',
      background: scrolled ? THEME.bg.base + 'ee' : 'transparent',
      backdropFilter: scrolled ? 'blur(16px)' : 'none',
      borderBottom: scrolled ? `1px solid ${THEME.border.subtle}` : '1px solid transparent',
      transition: 'all 0.3s ease',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer', minWidth: 0 }} onClick={() => setPage('landing')}>
        <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
          <path d="M14 2L2 26h8l4-8 4 8h8L14 2z" fill={THEME.primary[400]} />
          <path d="M14 10l-4 8h8l-4-8z" fill={THEME.primary[300]} opacity="0.6" />
        </svg>
        <span style={{ fontFamily: THEME.font.heading, fontWeight: 700, fontSize: isMobile ? '16px' : '18px', color: THEME.text.primary, letterSpacing: 0, whiteSpace: 'nowrap' }}>
          arc<span style={{ color: THEME.primary[400] }}>·</span>compute
        </span>
      </div>
      <div style={{
        display: 'flex', gap: '4px',
        order: isMobile ? 3 : 0,
        width: isMobile ? '100%' : 'auto',
        overflowX: isMobile ? 'auto' : 'visible',
        paddingBottom: isMobile ? '2px' : 0,
      }}>
        {links.map(l => (
          <button key={l.id} onClick={() => setPage(l.id)} style={{
            padding: '8px 16px', borderRadius: '8px', border: 'none', cursor: 'pointer',
            fontFamily: THEME.font.body, fontSize: '14px', fontWeight: 500,
            background: page === l.id ? THEME.primary[400] + '15' : 'transparent',
            color: page === l.id ? THEME.primary[400] : THEME.text.secondary,
            transition: 'all 0.2s',
            whiteSpace: 'nowrap',
            flex: '0 0 auto',
          }}>{l.label}</button>
        ))}
      </div>
      <GlowButton size="sm" onClick={() => setPage(account ? 'account' : 'dashboard')} style={{ flexShrink: 0 }}>
        {account ? 'Operator Account' : 'Launch App'}
      </GlowButton>
    </nav>
  );
};

/* ── Sparkline ── */
const Sparkline = ({ data, width = 120, height = 32, color = THEME.primary[400], style }) => {
  if (!data || data.length < 2) return null;
  const min = Math.min(...data), max = Math.max(...data);
  const range = max - min || 1;
  const points = data.map((v, i) => {
    const x = (i / (data.length - 1)) * width;
    const y = height - ((v - min) / range) * (height - 4) - 2;
    return `${x},${y}`;
  }).join(' ');
  const areaPoints = points + ` ${width},${height} 0,${height}`;
  return (
    <svg width={width} height={height} style={style}>
      <defs>
        <linearGradient id={`sg-${color.replace('#','')}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.3" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={areaPoints} fill={`url(#sg-${color.replace('#','')})`} />
      <polyline points={points} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
};

/* ── Animated counter ── */
const AnimatedNumber = ({ value, decimals = 2, prefix = '', suffix = '', style }) => {
  const [display, setDisplay] = React.useState(value);
  React.useEffect(() => {
    let start = display, end = value, t = 0;
    const duration = 400;
    const step = (ts) => {
      t += 16;
      const p = Math.min(t / duration, 1);
      const eased = 1 - Math.pow(1 - p, 3);
      setDisplay(start + (end - start) * eased);
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }, [value]);
  return <span style={style}>{prefix}{display.toFixed(decimals)}{suffix}</span>;
};

/* ── Circle Payment Modal ── */
const CirclePaymentModal = ({ plan, onClose, onComplete }) => {
  const [step, setStep] = React.useState('connect');
  const [walletAddr, setWalletAddr] = React.useState('');
  const [account, setAccount] = React.useState(null);
  const [paymentPending, setPaymentPending] = React.useState(false);
  const [paymentRequested, setPaymentRequested] = React.useState(false);
  const [paymentError, setPaymentError] = React.useState('');
  const isMobile = useIsMobile(520);

  const payableWallet = walletAddr || window.DEMO_OPERATOR_WALLET || '0x7a3B4C6D8E9F1029384756aBcDEF1234567890aB';

  React.useEffect(() => {
    if (step === 'processing') {
      const t = setTimeout(() => setStep('done'), 3000);
      return () => clearTimeout(t);
    }
  }, [step]);

  React.useEffect(() => {
    if (step !== 'done' || account || paymentPending || paymentRequested) return;
    if (typeof window.createDemoOperatorAccount === 'function') {
      setPaymentRequested(true);
      setPaymentPending(true);
      setPaymentError('');
      window.createDemoOperatorAccount({
        plan,
        wallet: payableWallet,
        txHash: window.DEMO_OPERATOR_TX || '0x3fbd4a19e88c0e2bf98d4c0f6134a946a3e22f19ea2346e8076bb4ac9f789678',
      })
        .then(setAccount)
        .catch(err => setPaymentError(String(err.message || err)))
        .finally(() => setPaymentPending(false));
    }
  }, [step, account, paymentPending, paymentRequested, plan, payableWallet]);

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 200,
      background: '#000000cc', backdropFilter: 'blur(8px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: isMobile ? '16px' : '24px',
    }} onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{
        background: THEME.bg.surface, border: `1px solid ${THEME.border.subtle}`,
        borderRadius: THEME.radius.xl,
        padding: isMobile ? '24px' : '36px',
        width: 'min(420px, calc(100vw - 32px))',
        maxHeight: 'calc(100dvh - 32px)',
        overflow: 'auto',
        boxShadow: `0 32px 64px #00000060`,
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
          <h3 style={{ fontFamily: THEME.font.heading, fontSize: '20px', fontWeight: 700, color: THEME.text.primary, margin: 0 }}>Pay with Circle</h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: THEME.text.muted, cursor: 'pointer', fontSize: '20px' }}>✕</button>
        </div>

        <div style={{ background: THEME.bg.elevated, borderRadius: THEME.radius.md, padding: '16px', marginBottom: '20px', border: `1px solid ${THEME.border.subtle}` }}>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ fontFamily: THEME.font.body, fontSize: '14px', color: THEME.text.secondary }}>Plan</span>
            <span style={{ fontFamily: THEME.font.heading, fontWeight: 700, color: THEME.text.primary }}>{plan.name}</span>
          </div>
          <Divider style={{ margin: '12px 0' }} />
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ fontFamily: THEME.font.body, fontSize: '14px', color: THEME.text.secondary }}>Amount</span>
            <MonoText style={{ fontSize: '16px', fontWeight: 700 }}>{plan.usdc} USDC</MonoText>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '8px' }}>
            <span style={{ fontFamily: THEME.font.body, fontSize: '14px', color: THEME.text.secondary }}>Network</span>
            <Badge color="primary">Arc Testnet</Badge>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '10px', padding: '6px 10px', borderRadius: '6px', background: THEME.amber[400] + '10' }}>
            <span style={{ fontFamily: THEME.font.mono, fontSize: '11px', color: THEME.amber[400] }}>Test tokens only — no real value. Request {plan.usdc} USDC from faucet.circle.com.</span>
          </div>
        </div>

        {step === 'connect' && (
          <div>
            <label style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.secondary, display: 'block', marginBottom: '8px' }}>Wallet address (or connect)</label>
            <input value={walletAddr} onChange={e => setWalletAddr(e.target.value)} placeholder="0x..." style={{
              width: '100%', boxSizing: 'border-box', padding: '12px 16px',
              background: THEME.bg.elevated, border: `1px solid ${THEME.border.default}`,
              borderRadius: THEME.radius.md, color: THEME.text.primary,
              fontFamily: THEME.font.mono, fontSize: '14px', outline: 'none', marginBottom: '16px',
            }} />
            <GlowButton size="md" style={{ width: '100%', justifyContent: 'center' }} onClick={() => {
              if (!walletAddr) setWalletAddr(window.DEMO_OPERATOR_WALLET || '0x7a3B4C6D8E9F1029384756aBcDEF1234567890aB');
              setStep('approve');
            }}>{walletAddr ? 'Continue' : 'Connect Wallet'}</GlowButton>
          </div>
        )}

        {step === 'approve' && (
          <div style={{ textAlign: 'center' }}>
            <div style={{ width: '64px', height: '64px', borderRadius: '50%', background: THEME.primary[400] + '15', border: `2px solid ${THEME.primary[400]}30`, display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px', fontSize: '28px' }}>💳</div>
            <p style={{ fontFamily: THEME.font.body, fontSize: '14px', color: THEME.text.secondary, marginBottom: '20px' }}>
              Approve <MonoText>{plan.usdc} test USDC</MonoText> transfer to Arc escrow
            </p>
            <GlowButton size="md" style={{ width: '100%', justifyContent: 'center' }} onClick={() => setStep('processing')}>Approve &amp; Pay</GlowButton>
          </div>
        )}

        {step === 'processing' && (
          <div style={{ textAlign: 'center', padding: '20px 0' }}>
            <div style={{ width: '48px', height: '48px', border: `3px solid ${THEME.border.default}`, borderTopColor: THEME.primary[400], borderRadius: '50%', margin: '0 auto 16px', animation: 'spin 1s linear infinite' }}></div>
            <p style={{ fontFamily: THEME.font.body, fontSize: '14px', color: THEME.text.secondary }}>Processing on Arc Testnet...</p>
            <MonoText style={{ fontSize: '12px', color: THEME.text.muted }}>Confirming test USDC transfer</MonoText>
          </div>
        )}

        {step === 'done' && (
          <div style={{ textAlign: 'center', padding: '20px 0' }}>
            <div style={{ width: '64px', height: '64px', borderRadius: '50%', background: THEME.primary[400] + '20', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px' }}>
              <svg width="32" height="32" viewBox="0 0 32 32" fill="none"><path d="M8 16l6 6 10-12" stroke={THEME.primary[400]} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" /></svg>
            </div>
            <h4 style={{ fontFamily: THEME.font.heading, fontWeight: 700, color: THEME.text.primary, margin: '0 0 8px' }}>Payment Complete</h4>
            <div style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.secondary, marginBottom: '8px' }}>
              Operator account {account?.id ? account.id : paymentPending ? 'is being created' : 'pending'}
            </div>
            {paymentError && <div style={{ fontFamily: THEME.font.body, fontSize: '12px', color: THEME.red[400], marginBottom: '10px' }}>{paymentError}</div>}
            <MonoText style={{ fontSize: '12px', color: THEME.text.muted, display: 'block', marginBottom: '20px' }}>tx: 0x3fbd...9678</MonoText>
            <GlowButton size="md" disabled={!account || paymentPending} style={{ width: '100%', justifyContent: 'center' }} onClick={() => {
              const finalAccount = account;
              onClose();
              if (onComplete) onComplete(finalAccount);
            }}>{paymentPending ? 'Creating Account...' : 'Go to Account'}</GlowButton>
          </div>
        )}
      </div>
    </div>
  );
};

Object.assign(window, { THEME, useViewport, useIsMobile, Badge, Card, GlowButton, MonoText, SectionLabel, Divider, Nav, Sparkline, AnimatedNumber, CirclePaymentModal });
