// Hand-drawn style line art. All strokes use currentColor so they follow the theme.

export function Logo({ size = 34 }) {
  return (
    <svg className="logo-mark" width={size} height={size} viewBox="0 0 40 40" aria-hidden="true">
      <rect x="1" y="1" width="38" height="38" rx="10" fill="var(--green)" />
      <path d="M7 19.5 20 9l13 10.5V32H7z" fill="var(--surface)" />
      <path d="M7 19.5 20 9l13 10.5" fill="none" stroke="var(--ink)" strokeWidth="1.6" strokeLinejoin="round" opacity=".25" />
      <path d="M17.5 16h5v4h4v5h-4v4h-5v-4h-4v-5h4z" fill="var(--orange)" />
    </svg>
  );
}

/** A string of marigolds and mango leaves, like the toran over a doorway. */
export function Toran({ flowers = 13 }) {
  const width = 600;
  const step = width / (flowers - 1);
  const sag = (x) => 10 + 14 * Math.sin((Math.PI * x) / width);
  return (
    <svg className="toran" viewBox={`0 0 ${width} 48`} preserveAspectRatio="none" aria-hidden="true">
      <path
        d={`M0 10 Q ${width / 2} 38 ${width} 10`}
        fill="none"
        stroke="var(--ink-soft)"
        strokeWidth="1.2"
        opacity=".45"
      />
      {Array.from({ length: flowers }, (_, i) => {
        const x = i * step;
        const y = sag(x);
        const leaf = i % 2 === 1;
        return (
          <g key={i} className="toran-bead" style={{ "--i": i, transformOrigin: `${x}px ${y - 6}px` }}>
            {leaf ? (
              <path d={`M${x} ${y} q 5 9 0 18 q -5 -9 0 -18z`} fill="var(--green)" opacity=".85" />
            ) : (
              <>
                <circle cx={x} cy={y + 5} r="6.5" fill="var(--orange)" />
                <circle cx={x} cy={y + 5} r="3.6" fill="var(--orange-deep)" />
                <circle cx={x} cy={y + 5} r="1.4" fill="var(--orange)" />
              </>
            )}
          </g>
        );
      })}
    </svg>
  );
}

export function Heartbeat({ className = "" }) {
  return (
    <svg className={`heartbeat ${className}`} viewBox="0 0 300 60" preserveAspectRatio="none" aria-hidden="true">
      <path
        d="M0 32 H70 l8 -6 l8 6 H110 l6 10 l10 -38 l10 46 l8 -18 H190 l8 -6 l8 6 H300"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function Goat({ size = 120 }) {
  return (
    <svg className="doodle goat" width={size} height={size * 0.8} viewBox="0 0 150 120" aria-hidden="true">
      <g fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
        <path d="M30 62c4-14 22-20 48-18 20 1 34 2 40 10 5 7 2 18-6 22-12 6-42 7-62 4-12-2-23-7-20-18z" />
        <path d="M44 80l-3 26M56 82l2 24M96 80l-2 26M108 76l4 28" />
        <path d="M30 62c-8-2-15-10-14-20 1-8 8-12 15-10 6 2 9 9 6 16" />
        <path d="M20 34c-4-8-2-16 4-20M27 32c0-8 4-14 10-15" />
        <path d="M16 46c-6 2-9 6-8 10" />
        <path d="M120 58c6-2 10 0 12 5" />
        <path className="goat-tail" d="M118 54c4-8 10-10 14-8" />
        <circle cx="22" cy="40" r="1.6" fill="currentColor" />
        <path d="M12 58c2 6 6 9 10 9" />
      </g>
    </svg>
  );
}

export function Lantern({ size = 90 }) {
  return (
    <svg className="doodle lantern" width={size} height={size * 1.3} viewBox="0 0 90 120" aria-hidden="true">
      <g fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
        <path d="M45 4v10M33 14h24M30 22h30l-4-8H34z" />
        <path d="M28 22c-6 10-8 40 0 66h34c8-26 6-56 0-66z" />
        <path d="M24 88h42l-4 10H28z" />
      </g>
      <ellipse className="lantern-flame" cx="45" cy="58" rx="7" ry="12" fill="var(--orange)" />
      <ellipse cx="45" cy="62" rx="3" ry="6" fill="var(--surface)" opacity=".75" />
    </svg>
  );
}

export function Banyan({ size = 130 }) {
  return (
    <svg className="doodle" width={size} height={size * 0.85} viewBox="0 0 150 128" aria-hidden="true">
      <g fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
        <path d="M20 58c-12-4-14-22 0-28 2-14 20-22 32-14 8-12 30-14 40-2 14-6 32 2 32 16 14 4 16 24 2 30-6 8-22 10-30 4-10 6-28 6-36 0-12 6-34 4-40-6z" />
        <path d="M68 66c2 20 0 38-6 54M82 66c-2 20 0 38 6 54M56 120h44" />
        <path d="M40 66v26M110 66v22M30 64v14" strokeDasharray="2 6" />
      </g>
    </svg>
  );
}

export function PaddyField({ size = 220 }) {
  return (
    <svg className="doodle" width={size} height={size * 0.5} viewBox="0 0 220 110" aria-hidden="true">
      <g fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
        <path d="M0 96c40-8 80-8 110 0s70 8 110 0" />
        {Array.from({ length: 11 }, (_, i) => {
          const x = 12 + i * 19;
          return (
            <g key={i} className="paddy" style={{ "--i": i, transformOrigin: `${x}px 92px` }}>
              <path d={`M${x} 92c0-18 2-30 8-40M${x} 92c-2-14-8-24-14-28M${x} 92c2-10 8-18 14-20`} />
            </g>
          );
        })}
        <circle cx="180" cy="22" r="12" stroke="var(--orange)" />
      </g>
    </svg>
  );
}

export function SignalBars({ level = 4, className = "" }) {
  return (
    <svg className={`signal-bars ${className}`} viewBox="0 0 20 16" width="20" height="16" aria-hidden="true">
      {[0, 1, 2, 3].map((i) => (
        <rect
          key={i}
          x={i * 5}
          y={12 - i * 3.6}
          width="3.4"
          height={4 + i * 3.6}
          rx="1"
          className={i < level ? "on" : "off"}
        />
      ))}
    </svg>
  );
}
