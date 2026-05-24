/* Arc Compute Sec — Landing Page v3 (Continuous Journey with Rails) */

/* ── Continuous Rail ── */
const Rail = ({ children }) => (
  <div style={{ position: 'relative' }}>
    {/* The continuous vertical rail line */}
    <div style={{
      position: 'absolute', left: '50%', top: 0, bottom: 0, width: '2px',
      background: `linear-gradient(180deg,
        transparent 0%,
        ${THEME.primary[400]}15 5%,
        ${THEME.primary[400]}25 20%,
        ${THEME.primary[400]}20 50%,
        ${THEME.primary[400]}25 80%,
        ${THEME.primary[400]}15 95%,
        transparent 100%)`,
      zIndex: 0,
    }}></div>
    {/* Energy pulse traveling down the rail */}
    <div style={{
      position: 'absolute', left: '50%', top: 0, width: '2px', height: '120px',
      background: `linear-gradient(180deg, transparent, ${THEME.primary[400]}60, transparent)`,
      zIndex: 1, animation: 'railPulse 6s ease-in-out infinite',
      transform: 'translateX(0)',
    }}></div>
    {children}
  </div>
);

const RailNode = ({ label, color, icon }) => (
  <div style={{
    display: 'flex', justifyContent: 'center', padding: '20px 0', position: 'relative', zIndex: 2,
  }}>
    <div style={{
      display: 'flex', alignItems: 'center', gap: '10px',
      padding: '8px 20px', borderRadius: '100px',
      background: THEME.bg.deep, border: `1px solid ${(color || THEME.primary[400])}30`,
    }}>
      <div style={{
        width: '10px', height: '10px', borderRadius: '50%',
        background: color || THEME.primary[400],
        boxShadow: `0 0 12px ${(color || THEME.primary[400])}50`,
      }}></div>
      <span style={{
        fontFamily: THEME.font.mono, fontSize: '11px', fontWeight: 600,
        letterSpacing: '0.08em', textTransform: 'uppercase',
        color: color || THEME.primary[400],
      }}>{label}</span>
    </div>
  </div>
);

