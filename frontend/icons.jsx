/* Arc Compute Sec — Custom SVG Icons */

const IconGrid = ({ size = 48, color = '#00DC82' }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    {/* Transmission tower */}
    <path d="M24 4L18 18h12L24 4z" stroke={color} strokeWidth="2" strokeLinejoin="round" fill={color + '15'} />
    <line x1="24" y1="18" x2="24" y2="42" stroke={color} strokeWidth="2" />
    <line x1="18" y1="18" x2="14" y2="42" stroke={color} strokeWidth="1.5" />
    <line x1="30" y1="18" x2="34" y2="42" stroke={color} strokeWidth="1.5" />
    {/* Cross braces */}
    <line x1="17" y1="26" x2="31" y2="26" stroke={color} strokeWidth="1" opacity="0.6" />
    <line x1="16" y1="34" x2="32" y2="34" stroke={color} strokeWidth="1" opacity="0.6" />
    {/* Power lines */}
    <path d="M4 14Q12 18 18 14" stroke={color} strokeWidth="1.5" fill="none" strokeLinecap="round" opacity="0.7" />
    <path d="M30 14Q36 18 44 14" stroke={color} strokeWidth="1.5" fill="none" strokeLinecap="round" opacity="0.7" />
    {/* Ground */}
    <line x1="10" y1="42" x2="38" y2="42" stroke={color} strokeWidth="1.5" opacity="0.4" />
    {/* Sparks */}
    <circle cx="24" cy="8" r="1.5" fill={color} opacity="0.8" />
  </svg>
);

const IconFactory = ({ size = 48, color = '#60A5FA' }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    {/* Main building */}
    <rect x="6" y="20" width="36" height="22" rx="2" stroke={color} strokeWidth="2" fill={color + '10'} />
    {/* Roof / ventilation */}
    <path d="M6 20L14 10V20" stroke={color} strokeWidth="2" fill={color + '08'} />
    <path d="M14 20L22 10V20" stroke={color} strokeWidth="2" fill={color + '08'} />
    <path d="M22 20L30 10V20" stroke={color} strokeWidth="2" fill={color + '08'} />
    {/* Chimney */}
    <rect x="34" y="6" width="5" height="14" rx="1" stroke={color} strokeWidth="1.5" fill={color + '15'} />
    {/* Smoke */}
    <circle cx="36.5" cy="4" r="1.5" fill={color} opacity="0.3" />
    <circle cx="38" cy="2" r="1" fill={color} opacity="0.2" />
    {/* Windows / server racks */}
    <rect x="10" y="26" width="4" height="6" rx="1" fill={color} opacity="0.4" />
    <rect x="17" y="26" width="4" height="6" rx="1" fill={color} opacity="0.4" />
    <rect x="24" y="26" width="4" height="6" rx="1" fill={color} opacity="0.4" />
    <rect x="31" y="26" width="4" height="6" rx="1" fill={color} opacity="0.4" />
    {/* Status LEDs */}
    <circle cx="12" cy="37" r="1.5" fill={color} opacity="0.8" />
    <circle cx="19" cy="37" r="1.5" fill={color} opacity="0.6" />
    <circle cx="26" cy="37" r="1.5" fill={color} opacity="0.8" />
    <circle cx="33" cy="37" r="1.5" fill={color} opacity="0.6" />
  </svg>
);

const IconCoin = ({ size = 48, color = '#F59E0B' }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    {/* Outer ring */}
    <circle cx="24" cy="24" r="18" stroke={color} strokeWidth="2" fill={color + '10'} />
    <circle cx="24" cy="24" r="14" stroke={color} strokeWidth="1" opacity="0.3" />
    {/* USDC style */}
    <text x="24" y="20" textAnchor="middle" fontFamily="'Space Grotesk', sans-serif" fontSize="8" fontWeight="700" fill={color} opacity="0.5">USDC</text>
    <text x="24" y="31" textAnchor="middle" fontFamily="'Space Grotesk', sans-serif" fontSize="14" fontWeight="800" fill={color}>$</text>
    {/* Circle dots */}
    <circle cx="24" cy="8" r="1.5" fill={color} opacity="0.6" />
    <circle cx="24" cy="40" r="1.5" fill={color} opacity="0.6" />
    <circle cx="8" cy="24" r="1.5" fill={color} opacity="0.6" />
    <circle cx="40" cy="24" r="1.5" fill={color} opacity="0.6" />
    {/* Testnet badge */}
    <rect x="28" y="34" width="16" height="10" rx="5" fill={color} />
    <text x="36" y="41" textAnchor="middle" fontFamily="'JetBrains Mono', monospace" fontSize="6" fontWeight="700" fill="#000">TEST</text>
  </svg>
);

