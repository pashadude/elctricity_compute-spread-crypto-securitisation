/* Power by Botozen — Methodology: how notes are constructed, signal logic, replay */

const PipelineStep = ({ n, title, body, last }) => (
  <div style={{ display: 'flex', gap: '16px' }}>
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
      <div style={{ width: 32, height: 32, borderRadius: '50%', flexShrink: 0, background: THEME.primary[400] + '15', border: `1px solid ${THEME.primary[400]}40`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: THEME.font.mono, fontSize: '13px', fontWeight: 700, color: THEME.primary[400] }}>{n}</div>
      {!last && <div style={{ width: 1, flex: 1, background: THEME.border.default, marginTop: '4px' }}></div>}
    </div>
    <div style={{ paddingBottom: last ? 0 : '24px' }}>
      <h4 style={{ fontFamily: THEME.font.heading, fontSize: '16px', fontWeight: 700, color: THEME.text.primary, margin: '4px 0 6px' }}>{title}</h4>
      <p style={{ fontFamily: THEME.font.body, fontSize: '13.5px', color: THEME.text.secondary, margin: 0, lineHeight: 1.6, maxWidth: '560px', textWrap: 'pretty' }}>{body}</p>
    </div>
  </div>
);

const SignalBand = ({ range, label, color, desc }) => (
  <div style={{ display: 'flex', alignItems: 'center', gap: '14px', padding: '12px 0', borderTop: `1px solid ${THEME.border.subtle}` }}>
    <MonoText style={{ fontSize: '13px', minWidth: '90px', color: THEME.text.secondary }}>{range}</MonoText>
    <Badge color={color} style={{ minWidth: '108px', justifyContent: 'center' }}>{label}</Badge>
    <span style={{ fontFamily: THEME.font.body, fontSize: '13px', color: THEME.text.muted }}>{desc}</span>
  </div>
);

const MethodologyView = () => (
  <div>
    <h2 style={{ fontFamily: THEME.font.heading, fontSize: '22px', fontWeight: 700, color: THEME.text.primary, margin: '0 0 6px', letterSpacing: '-0.02em' }}>Methodology</h2>
    <p style={{ fontFamily: THEME.font.body, fontSize: '13.5px', color: THEME.text.muted, margin: '0 0 24px', maxWidth: '640px', lineHeight: 1.55 }}>
      How a raw price index becomes a tradable spread note, and what the replay record does and doesn't tell you.
    </p>

    <div style={{ display: 'grid', gridTemplateColumns: '1.3fr 1fr', gap: '14px', alignItems: 'start' }}>
      {/* pipeline */}
      <Card style={{ padding: '26px' }}>
        <SectionLabel>From index to note</SectionLabel>
        <div style={{ marginTop: '18px' }}>
          <PipelineStep n="1" title="Indexes" body="The backend reads electricity, fuel, compute, direct-event, and public hedge marks. Each feed is normalized into canonical rows before it reaches the user interface." />
          <PipelineStep n="2" title="Spread form" body="Two or more rows become a spread form: compute spark spread, fuel-stack compute spread, calendar basis, miner-margin pair, grid-event hazard, and related structures." />
          <PipelineStep n="3" title="Note construction" body="A spread form is packaged into a paper note with priced proxy legs, direct event or forecast references, missing-collateral checks, and a Circle test-USDC size." />
          <PipelineStep n="4" title="Signal" body="The replay and current marks set the note signal: buy / paper entry, hold / watch, or close / avoid. A buyable paper note is still not asset-backed until collateral is attached." />
          <PipelineStep n="5" title="Account and Arc gate" body="A user paper ticket is stored under the signed Operator account and marked for PnL. Circle/Arc settlement remains locked unless the premium scorer and judge.classify() return EXECUTE." last />
        </div>
      </Card>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
        {/* signal bands */}
        <Card>
          <SectionLabel>Signal bands</SectionLabel>
          <p style={{ fontFamily: THEME.font.body, fontSize: '12.5px', color: THEME.text.muted, margin: '4px 0 8px', lineHeight: 1.5 }}>
            The headline z-score maps to a per-note signal.
          </p>
          <SignalBand range="BUY" label="ENTER" color="primary" desc="Replay and current marks support a paper ticket." />
          <SignalBand range="HOLD" label="HOLD" color="amber" desc="Track existing exposure, wait on fresh entry." />
          <SignalBand range="SELL" label="CLOSE / AVOID" color="red" desc="Do not add fresh paper exposure." />
        </Card>

        {/* replay meaning */}
        <Card>
          <SectionLabel>Reading the replay record</SectionLabel>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: '10px' }}>
            {[['Trailing yield', 'Annualised return of the basket over the replay window.'],
              ['Volatility / Max DD', 'Dispersion and worst peak-to-trough of the replayed series.'],
              ['Sharpe', 'Replay return per unit of replay volatility — not a forward promise.'],
              ['Replay status', 'Live = the basket is still being marked; paused = construction is on hold.']].map(([k, v], i) => (
              <div key={i}>
                <div style={{ fontFamily: THEME.font.heading, fontSize: '13px', fontWeight: 700, color: THEME.text.primary }}>{k}</div>
                <div style={{ fontFamily: THEME.font.body, fontSize: '12.5px', color: THEME.text.muted, lineHeight: 1.45 }}>{v}</div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>

    {/* disclosure */}
    <Card style={{ marginTop: '14px', padding: '18px 22px', background: THEME.bg.elevated }}>
      <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
        <div style={{ width: 32, height: 32, borderRadius: '8px', flexShrink: 0, background: THEME.amber[400] + '15', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '15px' }}>⚠</div>
        <div>
          <div style={{ fontFamily: THEME.font.heading, fontSize: '14px', fontWeight: 700, color: THEME.text.primary, marginBottom: '3px' }}>Paper tracking — not real trading</div>
          <p style={{ fontFamily: THEME.font.body, fontSize: '12.5px', color: THEME.text.muted, margin: 0, lineHeight: 1.55, maxWidth: '760px' }}>
            Positions, NAVs and P&L shown across this app are account-backed paper records marked against backend data. They are not live venue fills and are not legal ABS. Arc settlement is gated by judge.classify() and nothing here is investment advice.
          </p>
        </div>
      </div>
    </Card>
  </div>
);

Object.assign(window, { MethodologyView });