/* ── Hero (informative, with stats) ── */
const HeroV3 = ({ setPage }) => {
  const viewport = useViewport();
  const isMobile = viewport.width <= 820;
  const isNarrow = viewport.width <= 520;
  return (
  <section style={{
    minHeight: isMobile ? 'auto' : '100vh', display: 'flex', flexDirection: 'column',
    justifyContent: 'center', position: 'relative', overflow: 'hidden',
    padding: isMobile ? '42px 16px 36px' : '80px 32px 60px',
  }}>
    {/* Grid bg */}
    <div style={{
      position: 'absolute', inset: 0, opacity: 0.05,
      backgroundImage: `linear-gradient(${THEME.primary[400]} 1px, transparent 1px), linear-gradient(90deg, ${THEME.primary[400]} 1px, transparent 1px)`,
      backgroundSize: '60px 60px',
      maskImage: 'radial-gradient(ellipse 70% 60% at 50% 30%, black, transparent)',
    }}></div>
    <div style={{
      position: 'absolute', top: '-150px', left: '50%', transform: 'translateX(-50%)',
      width: isMobile ? '520px' : '800px', height: isMobile ? '360px' : '500px', borderRadius: '50%',
      background: `radial-gradient(ellipse, ${THEME.primary[400]}10, transparent 70%)`,
    }}></div>

    <div style={{ position: 'relative', zIndex: 1, maxWidth: '1100px', margin: '0 auto', width: '100%' }}>
      {/* Top row: badge + dashboard link */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: isNarrow ? 'stretch' : 'center',
        gap: '12px', flexDirection: isNarrow ? 'column' : 'row', marginBottom: isMobile ? '30px' : '40px',
      }}>
        <Badge color="primary">
          <span style={{ width: 6, height: 6, borderRadius: '50%', background: THEME.primary[400], display: 'inline-block', animation: 'pulse 2s ease infinite' }}></span>
          Live on Arc Testnet · Phase 4
        </Badge>
        <GlowButton size="sm" onClick={() => setPage('dashboard')} style={{ justifyContent: 'center' }}>
          Open Dashboard →
        </GlowButton>
      </div>

      {/* Main content: left text + right live preview */}
      <div style={{ display: 'flex', gap: isMobile ? '30px' : '60px', alignItems: 'center', flexDirection: isMobile ? 'column' : 'row' }}>
        <div style={{ flex: 1 }}>
          <h1 style={{
            fontFamily: THEME.font.heading, fontSize: isMobile ? (isNarrow ? '36px' : '44px') : '56px', fontWeight: 800,
            lineHeight: 1.05, letterSpacing: 0, color: THEME.text.primary,
            margin: '0 0 20px',
          }}>
            Wrap the<br />
            <span style={{ color: THEME.primary[400] }}>compute–energy</span><br />
            spread
          </h1>
          <p style={{
            fontFamily: THEME.font.body, fontSize: isMobile ? '16px' : '18px', lineHeight: 1.7,
            color: THEME.text.secondary, margin: '0 0 32px', maxWidth: '460px',
          }}>
            We measure the real-time gap between GPU compute costs and electricity prices,
            build a canonical spread package, and wrap only judge-approved legs as ERC-8183 jobs on Arc.
          </p>

          {/* Proof stats inline */}
          <div style={{ display: 'grid', gridTemplateColumns: isNarrow ? '1fr' : 'repeat(3, minmax(0, 1fr))', gap: '12px', maxWidth: isMobile ? '100%' : '420px' }}>
            {[
              { val: '97.1%', label: 'Win rate', color: THEME.primary[400] },
              { val: '+$152', label: 'PnL', color: THEME.primary[400] },
              { val: '280K', label: 'News sources', color: THEME.amber[400] },
            ].map((s, i) => (
              <div key={i} style={{
                padding: '14px', borderRadius: '10px',
                background: THEME.bg.surface, border: `1px solid ${THEME.border.subtle}`,
              }}>
                <div style={{ fontFamily: THEME.font.heading, fontSize: '24px', fontWeight: 800, color: s.color, letterSpacing: 0 }}>{s.val}</div>
                <div style={{ fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.muted, marginTop: '2px' }}>{s.label}</div>
              </div>
            ))}
          </div>

          <div style={{ display: 'flex', gap: '12px', marginTop: '28px', flexWrap: 'wrap' }}>
            <GlowButton size="md" onClick={() => setPage('telegram')} style={isNarrow ? { flex: '1 1 100%', justifyContent: 'center' } : undefined}>Telegram Bot</GlowButton>
            <GlowButton size="md" variant="ghost" onClick={() => {
              document.getElementById('spread-section')?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
              // Fallback: just let the user scroll
            }} style={isNarrow ? { flex: '1 1 100%', justifyContent: 'center' } : undefined}>How it works ↓</GlowButton>
          </div>
        </div>

        {/* Right: live spread preview */}
        <div style={{ flex: 1, maxWidth: '480px', width: '100%' }}>
          <div style={{
            background: THEME.bg.surface, border: `1px solid ${THEME.border.subtle}`,
            borderRadius: THEME.radius.lg, overflow: 'hidden',
          }}>
            {/* Terminal header */}
            <div style={{
              display: 'flex', alignItems: 'center', gap: '8px',
              padding: '12px 16px', borderBottom: `1px solid ${THEME.border.subtle}`,
            }}>
              <div style={{ width: 10, height: 10, borderRadius: '50%', background: '#ff5f57' }}></div>
              <div style={{ width: 10, height: 10, borderRadius: '50%', background: '#febc2e' }}></div>
              <div style={{ width: 10, height: 10, borderRadius: '50%', background: '#28c840' }}></div>
              <span style={{ fontFamily: THEME.font.mono, fontSize: '11px', color: THEME.text.muted, marginLeft: '8px' }}>arc-compute-sec · phase4:live</span>
            </div>
            {/* Live spread display */}
            <div style={{ padding: '20px' }}>
              <div style={{ display: 'grid', gridTemplateColumns: isNarrow ? '1fr' : '1fr 1fr', gap: '12px', marginBottom: '16px' }}>
                <div style={{ padding: '12px', borderRadius: '8px', background: THEME.bg.elevated }}>
                  <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.muted }}>Electricity</div>
                  <div style={{ fontFamily: THEME.font.mono, fontSize: isNarrow ? '18px' : '20px', fontWeight: 700, color: THEME.amber[400] }}>$72.34<span style={{ fontSize: '11px', fontWeight: 400, color: THEME.text.muted }}>/MWh</span></div>
                </div>
                <div style={{ padding: '12px', borderRadius: '8px', background: THEME.bg.elevated }}>
                  <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.muted }}>Compute</div>
                  <div style={{ fontFamily: THEME.font.mono, fontSize: isNarrow ? '18px' : '20px', fontWeight: 700, color: THEME.blue[400] }}>$1.54<span style={{ fontSize: '11px', fontWeight: 400, color: THEME.text.muted }}>/GPU-hr</span></div>
                </div>
              </div>
              {/* Spread result */}
              <div style={{
                padding: '14px', borderRadius: '8px',
                background: THEME.primary[400] + '08', border: `1px solid ${THEME.primary[400]}20`,
                marginBottom: '14px',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <div style={{ fontFamily: THEME.font.mono, fontSize: '10px', color: THEME.primary[400], letterSpacing: '0.06em' }}>SPREAD S_t</div>
                    <div style={{ fontFamily: THEME.font.heading, fontSize: isNarrow ? '24px' : '28px', fontWeight: 800, color: THEME.primary[400], letterSpacing: 0 }}>$1.489</div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontFamily: THEME.font.mono, fontSize: '10px', color: THEME.text.muted }}>Z-SCORE</div>
                    <div style={{ fontFamily: THEME.font.heading, fontSize: isNarrow ? '24px' : '28px', fontWeight: 800, color: THEME.red[400], letterSpacing: 0 }}>-2.14</div>
                  </div>
                </div>
              </div>
              {/* Signal + verdict */}
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                <Badge color="amber">electricity_expensive</Badge>
                <Badge color="primary">EXECUTE</Badge>
                <Badge color="muted">spread package</Badge>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    {/* Scroll provocation — show the rail starting */}
    <div style={{
      position: 'absolute', bottom: 0, left: '50%', transform: 'translateX(-50%)',
      width: '2px', height: '80px',
      background: `linear-gradient(transparent, ${THEME.primary[400]}40)`,
    }}></div>
  </section>
  );
};

