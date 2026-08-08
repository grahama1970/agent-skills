/** The no-match illustration: a node-graph "fail whale". A single filled query
 *  node reaches out with dotted feeler-edges to empty, hollow targets — nothing
 *  to connect to. Spoken in the constellation's own visual language, and honest:
 *  the search reached out and found no real node. Static (no motion); purely
 *  decorative, so aria-hidden. */
export function SearchMiss() {
  // hollow "nothing" targets the query node reached toward
  const targets = [
    { x: 34, y: 30 },
    { x: 210, y: 26 },
    { x: 28, y: 96 },
    { x: 206, y: 104 },
  ];
  const cx = 120;
  const cy = 66;
  return (
    <svg
      className="search-miss"
      viewBox="0 0 240 132"
      role="img"
      aria-hidden="true"
      focusable="false"
    >
      {targets.map((t, i) => (
        <line
          key={i}
          x1={cx}
          y1={cy}
          x2={t.x}
          y2={t.y}
          className="sm-edge"
        />
      ))}
      {targets.map((t, i) => (
        <circle key={`t${i}`} cx={t.x} cy={t.y} r={7} className="sm-empty" />
      ))}
      {/* the query node — present, reaching, unmatched */}
      <circle cx={cx} cy={cy} r={17} className="sm-core" />
      <circle cx={cx} cy={cy} r={17} className="sm-ring" />
      <text x={cx} y={cy + 5} textAnchor="middle" className="sm-q">
        ?
      </text>
    </svg>
  );
}
