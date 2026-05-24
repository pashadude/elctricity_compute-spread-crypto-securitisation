/* Arc Compute Sec — Large Infrastructure Illustrations */

/* ── Power Grid Illustration ── */
const GridIllustration = ({ width = 520, height = 360 }) => {
  const g = '#00DC82';
  const a = '#F59E0B';
  return (
    <svg width={width} height={height} viewBox="0 0 520 360" fill="none" style={{ display: 'block' }}>
      <defs>
        <linearGradient id="gridGlow" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={g} stopOpacity="0.12" />
          <stop offset="100%" stopColor={g} stopOpacity="0" />
        </linearGradient>
        <filter id="glow1"><feGaussianBlur stdDeviation="3" result="blur" /><feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
      </defs>
      {/* Background grid */}
      {Array.from({length: 14}, (_, i) => <line key={`v${i}`} x1={i*40} y1="0" x2={i*40} y2="360" stroke={g} strokeWidth="0.5" opacity="0.06" />)}
      {Array.from({length: 10}, (_, i) => <line key={`h${i}`} x1="0" y1={i*40} x2="520" y2={i*40} stroke={g} strokeWidth="0.5" opacity="0.06" />)}

      {/* Ground plane */}
      <line x1="0" y1="300" x2="520" y2="300" stroke={g} strokeWidth="1" opacity="0.15" />

      {/* Tower 1 */}
      <g transform="translate(60,100)">
        <line x1="30" y1="0" x2="10" y2="200" stroke={a} strokeWidth="2.5" />
        <line x1="30" y1="0" x2="50" y2="200" stroke={a} strokeWidth="2.5" />
        <line x1="30" y1="0" x2="30" y2="-20" stroke={a} strokeWidth="2" />
        <line x1="15" y1="60" x2="45" y2="60" stroke={a} strokeWidth="1.5" opacity="0.6" />
        <line x1="13" y1="120" x2="47" y2="120" stroke={a} strokeWidth="1.5" opacity="0.6" />
        <line x1="15" y1="60" x2="47" y2="120" stroke={a} strokeWidth="1" opacity="0.3" />
        <line x1="45" y1="60" x2="13" y2="120" stroke={a} strokeWidth="1" opacity="0.3" />
        <circle cx="30" cy="-20" r="3" fill={a} opacity="0.8" />
      </g>

      {/* Tower 2 */}
      <g transform="translate(200,120)">
        <line x1="25" y1="0" x2="8" y2="180" stroke={a} strokeWidth="2.5" />
        <line x1="25" y1="0" x2="42" y2="180" stroke={a} strokeWidth="2.5" />
        <line x1="25" y1="0" x2="25" y2="-18" stroke={a} strokeWidth="2" />
        <line x1="12" y1="55" x2="38" y2="55" stroke={a} strokeWidth="1.5" opacity="0.6" />
        <line x1="10" y1="110" x2="40" y2="110" stroke={a} strokeWidth="1.5" opacity="0.6" />
        <line x1="12" y1="55" x2="40" y2="110" stroke={a} strokeWidth="1" opacity="0.3" />
        <line x1="38" y1="55" x2="10" y2="110" stroke={a} strokeWidth="1" opacity="0.3" />
        <circle cx="25" cy="-18" r="3" fill={a} opacity="0.8" />
      </g>

      {/* Power lines between towers */}
      <path d="M90 100 Q145 115 225 120" stroke={a} strokeWidth="1.5" fill="none" opacity="0.5" />
      <path d="M90 105 Q145 122 225 125" stroke={a} strokeWidth="1" fill="none" opacity="0.3" />

      {/* Energy pulses along power lines */}
      <circle cx="0" cy="0" r="4" fill={a} opacity="0.9" filter="url(#glow1)">
        <animateMotion dur="3s" repeatCount="indefinite" path="M90,100 Q145,115 225,120" />
      </circle>
      <circle cx="0" cy="0" r="3" fill={a} opacity="0.6" filter="url(#glow1)">
        <animateMotion dur="3s" repeatCount="indefinite" path="M90,105 Q145,122 225,125" begin="1.5s" />
      </circle>

      {/* Substation */}
      <g transform="translate(310,220)">
        <rect x="0" y="0" width="80" height="80" rx="4" stroke={g} strokeWidth="1.5" fill={g} fillOpacity="0.04" />
        <rect x="8" y="8" width="28" height="28" rx="2" stroke={g} strokeWidth="1" fill={g} fillOpacity="0.06" />
        <rect x="44" y="8" width="28" height="28" rx="2" stroke={g} strokeWidth="1" fill={g} fillOpacity="0.06" />
        <rect x="8" y="44" width="28" height="28" rx="2" stroke={g} strokeWidth="1" fill={g} fillOpacity="0.06" />
        <rect x="44" y="44" width="28" height="28" rx="2" stroke={g} strokeWidth="1" fill={g} fillOpacity="0.06" />
        {/* Transformer symbols */}
        <circle cx="22" cy="22" r="6" stroke={g} strokeWidth="1" fill="none" opacity="0.5" />
        <circle cx="58" cy="22" r="6" stroke={g} strokeWidth="1" fill="none" opacity="0.5" />
        <circle cx="22" cy="58" r="6" stroke={g} strokeWidth="1" fill="none" opacity="0.5" />
        <circle cx="58" cy="58" r="6" stroke={g} strokeWidth="1" fill="none" opacity="0.5" />
        {/* Status dots */}
        <circle cx="22" cy="22" r="2" fill={g} opacity="0.8"><animate attributeName="opacity" values="0.4;1;0.4" dur="2s" repeatCount="indefinite" /></circle>
        <circle cx="58" cy="22" r="2" fill={g} opacity="0.6"><animate attributeName="opacity" values="0.6;1;0.6" dur="2.5s" repeatCount="indefinite" /></circle>
      </g>

      {/* Power line to substation */}
      <path d="M250 120 Q280 160 310 220" stroke={a} strokeWidth="1.5" fill="none" opacity="0.4" />

      {/* Labels */}
      <text x="75" y="330" fontFamily="'JetBrains Mono', monospace" fontSize="10" fill={a} opacity="0.6">ERCOT/TX</text>
      <text x="200" y="330" fontFamily="'JetBrains Mono', monospace" fontSize="10" fill={a} opacity="0.6">72.34 $/MWh</text>
      <text x="330" y="330" fontFamily="'JetBrains Mono', monospace" fontSize="10" fill={g} opacity="0.6">SUBSTATION</text>

      {/* Voltage indicator */}
      <g transform="translate(420,140)">
        <text fontFamily="'Space Grotesk', sans-serif" fontSize="42" fontWeight="800" fill={a} opacity="0.12">⚡</text>
      </g>

      {/* Data overlay */}
      <rect x="380" y="40" width="120" height="60" rx="6" fill="#0B0F0E" fillOpacity="0.8" stroke={g} strokeWidth="1" opacity="0.6" />
      <text x="395" y="60" fontFamily="'JetBrains Mono', monospace" fontSize="9" fill={g} opacity="0.7">LIVE FEED</text>
      <text x="395" y="78" fontFamily="'JetBrains Mono', monospace" fontSize="11" fill="#fff" opacity="0.9">$72.34/MWh</text>
      <text x="395" y="92" fontFamily="'JetBrains Mono', monospace" fontSize="9" fill={a} opacity="0.5">EIA ERCOT/TX</text>
    </svg>
  );
};