/* ── Larry Fink Quote (FULL VIEWPORT — the thesis moment) ── */
const QuoteV3 = () => {
  const isMobile = useIsMobile(760);
  const isNarrow = useIsMobile(480);
  return (
  <section style={{
    minHeight: isMobile ? 'auto' : '80vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
    position: 'relative', zIndex: 2, padding: isMobile ? '52px 16px' : '60px 32px', overflow: 'hidden',
  }}>
    {/* Background: faint infrastructure grid */}
    <div style={{
      position: 'absolute', inset: 0, opacity: 0.03,
      backgroundImage: `linear-gradient(${THEME.primary[400]} 1px, transparent 1px), linear-gradient(90deg, ${THEME.primary[400]} 1px, transparent 1px)`,
      backgroundSize: '80px 80px',
    }}></div>
    {/* Large ambient glow */}
    <div style={{
      position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%,-50%)',
      width: isMobile ? '420px' : '700px', height: isMobile ? '420px' : '700px', borderRadius: '50%',
      background: `radial-gradient(circle, ${THEME.primary[400]}08, transparent 65%)`,
    }}></div>

    <div style={{ maxWidth: '1000px', margin: '0 auto', textAlign: 'center', position: 'relative' }}>
      {/* Giant quotation mark */}
      <div style={{
        fontFamily: THEME.font.heading, fontSize: isMobile ? '96px' : '200px', lineHeight: 0.6,
        color: THEME.primary[400], opacity: 0.07, userSelect: 'none',
        position: 'absolute', top: isMobile ? '-24px' : '-60px', left: '50%', transform: 'translateX(-50%)',
      }}>"</div>

      {/* The quote — large, commanding typography */}
      <blockquote style={{
        fontFamily: THEME.font.heading, fontSize: isMobile ? (isNarrow ? '28px' : '34px') : '52px', fontWeight: 800,
        lineHeight: 1.15, letterSpacing: 0, color: THEME.text.primary,
        margin: isMobile ? '0 0 28px' : '0 0 40px', position: 'relative',
      }}>
        A new asset class will be<br />
        buying <span style={{
          color: THEME.primary[400],
          textShadow: `0 0 60px ${THEME.primary[400]}30`,
        }}>futures of compute</span>
      </blockquote>

      {/* Attribution — prominent */}
      <div style={{
        display: 'inline-flex', alignItems: 'center', gap: '16px',
        padding: isNarrow ? '12px 16px' : '14px 28px', borderRadius: '100px',
        background: THEME.bg.surface, border: `1px solid ${THEME.border.subtle}`,
      }}>
        <div style={{
          width: '44px', height: '44px', borderRadius: '50%',
          background: `linear-gradient(135deg, ${THEME.bg.elevated}, ${THEME.bg.hover})`,
          border: `1px solid ${THEME.border.default}`,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontFamily: THEME.font.heading, fontSize: '16px', fontWeight: 800,
          color: THEME.text.secondary,
        }}>LF</div>
        <div style={{ textAlign: 'left' }}>
          <div style={{ fontFamily: THEME.font.heading, fontSize: '16px', fontWeight: 700, color: THEME.text.primary }}>Larry Fink</div>
          <div style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.muted }}>CEO, BlackRock — Milken Conference</div>
        </div>
      </div>

      {/* Bridge text — connects quote to what this project does */}
      <div style={{ marginTop: '40px', maxWidth: '600px', margin: '40px auto 0' }}>
        <p style={{
          fontFamily: THEME.font.body, fontSize: isMobile ? '16px' : '18px', lineHeight: 1.7,
          color: THEME.text.secondary,
        }}>
          That market doesn't exist yet. <span style={{ color: THEME.text.primary, fontWeight: 600 }}>This is the first step.</span> We canonicalize a spread package: direct prediction-event pairs when available, labelled liquid proxies when not, and an Arc audit trail around the judged package.
        </p>
      </div>
    </div>
  </section>
  );
};

