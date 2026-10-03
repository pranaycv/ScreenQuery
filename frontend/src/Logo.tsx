/**
 * ScreenQuery mark in the EyesRhythm family: the same soft-blue rounded
 * square. The glyph is a screen with a question mark, not an eye.
 */
export function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
      className="er-logo"
    >
      <rect className="er-logo__mark" x="2" y="2" width="60" height="60" rx="18" />
      <rect x="13" y="17" width="38" height="30" rx="8" fill="#ffffff" />
      <text
        x="32"
        y="33.5"
        textAnchor="middle"
        dominantBaseline="central"
        fill="#1A2A38"
        fontFamily="Inter, system-ui, sans-serif"
        fontWeight="700"
        fontSize="20"
      >
        ?
      </text>
    </svg>
  );
}