/* ── Data Center Illustration ── */
const DataCenterIllustration = ({ width = 520, height = 360 }) => {
  const g = '#00DC82';
  const b = '#60A5FA';
  return (
    <svg width={width} height={height} viewBox="0 0 520 360" fill="none" style={{ display: 'block' }}>
      <defs>
        <filter id="glow2"><feGaussianBlur stdDeviation="2" result="blur" /><feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
      </defs>
      {/* Background grid */}
      {Array.from({length: 14}, (_, i) => <line key={`v${i}`} x1={i*40} y1="0" x2={i*40} y2="360" stroke={b} strokeWidth="0.5" opacity="0.04" />)}
      {Array.from({length: 10}, (_, i) => <line key={`h${i}`} x1="0" y1={i*40} x2="520" y2={i*40} stroke={b} strokeWidth="0.5" opacity="0.04" />)}

      {/* Building shell */}
      <rect x="80" y="60" width="280" height="240" rx="4" stroke={b} strokeWidth="2" fill={b} fillOpacity="0.03" />
      <line x1="80" y1="60" x2="220" y2="20" stroke={b} strokeWidth="1.5" opacity="0.4" />
      <line x1="360" y1="60" x2="220" y2="20" stroke={b} strokeWidth="1.5" opacity="0.4" />

      {/* Server racks — 3 rows x 4 cols */}
      {[0,1,2].map(row => [0,1,2,3].map(col => {
        const x = 105 + col * 62;
        const y = 85 + row * 70;
        const isActive = Math.random() > 0.2;
        return (
          <g key={`r${row}${col}`} transform={`translate(${x},${y})`}>
            <rect width="50" height="55" rx="3" stroke={b} strokeWidth="1.5" fill={b} fillOpacity={isActive ? "0.06" : "0.02"} />
            {/* Drive bays */}
            {[0,1,2,3,4].map(i => (
              <rect key={i} x="4" y={4 + i*10} width="42" height="7" rx="1" fill={b} fillOpacity="0.08" stroke={b} strokeWidth="0.5" opacity="0.4" />
            ))}
            {/* Status LED */}
            <circle cx="44" cy="7" r="2" fill={isActive ? g : '#EF4444'} opacity={isActive ? 0.9 : 0.5}>
              {isActive && <animate attributeName="opacity" values="0.5;1;0.5" dur={`${1.5 + Math.random()*2}s`} repeatCount="indefinite" />}
            </circle>
          </g>
        );
      }))}

      {/* GPU label */}
      <rect x="380" y="100" width="120" height="80" rx="6" fill="#0B0F0E" fillOpacity="0.8" stroke={b} strokeWidth="1" opacity="0.6" />
      <text x="395" y="120" fontFamily="'JetBrains Mono', monospace" fontSize="9" fill={b} opacity="0.7">GPU SPOT</text>
      <text x="395" y="140" fontFamily="'JetBrains Mono', monospace" fontSize="14" fill="#fff" opacity="0.9">$1.54</text>
      <text x="395" y="155" fontFamily="'JetBrains Mono', monospace" fontSize="9" fill={b} opacity="0.5">/GPU-hr · p4d</text>
      <text x="395" y="172" fontFamily="'JetBrains Mono', monospace" fontSize="9" fill={g} opacity="0.5">us-east-1</text>

      {/* Utilization bars */}
      <g transform="translate(380,210)">
        <text fontFamily="'JetBrains Mono', monospace" fontSize="9" fill={b} opacity="0.5">UTILIZATION</text>
        {[87, 92, 64, 78].map((v, i) => (
          <g key={i} transform={`translate(0,${14 + i*18})`}>
            <rect width="100" height="10" rx="2" fill={b} fillOpacity="0.1" />
            <rect width={v} height="10" rx="2" fill={b} fillOpacity="0.3" />
            <text x="106" y="8" fontFamily="'JetBrains Mono', monospace" fontSize="8" fill={b} opacity="0.6">{v}%</text>
          </g>
        ))}
      </g>

      {/* Ground */}
      <line x1="60" y1="300" x2="380" y2="300" stroke={b} strokeWidth="1" opacity="0.15" />
      <text x="120" y="330" fontFamily="'JetBrains Mono', monospace" fontSize="10" fill={b} opacity="0.5">AWS p4d.24xlarge</text>
      <text x="120" y="345" fontFamily="'JetBrains Mono', monospace" fontSize="9" fill={b} opacity="0.3">0.7 kWh/GPU-hr</text>
    </svg>
  );
};