/* ── Spread Section ── */
const SpreadV3 = () => {
  const isMobile = useIsMobile(760);
  return (
  <section id="spread-section" style={{ padding: isMobile ? '44px 16px' : '60px 32px', position: 'relative', zIndex: 2 }}>
    <div style={{ maxWidth: '1100px', margin: '0 auto', textAlign: 'center' }}>
      <h2 style={{
        fontFamily: THEME.font.heading, fontSize: isMobile ? '30px' : '40px', fontWeight: 800,
        letterSpacing: 0, color: THEME.text.primary, margin: '0 0 12px',
      }}>The electricity–compute spread</h2>
      <p style={{
        fontFamily: THEME.font.body, fontSize: '17px', color: THEME.text.secondary,
        maxWidth: '580px', margin: '0 auto 40px', lineHeight: 1.6,
      }}>
        Compute is becoming a commodity, but not yet directly tradable. We bridge the gap by measuring the real-time spread and turning it into a canonical package of direct event legs plus labelled proxy legs.
      </p>
      <div style={{ display: 'flex', justifyContent: 'center', overflow: 'hidden' }}>
        <SpreadIllustration width={isMobile ? 340 : 600} height={isMobile ? 150 : 200} />
      </div>
    </div>
  </section>
  );
};

/* ── Layer Section (with rail alignment) ── */
const LayerV3 = ({ layer, label, title, desc, children, illustration, reverse, color }) => {
  const isMobile = useIsMobile(820);
  return (
  <section style={{ padding: isMobile ? '42px 16px' : '60px 32px', position: 'relative', zIndex: 2 }}>
    <div style={{
      maxWidth: '1100px', margin: '0 auto', width: '100%',
      display: 'flex', gap: isMobile ? '24px' : '48px', alignItems: 'center',
      flexDirection: isMobile ? 'column' : (reverse ? 'row-reverse' : 'row'),
    }}>
      <div style={{ flex: 1 }}>
        <div style={{
          fontFamily: THEME.font.mono, fontSize: '12px', fontWeight: 700,
          letterSpacing: '0.1em', textTransform: 'uppercase',
          color: THEME.text.faint, marginBottom: '4px',
        }}>Layer {layer}</div>
        <SectionLabel style={{ color: color }}>{label}</SectionLabel>
        <h2 style={{
          fontFamily: THEME.font.heading, fontSize: isMobile ? '28px' : '36px', fontWeight: 800,
          letterSpacing: 0, color: THEME.text.primary, margin: '0 0 16px',
        }}>{title}</h2>
        <p style={{
          fontFamily: THEME.font.body, fontSize: '16px', lineHeight: 1.7,
          color: THEME.text.secondary, margin: '0 0 24px', maxWidth: '460px',
        }}>{desc}</p>
        {children}
      </div>
      <div style={{ flex: 1, display: 'flex', justifyContent: 'center', width: '100%', overflow: 'hidden' }}>
        {illustration}
      </div>
    </div>
  </section>
  );
};

