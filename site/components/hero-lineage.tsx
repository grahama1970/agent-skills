export interface HeroLineageNode {
  id: 'G0' | 'G1-A' | 'G1-B' | 'G2';
  mutationOperator: string | null;
  noveltyDistance: number | null;
  techniqueDelta: string;
  changedDimensions: Array<{
    dimension: string;
    parent: string;
    child: string;
  }>;
}

export interface HeroLineageData {
  battleId: 'battle-004';
  runId: string;
  sourceSha256: string;
  qualification: 'PASS';
  criterion: 'novelty_distance';
  selectedId: 'G1-A';
  runnerUpId: 'G1-B';
  nodes: Record<HeroLineageNode['id'], HeroLineageNode>;
}

/**
 * Recorded battle-004 adaptive lineage, rendered as an unboxed instrument in
 * the Inventory rail. Every value comes from generated/battle-lineage.json;
 * the component has no fixture defaults. G1-A owns the solid parent lineage
 * to G2; G1-B stays visible as runner-up whose evidence terminates at a
 * selection-receipt sidecar, not a co-parent junction.
 */
export function HeroLineage({ data }: { data: HeroLineageData }) {
  const g1a = data.nodes['G1-A'];
  const g1b = data.nodes['G1-B'];
  const g2 = data.nodes.G2;
  const runStamp = data.runId.replace('arena-adaptive-lineage-', '');

  return (
    <figure
      className="proof-lineage"
      data-qid="hero:proof-lineage"
      data-battle-id={data.battleId}
      data-source-sha256={data.sourceSha256}
    >
      <div className="proof-lineage__header">
        <span>Adaptive lineage</span>
        <span>{data.battleId}</span>
      </div>
      <svg
        className="proof-lineage__svg"
        viewBox="0 0 360 224"
        role="img"
        aria-labelledby="proof-lineage-title proof-lineage-desc"
      >
        <title id="proof-lineage-title">Recorded Battle adaptive lineage</title>
        <desc id="proof-lineage-desc">
          G0 produces candidates G1-A and G1-B. G1-A is selected by novelty
          distance and becomes the parent of G2. G1-B remains visible as
          runner-up evidence.
        </desc>

        {/* Root and candidate branches */}
        <path
          className="proof-lineage__edge proof-lineage__edge--trunk"
          d="M180 21 V49"
          pathLength="1"
        />
        <path
          className="proof-lineage__edge proof-lineage__edge--branch-a"
          d="M180 49 H74 V64"
          pathLength="1"
        />
        <path
          className="proof-lineage__edge proof-lineage__edge--branch-b"
          d="M180 49 H286 V64"
          pathLength="1"
        />
        {/* Only selected G1-A owns the solid parent lineage to G2. */}
        <path
          className="proof-lineage__edge proof-lineage__edge--selected"
          d="M74 69 V142 C74 166 126 176 180 176"
          pathLength="1"
        />
        {/* Runner-up evidence: dotted edge to the selection-receipt sidecar. */}
        <path
          className="proof-lineage__edge proof-lineage__edge--evidence"
          d="M286 69 V142 C286 158 248 166 212 166"
          pathLength="1"
        />
        {/* G2 continues the selected lineage downward. */}
        <path
          className="proof-lineage__edge proof-lineage__edge--g2"
          d="M180 176 V193"
          pathLength="1"
        />

        {/* G0 root — the bridge's return target. */}
        <g className="proof-lineage__node proof-lineage__node--g0">
          <rect
            data-proof-entry
            className="proof-lineage__node-core"
            x="177.5"
            y="13.5"
            width="5"
            height="5"
          />
          <text className="proof-lineage__id" x="191" y="19">
            G0
          </text>
          <text className="proof-lineage__operator" x="191" y="30">
            seed exploit
          </text>
        </g>

        {/* G1-A selected: base core + evaluation halo + selection overlay. */}
        <g
          className="proof-lineage__node proof-lineage__node--g1a"
          tabIndex={0}
          role="group"
          aria-label={`G1-A selected. ${g1a.techniqueDelta}`}
        >
          <title>{g1a.techniqueDelta}</title>
          <rect className="proof-lineage__eval-halo" x="69" y="61" width="10" height="10" />
          <rect className="proof-lineage__node-core" x="71.5" y="63.5" width="5" height="5" />
          <rect className="proof-lineage__selected-overlay" x="71.5" y="63.5" width="5" height="5" />
          <text className="proof-lineage__id" x="16" y="84">
            G1-A
          </text>
          <text className="proof-lineage__operator" x="16" y="97">
            {g1a.mutationOperator}
          </text>
          <text className="proof-lineage__meta" x="16" y="110">
            ν {g1a.noveltyDistance} · Δast {g1a.changedDimensions.length}
          </text>
          <circle className="proof-lineage__judge-dot" cx="74" cy="122" r="1.7" />
          <text className="proof-lineage__judge-label" x="82" y="125">
            judge
          </text>
          <text
            className="proof-lineage__role proof-lineage__role--selected"
            x="16"
            y="140"
          >
            selected · {data.criterion}
          </text>
        </g>

        {/* G1-B runner-up: base core + evaluation halo + runner outline. */}
        <g
          className="proof-lineage__node proof-lineage__node--g1b"
          tabIndex={0}
          role="group"
          aria-label={`G1-B runner-up. ${g1b.techniqueDelta}`}
        >
          <title>{g1b.techniqueDelta}</title>
          <rect className="proof-lineage__eval-halo" x="281" y="61" width="10" height="10" />
          <rect className="proof-lineage__node-core" x="283.5" y="63.5" width="5" height="5" />
          <rect className="proof-lineage__runner-outline" x="281.5" y="61.5" width="9" height="9" />
          <text className="proof-lineage__id" x="196" y="84">
            G1-B
          </text>
          <text className="proof-lineage__operator" x="196" y="97">
            {g1b.mutationOperator}
          </text>
          <text className="proof-lineage__meta" x="196" y="110">
            ν {g1b.noveltyDistance} · Δast {g1b.changedDimensions.length}
          </text>
          <circle className="proof-lineage__judge-dot" cx="286" cy="122" r="1.7" />
          <text className="proof-lineage__judge-label" x="294" y="125">
            judge
          </text>
          <text
            className="proof-lineage__role proof-lineage__role--runner"
            x="196"
            y="140"
          >
            runner-up · retained
          </text>
        </g>

        {/* Selection receipt sidecar */}
        <g className="proof-lineage__receipt">
          <rect x="209.5" y="163.5" width="5" height="5" />
          <text x="221" y="174">
            selection receipt
          </text>
        </g>

        {/* G2 */}
        <g className="proof-lineage__node proof-lineage__node--g2">
          <title>{g2.techniqueDelta}</title>
          <rect className="proof-lineage__node-core" x="177.5" y="193.5" width="5" height="5" />
          <text className="proof-lineage__id" x="191" y="200">
            G2
          </text>
          <text className="proof-lineage__operator" x="191" y="213">
            {g2.mutationOperator} · ν {g2.noveltyDistance}
          </text>
        </g>

        {/* Runner-up evidence travels to the receipt sidecar. */}
        <rect
          className="proof-lineage__token proof-lineage__token--evidence"
          x="-1.5"
          y="-1.5"
          width="3"
          height="3"
        />
        {/* Final receipt follows selected lineage back to G0. */}
        <rect
          className="proof-lineage__token proof-lineage__token--return"
          x="-1.75"
          y="-1.75"
          width="3.5"
          height="3.5"
        />
      </svg>
      <figcaption className="proof-lineage__caption">
        Recorded proof · {runStamp} · source {data.sourceSha256.slice(0, 8)}
      </figcaption>
    </figure>
  );
}