const IconPrediction = ({ size = 48, color = '#A78BFA' }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    {/* Chart frame */}
    <line x1="8" y1="40" x2="8" y2="8" stroke={color} strokeWidth="1.5" strokeLinecap="round" opacity="0.4" />
    <line x1="8" y1="40" x2="42" y2="40" stroke={color} strokeWidth="1.5" strokeLinecap="round" opacity="0.4" />
    {/* Probability bars */}
    <rect x="12" y="24" width="5" height="16" rx="2" fill={color} opacity="0.3" />
    <rect x="20" y="16" width="5" height="24" rx="2" fill={color} opacity="0.5" />
    <rect x="28" y="10" width="5" height="30" rx="2" fill={color} opacity="0.7" />
    <rect x="36" y="20" width="5" height="20" rx="2" fill={color} opacity="0.4" />
    {/* Trend line */}
    <path d="M14.5 22 L22.5 14 L30.5 8 L38.5 18" stroke={color} strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    {/* Data points */}
    <circle cx="14.5" cy="22" r="2.5" fill={color} />
    <circle cx="22.5" cy="14" r="2.5" fill={color} />
    <circle cx="30.5" cy="8" r="2.5" fill={color} />
    <circle cx="38.5" cy="18" r="2.5" fill={color} />
    {/* Yes/No labels */}
    <text x="16" y="47" textAnchor="middle" fontFamily="'JetBrains Mono', monospace" fontSize="5" fill={color} opacity="0.5">Y</text>
    <text x="24" y="47" textAnchor="middle" fontFamily="'JetBrains Mono', monospace" fontSize="5" fill={color} opacity="0.5">Y</text>
    <text x="32" y="47" textAnchor="middle" fontFamily="'JetBrains Mono', monospace" fontSize="5" fill={color} opacity="0.5">Y</text>
    <text x="40" y="47" textAnchor="middle" fontFamily="'JetBrains Mono', monospace" fontSize="5" fill={color} opacity="0.5">N</text>
  </svg>
);

const IconJudge = ({ size = 48, color = '#00DC82' }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    {/* Scale base */}
    <line x1="24" y1="8" x2="24" y2="38" stroke={color} strokeWidth="2" />
    <rect x="16" y="38" width="16" height="4" rx="2" fill={color} opacity="0.3" />
    {/* Beam */}
    <line x1="8" y1="14" x2="40" y2="18" stroke={color} strokeWidth="2" strokeLinecap="round" />
    {/* Left pan */}
    <path d="M4 14L8 14L12 14L10 24H6L4 14z" stroke={color} strokeWidth="1.5" fill={color + '20'} strokeLinejoin="round" />
    <line x1="4" y1="14" x2="12" y2="14" stroke={color} strokeWidth="1.5" />
    {/* Right pan */}
    <path d="M36 18L40 18L44 18L42 28H38L36 18z" stroke={color} strokeWidth="1.5" fill={color + '20'} strokeLinejoin="round" />
    <line x1="36" y1="18" x2="44" y2="18" stroke={color} strokeWidth="1.5" />
    {/* Pivot */}
    <circle cx="24" cy="10" r="3" fill={color} opacity="0.6" />
    {/* Check mark in right pan */}
    <path d="M38.5 22L40 23.5L42.5 21" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const IconSignal = ({ size = 48, color = '#00DC82' }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    {/* Waveform */}
    <path d="M4 24 L10 24 L13 12 L17 36 L21 8 L25 40 L29 16 L33 32 L36 24 L44 24"
      stroke={color} strokeWidth="2.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    {/* Baseline */}
    <line x1="4" y1="24" x2="44" y2="24" stroke={color} strokeWidth="0.5" opacity="0.2" strokeDasharray="2 2" />
    {/* Threshold lines */}
    <line x1="4" y1="14" x2="44" y2="14" stroke={color} strokeWidth="0.5" opacity="0.15" strokeDasharray="4 2" />
    <line x1="4" y1="34" x2="44" y2="34" stroke={color} strokeWidth="0.5" opacity="0.15" strokeDasharray="4 2" />
    {/* +σ / -σ labels */}
    <text x="46" y="15" fontFamily="'JetBrains Mono', monospace" fontSize="5" fill={color} opacity="0.4">+σ</text>
    <text x="46" y="35" fontFamily="'JetBrains Mono', monospace" fontSize="5" fill={color} opacity="0.4">-σ</text>
  </svg>
);

const IconArc = ({ size = 48, color = '#00DC82' }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
    {/* Blockchain blocks */}
    <rect x="4" y="18" width="10" height="10" rx="2" stroke={color} strokeWidth="1.5" fill={color + '15'} />
    <rect x="19" y="18" width="10" height="10" rx="2" stroke={color} strokeWidth="1.5" fill={color + '15'} />
    <rect x="34" y="18" width="10" height="10" rx="2" stroke={color} strokeWidth="1.5" fill={color + '15'} />
    {/* Chain links */}
    <line x1="14" y1="23" x2="19" y2="23" stroke={color} strokeWidth="1.5" />
    <line x1="29" y1="23" x2="34" y2="23" stroke={color} strokeWidth="1.5" />
    {/* Hash symbols inside */}
    <text x="9" y="25" textAnchor="middle" fontFamily="'JetBrains Mono', monospace" fontSize="6" fill={color} opacity="0.7">#</text>
    <text x="24" y="25" textAnchor="middle" fontFamily="'JetBrains Mono', monospace" fontSize="6" fill={color} opacity="0.7">#</text>
    <text x="39" y="25" textAnchor="middle" fontFamily="'JetBrains Mono', monospace" fontSize="6" fill={color} opacity="0.7">#</text>
    {/* Arc curve on top */}
    <path d="M9 16Q24 4 39 16" stroke={color} strokeWidth="2" fill="none" strokeLinecap="round" />
    <circle cx="24" cy="8" r="2" fill={color} opacity="0.6" />
    {/* Settlement arrows */}
    <path d="M9 30L9 36" stroke={color} strokeWidth="1" opacity="0.4" />
    <path d="M24 30L24 36" stroke={color} strokeWidth="1" opacity="0.4" />
    <path d="M39 30L39 36" stroke={color} strokeWidth="1" opacity="0.4" />
    <text x="24" y="42" textAnchor="middle" fontFamily="'JetBrains Mono', monospace" fontSize="5" fill={color} opacity="0.4">ERC-8183</text>
  </svg>
);

Object.assign(window, { IconGrid, IconFactory, IconCoin, IconPrediction, IconJudge, IconSignal, IconArc });