const MetricChips = ({ items }) => (
  <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
    {items.map((s, i) => (
      <div key={i} style={{
        padding: '10px 16px', borderRadius: '8px',
        background: THEME.bg.surface, border: `1px solid ${THEME.border.subtle}`,
      }}>
        <div style={{ fontFamily: THEME.font.mono, fontSize: '15px', fontWeight: 700, color: s.color }}>{s.val}</div>
        <div style={{ fontFamily: THEME.font.body, fontSize: '11px', color: THEME.text.muted, marginTop: '2px' }}>{s.label}</div>
      </div>
    ))}
  </div>
);

const ElecLayer = () => {
  const isMobile = useIsMobile(820);
  return (
  <LayerV3 layer="1.0" label="Electricity" color={THEME.amber[400]}
    title="Real-time grid pricing"
    desc="EIA's ERCOT/TX data feeds wholesale power costs that directly drive GPU operating expenses. Spikes and dips shift the spread."
    illustration={<GridIllustration width={isMobile ? 330 : 440} height={isMobile ? 230 : 300} />}
  >
    <MetricChips items={[
      { val: '$72.34', label: '/MWh current', color: THEME.amber[400] },
      { val: 'ERCOT/TX', label: 'region', color: THEME.text.secondary },
      { val: 'Live', label: 'EIA feed', color: THEME.primary[400] },
    ]} />
  </LayerV3>
  );
};

const CompLayer = () => {
  const isMobile = useIsMobile(820);
  return (
  <LayerV3 layer="2.0" label="Compute" color={THEME.blue[400]}
    title="GPU spot pricing"
    desc="AWS spot prices for p4d.24xlarge instances. Hardware depreciates faster than it wears out — there is no standard futures unit for a GPU-hour."
    illustration={<DataCenterIllustration width={isMobile ? 330 : 440} height={isMobile ? 230 : 300} />}
    reverse
  >
    <MetricChips items={[
      { val: '$1.54', label: '/GPU-hr spot', color: THEME.blue[400] },
      { val: '0.7', label: 'kWh/GPU-hr', color: THEME.text.secondary },
      { val: 'p4d', label: 'us-east-1', color: THEME.blue[400] },
    ]} />
  </LayerV3>
  );
};