/* ── Blockchain / Arc Settlement Illustration ── */
const BlockchainIllustration = ({ width = 520, height = 360 }) => {
  const g = '#00DC82';
  const p = '#A78BFA';
  return (
    <svg width={width} height={height} viewBox="0 0 520 360" fill="none" style={{ display: 'block' }}>
      <defs>
        <filter id="glow3"><feGaussianBlur stdDeviation="3" result="blur" /><feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
      </defs>
      {/* Background grid */}
      {Array.from({length: 14}, (_, i) => <line key={`v${i}`} x1={i*40} y1="0" x2={i*40} y2="360" stroke={g} strokeWidth="0.5" opacity="0.04" />)}
      {Array.from({length: 10}, (_, i) => <line key={`h${i}`} x1="0" y1={i*40} x2="520" y2={i*40} stroke={g} strokeWidth="0.5" opacity="0.04" />)}

      {/* Main chain — 5 blocks */}
      {[0,1,2,3,4].map(i => {
        const x = 40 + i * 95;
        const y = 130;
        const labels = ['CREATE', 'BUDGET', 'FUND', 'SUBMIT', 'SETTLE'];
        const opacity = 0.5 + i * 0.1;
        return (
          <g key={i}>
            {/* Connection line */}
            {i > 0 && <line x1={x - 15} y1={y + 35} x2={x} y2={y + 35} stroke={g} strokeWidth="2" opacity="0.4" />}
            {i > 0 && <circle cx={x - 7} cy={y + 35} r="2" fill={g} opacity="0.6">
              <animate attributeName="cx" values={`${x-15};${x};${x-15}`} dur={`${2 + i*0.3}s`} repeatCount="indefinite" />
            </circle>}
            {/* Block */}
            <rect x={x} y={y} width="80" height="70" rx="6" stroke={g} strokeWidth="1.5" fill={g} fillOpacity="0.05" />
            <text x={x + 40} y={y + 18} textAnchor="middle" fontFamily="'JetBrains Mono', monospace" fontSize="8" fill={g} opacity="0.5">ERC-8183</text>
            <text x={x + 40} y={y + 40} textAnchor="middle" fontFamily="'Space Grotesk', sans-serif" fontSize="12" fontWeight="700" fill="#fff" opacity={opacity}>{labels[i]}</text>
            {/* Hash */}
            <text x={x + 40} y={y + 58} textAnchor="middle" fontFamily="'JetBrains Mono', monospace" fontSize="7" fill={g} opacity="0.3">
              0x{Math.random().toString(16).slice(2,8)}
            </text>
          </g>
        );
      })}

      {/* Arc curve above chain */}
      <path d="M80 120 Q260 30 500 120" stroke={g} strokeWidth="2" fill="none" opacity="0.2" strokeDasharray="6 4" />
      <text x="260" y="60" textAnchor="middle" fontFamily="'Space Grotesk', sans-serif" fontSize="14" fontWeight="700" fill={g} opacity="0.4">Arc Testnet</text>

      {/* Judge verdict flow */}
      <g transform="translate(150,240)">
        <rect width="220" height="50" rx="8" stroke={p} strokeWidth="1.5" fill={p} fillOpacity="0.05" />
        <text x="16" y="20" fontFamily="'JetBrains Mono', monospace" fontSize="9" fill={p} opacity="0.6">JUDGE VERDICT</text>
        <text x="16" y="38" fontFamily="'Space Grotesk', sans-serif" fontSize="16" fontWeight="800" fill={g}>EXECUTE</text>
        <text x="110" y="38" fontFamily="'JetBrains Mono', monospace" fontSize="10" fill="#fff" opacity="0.5">→ all_gates_passed</text>
      </g>

      {/* USDC flow */}
      <g transform="translate(150,305)">
        <rect width="220" height="40" rx="6" stroke="#F59E0B" strokeWidth="1" fill="#F59E0B" fillOpacity="0.04" />
        <text x="16" y="16" fontFamily="'JetBrains Mono', monospace" fontSize="9" fill="#F59E0B" opacity="0.6">CIRCLE USDC</text>
        <text x="16" y="32" fontFamily="'JetBrains Mono', monospace" fontSize="12" fill="#F59E0B" opacity="0.8">5.00 USDC</text>
        <text x="100" y="32" fontFamily="'JetBrains Mono', monospace" fontSize="9" fill="#F59E0B" opacity="0.4">TESTNET</text>
        <rect x="150" y="6" width="56" height="28" rx="4" fill="#F59E0B" fillOpacity="0.15" stroke="#F59E0B" strokeWidth="0.5" opacity="0.6" />
        <text x="178" y="24" textAnchor="middle" fontFamily="'JetBrains Mono', monospace" fontSize="8" fontWeight="700" fill="#F59E0B">ESCROWED</text>
      </g>

      {/* Job ID */}
      <rect x="400" y="250" width="100" height="90" rx="8" fill="#0B0F0E" fillOpacity="0.8" stroke={g} strokeWidth="1" opacity="0.5" />
      <text x="415" y="272" fontFamily="'JetBrains Mono', monospace" fontSize="9" fill={g} opacity="0.6">JOB</text>
      <text x="415" y="296" fontFamily="'Space Grotesk', sans-serif" fontSize="24" fontWeight="800" fill="#fff">#19091</text>
      <text x="415" y="316" fontFamily="'JetBrains Mono', monospace" fontSize="8" fill={g} opacity="0.4">Phase 4 Live</text>
      <circle x="480" y="258" cx="480" cy="258" r="4" fill={g} opacity="0.8">
        <animate attributeName="opacity" values="0.4;1;0.4" dur="2s" repeatCount="indefinite" />
      </circle>
    </svg>
  );
};

