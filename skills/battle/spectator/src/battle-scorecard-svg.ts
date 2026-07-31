/**
 * Red vs Blue scorecard — user-supplied SVG (self-contained transparent card,
 * faithful to battle-004 core mockup). `__RED_SCORE__` / `__BLUE_SCORE__` are
 * substituted with real receipt scores at render time; a null score becomes a
 * muted em dash (never faked). Scores are `text-anchor="middle"` so a single
 * "—" centers cleanly.
 */
export const BATTLE_SCORECARD_SVG = `<svg xmlns="http://www.w3.org/2000/svg"
     viewBox="0 0 666 143"
     role="img"
     aria-labelledby="score-title score-desc">
  <title id="score-title">Red Team versus Blue Team score</title>
  <desc id="score-desc">Red Team versus Blue Team score.</desc>

  <defs>
    <style>
      text {
        font-family: "Rajdhani", "Roboto Condensed", "Arial Narrow", sans-serif;
        text-rendering: geometricPrecision;
        font-variant-numeric: tabular-nums;
        user-select: none;
      }
      .team-label { font-size: 25px; font-weight: 700; letter-spacing: .8px; }
      .score { font-size: 64px; font-weight: 600; }
      .versus { font-size: 30px; font-weight: 500; letter-spacing: .2px; }
    </style>

    <path id="panel-shape"
          d="M26 1.5 H639 L664.5 27 V116 L639 141.5 H26 L1.5 116 V27 Z" />

    <clipPath id="panel-clip">
      <use href="#panel-shape" />
    </clipPath>

    <linearGradient id="panel-fill" x1="0" y1="71.5" x2="666" y2="71.5" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#070912" />
      <stop offset=".32" stop-color="#0b0710" />
      <stop offset=".50" stop-color="#030914" />
      <stop offset=".70" stop-color="#030c19" />
      <stop offset="1" stop-color="#040a13" />
    </linearGradient>

    <linearGradient id="frame-stroke" x1="0" y1="71.5" x2="666" y2="71.5" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#172435" />
      <stop offset=".18" stop-color="#283044" />
      <stop offset=".32" stop-color="#52202a" />
      <stop offset=".49" stop-color="#1a2030" />
      <stop offset=".67" stop-color="#17344f" />
      <stop offset=".85" stop-color="#21415d" />
      <stop offset="1" stop-color="#192a3a" />
    </linearGradient>

    <radialGradient id="red-atmosphere" cx="0" cy="0" r="1"
                    gradientTransform="translate(195 110) rotate(90) scale(118 234)"
                    gradientUnits="userSpaceOnUse">
      <stop stop-color="#d71e2a" stop-opacity=".16" />
      <stop offset=".43" stop-color="#9b1420" stop-opacity=".07" />
      <stop offset="1" stop-color="#5a0c16" stop-opacity="0" />
    </radialGradient>

    <radialGradient id="blue-atmosphere" cx="0" cy="0" r="1"
                    gradientTransform="translate(516 109) rotate(90) scale(120 230)"
                    gradientUnits="userSpaceOnUse">
      <stop stop-color="#0879de" stop-opacity=".18" />
      <stop offset=".44" stop-color="#075aa6" stop-opacity=".075" />
      <stop offset="1" stop-color="#06396a" stop-opacity="0" />
    </radialGradient>

    <linearGradient id="center-shade" x1="243" y1="0" x2="428" y2="143" gradientUnits="userSpaceOnUse">
      <stop stop-color="#130912" stop-opacity=".46" />
      <stop offset=".48" stop-color="#030914" stop-opacity=".89" />
      <stop offset="1" stop-color="#03111f" stop-opacity=".44" />
    </linearGradient>

    <pattern id="scanlines" width="4" height="4" patternUnits="userSpaceOnUse">
      <path d="M0 .5 H4" stroke="#ffffff" stroke-width="1" opacity=".035" />
    </pattern>

    <filter id="red-glow" x="-80%" y="-80%" width="260%" height="260%">
      <feGaussianBlur in="SourceGraphic" stdDeviation="2.1" result="blur" />
      <feColorMatrix in="blur" type="matrix" values="1 0 0 0 0 0 .15 0 0 0 0 0 .15 0 0 0 0 0 .65 0" result="glow" />
      <feMerge>
        <feMergeNode in="glow" />
        <feMergeNode in="SourceGraphic" />
      </feMerge>
    </filter>

    <filter id="blue-glow" x="-80%" y="-80%" width="260%" height="260%">
      <feGaussianBlur in="SourceGraphic" stdDeviation="2.1" result="blur" />
      <feColorMatrix in="blur" type="matrix" values=".15 0 0 0 0 0 .55 0 0 0 0 0 1 0 0 0 0 0 .68 0" result="glow" />
      <feMerge>
        <feMergeNode in="glow" />
        <feMergeNode in="SourceGraphic" />
      </feMerge>
    </filter>

    <filter id="soft-red-line" x="-20%" y="-300%" width="140%" height="700%">
      <feGaussianBlur stdDeviation="3.2" />
    </filter>

    <filter id="soft-blue-line" x="-20%" y="-300%" width="140%" height="700%">
      <feGaussianBlur stdDeviation="3.2" />
    </filter>
  </defs>

  <use href="#panel-shape" fill="url(#panel-fill)" stroke="#09121f" stroke-width="3" />
  <use href="#panel-shape" fill="none" stroke="url(#frame-stroke)" stroke-width="2" opacity=".86" />

  <g clip-path="url(#panel-clip)">
    <rect width="666" height="143" fill="url(#panel-fill)" />
    <ellipse cx="195" cy="110" rx="234" ry="118" fill="url(#red-atmosphere)" />
    <ellipse cx="516" cy="109" rx="230" ry="120" fill="url(#blue-atmosphere)" />

    <path d="M244 0 H427 L346 83 L425 143 H244 L326 83 Z" fill="url(#center-shade)" opacity=".58" />

    <path d="M255 0 L336 83 L258 143" fill="none" stroke="#8f1724" stroke-width="2.2" opacity=".14" />
    <path d="M418 0 L336 83 L417 143" fill="none" stroke="#0b4e86" stroke-width="2.2" opacity=".15" />
    <path d="M336 83 L282 28" fill="none" stroke="#a21b28" stroke-width="1.3" opacity=".09" />
    <path d="M336 83 L393 27" fill="none" stroke="#1261a4" stroke-width="1.3" opacity=".09" />

    <path d="M52 31 H112" stroke="#d92a33" stroke-width="2" opacity=".045" />
    <path d="M547 31 H593" stroke="#299cff" stroke-width="2" opacity=".052" />

    <rect width="666" height="143" fill="url(#scanlines)" />
  </g>

  <path d="M26 141.5 H305" stroke="#ff343d" stroke-width="2.5" opacity=".28" filter="url(#soft-red-line)" />
  <path d="M26 141.5 H307" stroke="#ff3e47" stroke-width="1.1" opacity=".67" />
  <path d="M398 141.5 H640" stroke="#2d9cff" stroke-width="2.5" opacity=".28" filter="url(#soft-blue-line)" />
  <path d="M397 141.5 H640" stroke="#359fff" stroke-width="1.1" opacity=".62" />

  <!-- Team emblems: lucide Bug (red) / Shield (blue), 24x24 icons scaled up to
       read at the mockup's emblem weight (~score height). -->
  <g transform="translate(25 47) scale(2.9)" fill="none" stroke="#ff4349" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round" filter="url(#red-glow)" aria-hidden="true">
    <path d="m8 2 1.88 1.88" />
    <path d="M14.12 3.88 16 2" />
    <path d="M9 7.13v-1a3.003 3.003 0 1 1 6 0v1" />
    <path d="M12 20c-3.3 0-6-2.7-6-6v-3a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v3c0 3.3-2.7 6-6 6" />
    <path d="M12 20v-9" />
    <path d="M6.53 9C4.6 8.8 3 7.1 3 5" />
    <path d="M6 13H2" />
    <path d="M3 21c0-2.1 1.7-3.9 3.8-4" />
    <path d="M20.97 5c0 2.1-1.6 3.8-3.5 4" />
    <path d="M22 13h-4" />
    <path d="M17.2 17c2.1.1 3.8 1.9 3.8 4" />
  </g>

  <g transform="translate(571 47) scale(2.9)" fill="none" stroke="#42a6ff" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round" filter="url(#blue-glow)" aria-hidden="true">
    <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" />
  </g>

  <g fill="#ff4d52" filter="url(#red-glow)">
    <text id="red-label" class="team-label" x="124" y="43">RED TEAM</text>
    <text id="red-score" class="score" x="183" y="111" text-anchor="middle">__RED_SCORE__</text>
  </g>

  <text class="versus" x="333" y="98" text-anchor="middle" fill="#68758b" opacity=".92">VS</text>

  <g fill="#3c9fff" filter="url(#blue-glow)">
    <text id="blue-label" class="team-label" x="415" y="43">BLUE TEAM</text>
    <text id="blue-score" class="score" x="483" y="111" text-anchor="middle">__BLUE_SCORE__</text>
  </g>
</svg>`;