const SettleLayer = () => {
  const isMobile = useIsMobile(820);
  return (
  <LayerV3 layer="3.0" label="Settlement" color={THEME.primary[400]}
    title="Arc on-chain audit"
    desc="Every judged spread package becomes an ERC-8183 job with escrow, identity, reputation, and a full trail. Circle USDC handles settlement. The 4-way judge ensures nothing bypasses review."
    illustration={<BlockchainIllustration width={isMobile ? 330 : 440} height={isMobile ? 230 : 300} />}
  >
    <MetricChips items={[
      { val: '#19091', label: 'latest job', color: THEME.primary[400] },
      { val: 'EXECUTE', label: 'judge verdict', color: THEME.primary[400] },
      { val: '5 USDC', label: 'escrowed (test)', color: THEME.amber[400] },
    ]} />
  </LayerV3>
  );
};

/* ── Big Stats ── */
const BigStatsV3 = () => {
  const isMobile = useIsMobile(760);
  return (
  <section style={{ padding: isMobile ? '48px 16px' : '80px 32px', position: 'relative', zIndex: 2 }}>
    <div style={{ maxWidth: '1000px', margin: '0 auto' }}>
      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, 1fr)', gap: isMobile ? '12px' : '20px' }}>
        {[
          { value: '97.1%', label: 'Win rate on AI-infra', color: THEME.primary[400] },
          { value: '+$152', label: 'PnL from 99 gate-kept fills', color: THEME.primary[400] },
          { value: '280K', label: 'News sources · 200 languages', color: THEME.amber[400] },
        ].map((s, i) => (
          <div key={i} style={{
            padding: isMobile ? '24px 18px' : '36px 24px', borderRadius: THEME.radius.lg, textAlign: 'center',
            background: THEME.bg.surface, border: `1px solid ${THEME.border.subtle}`,
          }}>
            <div style={{
              fontFamily: THEME.font.heading, fontSize: isMobile ? '40px' : '52px', fontWeight: 800,
              letterSpacing: 0, color: s.color, lineHeight: 1,
            }}>{s.value}</div>
            <div style={{ fontFamily: THEME.font.body, fontSize: '14px', color: THEME.text.muted, marginTop: '10px' }}>{s.label}</div>
          </div>
        ))}
      </div>
      <div style={{ textAlign: 'center', marginTop: '16px' }}>
        <MonoText style={{ fontSize: '12px', color: THEME.text.faint }}>
          Frontier models analyse · Premium gate filters · Only EXECUTE hits the chain
        </MonoText>
      </div>
    </div>
  </section>
  );
};

