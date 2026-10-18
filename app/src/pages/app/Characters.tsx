// The tour's guides: outlined, flat-colour blobs with props, sitting on the ground (they don't float).
export type CharacterName = 'sunny' | 'bea' | 'rory' | 'pip' | 'echo';

const INK = '#1f2a24';
const PAPER = '#fdf3d8';
const ACCENT = '#ed6a3c';

const BG: Record<CharacterName, string> = {
  sunny: '#fdeee7',
  bea: '#e6f4ec',
  rory: '#e4f0f8',
  pip: '#fbf3e1',
  echo: '#efe9fb',
};

/** A sticky note, like the ones stuck around the desk. */
const Note = ({ x, y, r }: { x: number; y: number; r: number }) => (
  <g transform={`translate(${x} ${y}) rotate(${r})`}>
    <rect width="24" height="24" rx="2" fill={PAPER} />
    <path d="M6 9 h12 M6 15 h8" />
  </g>
);

const Cheeks = ({ y, dx = 22 }: { y: number; dx?: number }) => (
  <g fill="#f48c8c" opacity=".5" stroke="none">
    <ellipse cx={100 - dx} cy={y} rx="6" ry="3.5" />
    <ellipse cx={100 + dx} cy={y} rx="6" ry="3.5" />
  </g>
);

const Dots = ({ y, gap = 13 }: { y: number; gap?: number }) => (
  <g className="eyes" fill={INK} stroke="none">
    <ellipse cx={100 - gap} cy={y} rx="3.6" ry="4.6" />
    <ellipse cx={100 + gap} cy={y} rx="3.6" ry="4.6" />
  </g>
);

const Ground = () => <path d="M14 150 H186" />;