/* ── Spread Formula Illustration ── */
const SpreadIllustration = ({ width = 600, height = 200 }) => {
  const g = '#00DC82';
  const a = '#F59E0B';
  const b = '#60A5FA';
  return (
    <svg width={width} height={height} viewBox="0 0 600 200" fill="none" style={{ display: 'block' }}>
      {/* Formula */}
      <text x="300" y="50" textAnchor="middle" fontFamily="'JetBrains Mono', monospace" fontSize="22" fontWeight="700" fill="#fff" opacity="0.9">
        S_t = compute − k × electricity
      </text>
      {/* Arrow down */}
      <line x1="300" y1="65" x2="300" y2="95" stroke={g} strokeWidth="1.5" opacity="0.3" />
      <polygon points="294,90 300,100 306,90" fill={g} opacity="0.3" />
      {/* Values */}
      <g transform="translate(100,110)">
        <rect width="120" height="60" rx="8" stroke={b} strokeWidth="1.5" fill={b} fillOpacity="0.06" />
        <text x="60" y="24" textAnchor="middle" fontFamily="'JetBrains Mono', monospace" fontSize="9" fill={b} opacity="0.6">COMPUTE</text>
        <text x="60" y="48" textAnchor="middle" fontFamily="'JetBrains Mono', monospace" fontSize="18" fontWeight="700" fill={b}>$1.54</text>
      </g>
      <text x="255" y="148" textAnchor="middle" fontFamily="'Space Grotesk', sans-serif" fontSize="24" fontWeight="800" fill={g} opacity="0.4">−</text>
      <g transform="translate(280,110)">
        <rect width="120" height="60" rx="8" stroke={a} strokeWidth="1.5" fill={a} fillOpacity="0.06" />
        <text x="60" y="24" textAnchor="middle" fontFamily="'JetBrains Mono', monospace" fontSize="9" fill={a} opacity="0.6">ELECTRICITY</text>
        <text x="60" y="48" textAnchor="middle" fontFamily="'JetBrains Mono', monospace" fontSize="18" fontWeight="700" fill={a}>$72.34</text>
      </g>
      <text x="435" y="148" textAnchor="middle" fontFamily="'Space Grotesk', sans-serif" fontSize="24" fontWeight="800" fill={g} opacity="0.4">=</text>
      <g transform="translate(460,110)">
        <rect width="120" height="60" rx="8" stroke={g} strokeWidth="2" fill={g} fillOpacity="0.08" />
        <text x="60" y="24" textAnchor="middle" fontFamily="'JetBrains Mono', monospace" fontSize="9" fill={g} opacity="0.6">SPREAD S_t</text>
        <text x="60" y="48" textAnchor="middle" fontFamily="'JetBrains Mono', monospace" fontSize="18" fontWeight="700" fill={g}>$1.489</text>
      </g>
    </svg>
  );
};

Object.assign(window, { GridIllustration, DataCenterIllustration, BlockchainIllustration, SpreadIllustration });