/* ── Pipeline (compact horizontal) ── */
const PipelineV3 = () => {
  const isMobile = useIsMobile(700);
  const steps = [
    { IconComp: IconSignal, title: 'Signal', desc: 'Z-score dislocation', color: THEME.amber[400] },
    { IconComp: IconPrediction, title: 'Package', desc: 'events + proxies', color: THEME.purple[400] },
    { IconComp: IconJudge, title: 'Judge', desc: '4-way gate', color: THEME.primary[400] },
    { IconComp: IconArc, title: 'Settle', desc: 'ERC-8183 on Arc', color: THEME.primary[400] },
  ];
  return (
    <section style={{ padding: isMobile ? '32px 16px 46px' : '40px 32px 60px', position: 'relative', zIndex: 2 }}>
      <div style={{ maxWidth: '800px', margin: '0 auto' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', position: 'relative', flexWrap: isMobile ? 'wrap' : 'nowrap', rowGap: '22px' }}>
          <div style={{
            position: 'absolute', top: '26px', left: '50px', right: '50px', height: '2px',
            background: `linear-gradient(90deg, ${THEME.amber[400]}30, ${THEME.purple[400]}30, ${THEME.primary[400]}30, ${THEME.primary[400]}30)`,
            display: isMobile ? 'none' : 'block',
          }}></div>
          {steps.map((s, i) => (
            <div key={i} style={{ flex: isMobile ? '1 1 50%' : 1, textAlign: 'center', position: 'relative' }}>
              <div style={{
                width: '52px', height: '52px', borderRadius: '50%',
                background: THEME.bg.surface, border: `2px solid ${s.color}25`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                margin: '0 auto 12px', position: 'relative', zIndex: 1,
              }}>
                <s.IconComp size={24} color={s.color} />
              </div>
              <div style={{ fontFamily: THEME.font.heading, fontSize: '14px', fontWeight: 700, color: THEME.text.primary }}>{s.title}</div>
              <div style={{ fontFamily: THEME.font.body, fontSize: '12px', color: THEME.text.muted, marginTop: '3px' }}>{s.desc}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

/* ── Pricing ── */
const PricingV3 = ({ setPage }) => {
  const [showPayment, setShowPayment] = React.useState(false);
  const [selectedPlan, setSelectedPlan] = React.useState(null);
  const isMobile = useIsMobile(760);
  const plans = [
    { id: 'free', name: 'Explorer', price: '0', period: 'forever', features: ['Read-only signal feed', 'Basic z-score alerts', 'Community Telegram channel', '1 mock backtest/day'], cta: 'Start Free', popular: false },
    { id: 'operator', name: 'Operator', price: '5', period: '/month', features: ['Spread package routing', 'Actionable package alerts', 'Telegram scan commands', 'Saved oracle backtest view', 'Arc Testnet wrap controls'], cta: 'Start Operator', popular: true, usdc: '5' },
  ];
  return (
    <section id="pricing-section" style={{ padding: isMobile ? '48px 16px' : '60px 32px', position: 'relative', zIndex: 2 }}>
      <div style={{ maxWidth: '1000px', margin: '0 auto' }}>
        <div style={{ textAlign: 'center', marginBottom: '40px' }}>
          <SectionLabel>Pricing</SectionLabel>
          <h2 style={{ fontFamily: THEME.font.heading, fontSize: isMobile ? '30px' : '40px', fontWeight: 800, letterSpacing: 0, color: THEME.text.primary, margin: '0 0 12px' }}>
            Pay with Circle USDC
          </h2>
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', padding: '8px 16px', borderRadius: '8px', background: THEME.amber[400] + '12', border: `1px solid ${THEME.amber[400]}25`, maxWidth: '100%' }}>
            <IconCoin size={18} color={THEME.amber[400]} />
            <span style={{ fontFamily: THEME.font.mono, fontSize: '12px', color: THEME.amber[400], minWidth: 0 }}>Test tokens only — free from faucet.circle.com</span>
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(2, minmax(0, 1fr))', gap: '16px', maxWidth: '760px', margin: '0 auto' }}>
          {plans.map(p => (
            <Card key={p.id} glow={p.popular} style={{
              border: p.popular ? `1px solid ${THEME.primary[400]}40` : undefined,
              position: 'relative',
              paddingTop: p.popular ? '48px' : undefined,
            }}>
              {p.popular && <Badge color="primary" style={{ position: 'absolute', top: '14px', right: '16px', whiteSpace: 'nowrap', zIndex: 2 }}>Most Popular</Badge>}
              <h3 style={{ fontFamily: THEME.font.heading, fontSize: '20px', fontWeight: 700, color: THEME.text.primary, margin: '0 0 8px' }}>{p.name}</h3>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '4px', marginBottom: '20px' }}>
                <span style={{ fontFamily: THEME.font.heading, fontSize: '44px', fontWeight: 800, color: THEME.text.primary, letterSpacing: 0 }}>${p.price}</span>
                <span style={{ fontFamily: THEME.font.body, fontSize: '14px', color: THEME.text.muted }}>{p.period}</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '24px' }}>
                {p.features.map((f, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M3 7l3 3 5-6" stroke={THEME.primary[400]} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
                    <span style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.secondary }}>{f}</span>
                  </div>
                ))}
              </div>
              <GlowButton variant={p.popular ? 'primary' : 'ghost'} size="md" style={{ width: '100%', justifyContent: 'center' }}
                onClick={() => {
                  if (window.scrollAppToTop) window.scrollAppToTop();
                  if (p.usdc) {
                    setSelectedPlan(p);
                    setShowPayment(true);
                  } else {
                    setPage('dashboard');
                  }
                }}
              >{p.cta}</GlowButton>
              {p.usdc && <div style={{ textAlign: 'center', marginTop: '8px' }}><MonoText style={{ fontSize: '11px', color: THEME.text.muted }}>or {p.usdc} test USDC from Circle faucet</MonoText></div>}
            </Card>
          ))}
        </div>
        {showPayment && selectedPlan && (
          <CirclePaymentModal
            plan={selectedPlan}
            onClose={() => setShowPayment(false)}
            onComplete={() => {
              if (window.scrollAppToTop) window.scrollAppToTop();
              setPage('account');
            }}
          />
        )}
      </div>
    </section>
  );
};

/* ── Testnet Explainer (compact) ── */
const TestnetV3 = () => {
  const isMobile = useIsMobile(640);
  return (
  <section style={{ padding: isMobile ? '0 16px 48px' : '0 32px 60px', position: 'relative', zIndex: 2 }}>
    <div style={{ maxWidth: '800px', margin: '0 auto' }}>
      <Card style={{ padding: '24px', border: `1px solid ${THEME.amber[400]}15` }}>
        <div style={{ display: 'flex', gap: '20px', alignItems: isMobile ? 'flex-start' : 'center', flexDirection: isMobile ? 'column' : 'row' }}>
          <IconCoin size={44} color={THEME.amber[400]} />
          <div style={{ flex: 1 }}>
            <div style={{ fontFamily: THEME.font.heading, fontSize: '16px', fontWeight: 700, color: THEME.text.primary, marginBottom: '6px' }}>
              Circle Testnet USDC — Free, zero real value
            </div>
            <div style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.secondary, lineHeight: 1.6 }}>
              Visit <MonoText style={{ color: THEME.amber[400] }}>faucet.circle.com</MonoText> → enter wallet → select Arc Testnet → request ≥ 5 USDC. Tokens arrive in ~30s. Rate limit: 1 per IP.
            </div>
          </div>
        </div>
      </Card>
    </div>
  </section>
  );
};