const SCENES: Record<CharacterName, React.ReactNode> = {
  sunny: (
    <>
      <Note x={18} y={38} r={-12} />
      <Note x={156} y={24} r={10} />
      <path d="M52 150 C42 122 44 84 66 64 C86 46 118 46 136 62 C158 82 160 122 150 150 Z" fill="#f4a259" />
      <path d="M92 52 C88 40 98 34 102 45 C104 34 116 36 111 50" fill="none" />
      <path d="M54 112 C44 116 42 128 50 132" fill="none" />
      <g className="wave">
        <path d="M148 106 C162 98 168 86 170 76" fill="none" />
        <circle cx="171" cy="68" r="8.5" fill="#f4a259" />
      </g>
      <path d="M84 84 l6 -2 M116 84 l-6 -2" />
      <Dots y={96} gap={13} />
      <Cheeks y={108} />
      <path d="M90 112 Q100 123 110 112" fill="none" />
      <Ground />
    </>
  ),
  bea: (
    <>
      <Note x={16} y={30} r={-8} />
      <path d="M58 150 C50 112 52 70 74 52 C90 38 112 38 128 52 C150 70 152 112 144 150 Z" fill="#8fd1a6" />
      <path d="M86 72 l7 -3 M114 72 l-7 -3" />
      <Dots y={82} gap={12} />
      <Cheeks y={94} dx={20} />
      <path d="M92 97 Q100 108 108 97 Z" fill={INK} />
      <path d="M58 150 L66 106 H134 L142 150 Z" fill="#e8613c" />
      <circle cx="100" cy="128" r="9" fill={PAPER} />
      <path
        d="M100 121 v14 M104 124 c-2 -2 -8 -2 -8 1.5 c0 3.5 8 2 8 5.5 c0 3.5 -6 3.5 -8 1.5"
        fill="none"
        strokeWidth="2.2"
      />
      <circle cx="70" cy="106" r="7.5" fill="#8fd1a6" />
      <circle cx="130" cy="106" r="7.5" fill="#8fd1a6" />
      <path d="M152 124 h22 v22 a4 4 0 0 1 -4 4 h-14 a4 4 0 0 1 -4 -4 Z" fill={PAPER} />
      <path d="M174 129 c8 0 8 12 0 12" fill="none" />
      <path d="M158 116 c-3 -4 3 -6 0 -10 M166 116 c-3 -4 3 -6 0 -10" fill="none" strokeWidth="2.2" />
      <Ground />
    </>
  ),
  rory: (
    <>
      <path d="M48 150 C40 116 46 78 72 62 C92 50 116 50 134 62 C160 80 162 118 154 150 Z" fill="#8cc0e8" />
      <path d="M70 66 C74 40 130 40 134 66 Z" fill={ACCENT} />
      <path d="M128 62 C142 59 158 61 162 68 C150 71 137 69 126 68 Z" fill={ACCENT} />
      <path d="M84 83 l9 -3 M118 83 l-9 -3" />
      <Dots y={92} gap={14} />
      <Cheeks y={104} dx={24} />
      <path d="M92 104 Q101 112 110 104" fill="none" />
      <rect x="50" y="114" width="100" height="36" rx="3" fill={PAPER} />
      <path d="M83 114 v36 M117 114 v36" strokeWidth="2" />
      <path d="M58 143 C74 136 82 126 98 130 S124 122 136 122" fill="none" stroke={ACCENT} strokeDasharray="4 4" />
      <circle cx="138" cy="122" r="4.5" fill={ACCENT} />
      <circle cx="54" cy="116" r="7" fill="#8cc0e8" />
      <circle cx="146" cy="116" r="7" fill="#8cc0e8" />
      <Ground />
    </>
  ),
  pip: (
    <>
      <Note x={160} y={32} r={8} />
      <path d="M56 150 C46 118 50 76 74 58 C92 46 114 48 130 60 C152 78 154 118 146 150 Z" fill="#f6d06e" />
      <g transform="rotate(28 140 52)">
        <rect x="134" y="30" width="9" height="34" rx="2" fill={ACCENT} />
        <path d="M134 64 l4.5 8 l4.5 -8 Z" fill={PAPER} />
      </g>
      <circle cx="87" cy="88" r="11" fill="#ffffff80" />
      <circle cx="115" cy="88" r="11" fill="#ffffff80" />
      <path d="M98 88 h6" />
      <g className="eyes" fill={INK} stroke="none">
        <circle cx="87" cy="89" r="3.4" />
        <circle cx="115" cy="89" r="3.4" />
      </g>
      <path d="M93 108 Q102 114 111 105" fill="none" />
      <rect x="104" y="100" width="46" height="48" rx="4" fill={PAPER} />
      <rect x="118" y="95" width="18" height="9" rx="2" fill="#9aa59e" />
      <path d="M111 116 l3 3 l6 -7 M111 132 l3 3 l6 -7" fill="none" stroke="#1f8a5b" />
      <path d="M126 116 h16 M126 132 h12" strokeWidth="2.2" />
      <circle cx="104" cy="124" r="7" fill="#f6d06e" />
      <path d="M58 112 C48 118 48 128 54 132" fill="none" />
      <Ground />
    </>
  ),
  echo: (
    <>
      <path
        d="M134 14 h46 a8 8 0 0 1 8 8 v18 a8 8 0 0 1 -8 8 h-24 l-10 9 v-9 h-12 a8 8 0 0 1 -8 -8 v-18 a8 8 0 0 1 8 -8 Z"
        fill="#fff"
      />
      <g fill={INK} stroke="none">
        <circle cx="146" cy="31" r="3" />
        <circle cx="157" cy="31" r="3" />
        <circle cx="168" cy="31" r="3" />
      </g>
      <path d="M60 150 C52 112 54 72 76 54 C92 42 112 42 126 54 C148 72 150 112 142 150 Z" fill="#c9b8f0" />
      <path d="M66 74 C66 30 136 30 136 74" fill="none" strokeWidth="5" />
      <rect x="56" y="66" width="14" height="26" rx="6" fill={ACCENT} />
      <rect x="132" y="66" width="14" height="26" rx="6" fill={ACCENT} />
      <g className="eyes">
        <path d="M83 88 Q89 81 95 88 M107 88 Q113 81 119 88" fill="none" />
      </g>
      <Cheeks y={98} dx={21} />
      <path d="M92 100 Q100 111 108 100 Z" fill={INK} />
      <rect x="64" y="106" width="24" height="38" rx="5" fill="#2b3437" />
      <rect x="68" y="111" width="16" height="26" rx="2" fill="#8cc0e8" strokeWidth="2" />
      <circle cx="90" cy="120" r="7" fill="#c9b8f0" />
      <path d="M140 112 C150 118 150 128 144 132" fill="none" />
      <Ground />
    </>
  ),
};

export function Character({ name }: { name: CharacterName }) {
  return (
    <div className="character" style={{ background: BG[name] }}>
      <svg className="character-art" viewBox="0 0 200 165" aria-hidden="true">
        <g stroke={INK} strokeWidth="3" strokeLinejoin="round" strokeLinecap="round">
          {SCENES[name]}
        </g>
      </svg>
    </div>
  );
}