/* ── Assembled Landing ── */
const LandingPage = ({ setPage }) => (
  <div>
    <HeroV3 setPage={setPage} />
    <Rail>
      <RailNode label="Thesis" color={THEME.text.muted} />
      <QuoteV3 />
      <RailNode label="The Spread" color={THEME.primary[400]} />
      <SpreadV3 />
      <RailNode label="Layer 1.0 · Electricity" color={THEME.amber[400]} />
      <ElecLayer />
      <RailNode label="Layer 2.0 · Compute" color={THEME.blue[400]} />
      <CompLayer />
      <RailNode label="Layer 3.0 · Settlement" color={THEME.primary[400]} />
      <SettleLayer />
      <RailNode label="Evidence" color={THEME.primary[400]} />
      <BigStatsV3 />
      <PipelineV3 />
      <RailNode label="Get Started" color={THEME.primary[400]} />
      <PricingV3 setPage={setPage} />
      <TestnetV3 />
    </Rail>
    <footer style={{ padding: '40px 32px 60px', textAlign: 'center', borderTop: `1px solid ${THEME.border.subtle}` }}>
      <MonoText style={{ color: THEME.text.faint, fontSize: '12px' }}>
        arc-compute-sec v1.0 · Arc Testnet · Phase 4 Live · Job #19091
      </MonoText>
    </footer>
  </div>
);

Object.assign(window, { LandingPage });
