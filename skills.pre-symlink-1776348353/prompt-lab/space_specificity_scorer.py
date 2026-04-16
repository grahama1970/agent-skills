"""
Space-Specificity Scorer for SPARTA QRAs.

Goes beyond keyword counting to measure whether QRA answers contain
genuine space-domain reasoning vs generic IT with space terms appended.

Scoring levels:
  0 = Generic IT (no space terms)
  1 = Space-washed (space terms appended to generic reasoning)
  2 = Space-contextualized (space terms integrated into reasoning)
  3 = Space-specific (reasoning depends on space-domain properties)
"""
import json
import re
import sys
from pathlib import Path
from typing import List, Dict, Any, Tuple


# Space-specific terms (presence required but not sufficient)
SPACE_TERMS = {
    'satellite', 'spacecraft', 'payload', 'ground station', 'mission control',
    'rf', 'satcom', 'uplink', 'downlink', 'telemetry', 'tracking', 'tt&c',
    'jamming', 'spoofing', 'asat', 'ccsds', 'spacewire',
    'leo', 'meo', 'geo', 'orbit', 'constellation',
    'ground segment', 'link segment', 'space segment',
    'mission operations', 'flight software', 'star tracker',
    'reaction wheel', 'solar array', 'transponder', 'antenna',
    'radiation-hardened', 'space vehicle', 'crosslink',
}

# Space-specific MECHANISMS that indicate genuine domain knowledge
# These are concepts unique to space that don't exist in terrestrial IT
SPACE_MECHANISMS = {
    # Tier 3: Uniquely space (no terrestrial equivalent)
    'contact window': 3,
    'orbital period': 3,
    'communication blackout': 3,
    'radiation hardened': 3,
    'orbital debris': 3,
    'solar event': 3,
    'single event upset': 3,
    'deorbiting': 3,
    'thermal cycling': 3,
    'orbital mechanics': 3,
    'orbital maneuver': 3,
    'orbital slot': 3,
    'launch window': 3,
    'space weather': 3,
    'radiation effect': 3,

    # Tier 2: Space-specific operations & interfaces
    'autonomous operation': 2,
    'uplink command': 2,
    'downlink telemetry': 2,
    'inter-satellite link': 2,
    'ground-to-space': 2,
    'space-to-ground': 2,
    'command authentication': 2,
    'onboard processing': 2,
    'constellation management': 2,
    'safe mode': 2,
    'frequency hopping': 2,
    'power budget': 2,
    'attitude control': 2,
    'attitude determination': 2,
    'onboard computer': 2,
    'onboard memory': 2,
    'onboard storage': 2,
    'onboard software': 2,
    'spacecraft bus': 2,
    'spacecraft subsystem': 2,
    'spacecraft anomaly': 2,
    'antenna pointing': 2,
    'antenna tracking': 2,
    'rf interference': 2,
    'rf spectrum': 2,
    'signal propagation': 2,
    'link budget': 2,
    'ground-to-spacecraft': 2,
    'spacecraft-to-ground': 2,
    'orbit determination': 2,

    # Tier 1: Space-domain operational concepts (compound phrases)
    'mission critical': 1,
    'telemetry processing': 1,
    'telemetry channel': 1,
    'telemetry routing': 1,
    'telemetry data': 1,
    'telemetry downlink': 1,
    'telemetry stream': 1,
    'command sequence': 1,
    'command processing': 1,
    'command validation': 1,
    'command channel': 1,
    'command injection': 1,
    'command execution': 1,
    'command uplink': 1,
    'payload command': 1,
    'payload processing': 1,
    'payload data': 1,
    'payload control': 1,
    'payload configuration': 1,
    'payload interface': 1,
    'payload processor': 1,
    'flight software update': 1,
    'flight software validation': 1,
    'flight software modification': 1,
    'flight software integrity': 1,
    'flight software patch': 1,
    'ground station network': 1,
    'ground station operator': 1,
    'ground station software': 1,
    'ground station interface': 1,
    'ground station authentication': 1,
    'mission operations center': 1,
    'mission data': 1,
    'mission planning': 1,
    'mission phase': 1,
    'mission timeline': 1,
    'rf link': 1,
    'rf signal': 1,
    'rf channel': 1,
    'rf band': 1,
    'constellation topology': 1,
    'constellation routing': 1,
    'constellation key': 1,
    'solar panel': 1,
    'solar array': 1,
    'solar power': 1,
    'orbit parameter': 1,
    'orbital position': 1,
    'orbital plane': 1,
    'spacecraft health': 1,
    'spacecraft state': 1,
    'spacecraft reboot': 1,
    'antenna beam': 1,
    'antenna pattern': 1,

    # Additional space-domain concepts (hardware, environment, operations)
    'write once memory': 2,
    'radiation tolerant': 2,
    'bit flip': 2,
    'air gapped': 1,
    'firmware uplink': 2,
    'uplinked to': 1,
    'command protocol': 1,
    'space packet': 2,
    'proximity 1': 2,
    'ccsds protocol': 2,
    'telemetry manager': 1,
    'command manager': 1,
    'memory protection unit': 2,
    'bootloader': 1,
    'eeprom': 2,
    'rad hard': 2,
    'rad tolerant': 2,
}

# Regex patterns for space-domain causal reasoning
# These indicate the answer explains WHY something is different in space
CAUSAL_SPACE_PATTERNS = [
    r'because .*(?:orbit|latency|rf|satellite|spacecraft|ground station|telemetry|radiation|propagation|bandwidth|autonomous)',
    r'due to .*(?:orbit|latency|rf|satellite|spacecraft|radiation|propagation|bandwidth|contact|signal)',
    r'since .*(?:spacecraft|satellite|contact|blackout|autonomous|orbit|latency)',
    r'unlike .*(?:terrestrial|traditional|conventional|ground-based|enterprise|commercial)',
    r'(?:cannot|can.t|unable to) .*(?:physically|reboot|patch|access|replace|visit|service)',
    r'limited (?:bandwidth|power|processing|contact|window|time|link|resource)',
    r'no (?:physical|direct) (?:access|connection|link)',
    r'(?:minutes?|hours?) of (?:latency|delay|propagation)',
    r'inability to (?:receive|send|patch|update|access|service)',
    r'(?:multi[ -]year|decade[ -]long) (?:lifespan|mission|operation)',
    r'~?\d+\s*m[s]?\s+(?:round[ -]trip|latency|delay|propagation)',
    r'(?:100\s*mhz|radiation[ -]induced|bit[ -]flip)',
    r'during (?:a |the )?(?:contact|communication|telemetry) (?:pass|window|session)',
]

# Patterns that indicate surface-level "space-washing"
BOILERPLATE_PATTERNS = [
    r'in space (?:systems|environments|operations|missions)',
    r'for (?:space|satellite|spacecraft) (?:systems|operations|missions)',
    r'in the (?:space|space cyber|aerospace) domain',
    r'(?:protects?|secures?) (?:space|satellite|spacecraft) (?:systems|operations)',
]


def _normalize(text: str) -> str:
    """Normalize text for matching: lowercase, dehyphenate compounds."""
    return text.lower().replace('-', ' ').replace('–', ' ')


def count_space_terms(text: str) -> int:
    """Count space-specific terms in text."""
    normalized = _normalize(text)
    return sum(1 for term in SPACE_TERMS if term in normalized)


def count_space_mechanisms(text: str) -> Tuple[int, List[str]]:
    """Count space-specific mechanisms and return which ones were found."""
    normalized = _normalize(text)
    found = []
    score = 0
    for mechanism, points in SPACE_MECHANISMS.items():
        if mechanism in normalized:
            found.append(mechanism)
            score += points
    return score, found


def count_boilerplate(text: str) -> int:
    """Count surface-level space-washing patterns."""
    normalized = _normalize(text)
    return sum(1 for pattern in BOILERPLATE_PATTERNS if re.search(pattern, normalized))


def count_causal_reasoning(text: str) -> int:
    """Count causal reasoning patterns that connect space constraints to security."""
    normalized = _normalize(text)
    return sum(1 for pattern in CAUSAL_SPACE_PATTERNS if re.search(pattern, normalized))


def score_answer(answer: str) -> Dict[str, Any]:
    """Score a single QRA answer for space-specificity.

    Returns dict with:
        level: 0-3 (generic → space-specific)
        space_terms: count of space terms
        mechanism_score: weighted score of space mechanisms found
        mechanisms: list of mechanisms found
        boilerplate: count of space-washing patterns
        causal_reasoning: count of causal space reasoning patterns
        details: human-readable assessment
    """
    space_terms = count_space_terms(answer)
    mechanism_score, mechanisms = count_space_mechanisms(answer)
    boilerplate = count_boilerplate(answer)
    causal = count_causal_reasoning(answer)

    # Causal reasoning about space constraints boosts mechanism score
    # (explains WHY space is different, even without specific mechanism keywords)
    effective_score = mechanism_score + causal * 2

    # Determine level
    if space_terms == 0:
        level = 0
        details = "Generic IT: No space-specific terms"
    elif effective_score == 0 and boilerplate > 0:
        level = 1
        details = f"Space-washed: {space_terms} space terms but {boilerplate} boilerplate patterns, no mechanisms"
    elif effective_score == 0:
        level = 1
        details = f"Thin space context: {space_terms} space terms but no space-specific mechanisms"
    elif effective_score <= 2:
        level = 2
        details = f"Space-contextualized: {space_terms} terms, mechanisms: {mechanisms}" + (f", causal: {causal}" if causal else "")
    else:
        level = 3
        details = f"Space-specific: {space_terms} terms, mechanisms ({mechanism_score}pts): {mechanisms}" + (f", causal reasoning: {causal}" if causal else "")

    return {
        'level': level,
        'space_terms': space_terms,
        'mechanism_score': mechanism_score,
        'effective_score': effective_score,
        'mechanisms': mechanisms,
        'boilerplate': boilerplate,
        'causal_reasoning': causal,
        'details': details,
    }


def score_qra_batch(qras: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Score a batch of QRAs and return aggregate statistics."""
    results = []
    level_counts = {0: 0, 1: 0, 2: 0, 3: 0}

    for qra in qras:
        answer = qra.get('answer', '')
        result = score_answer(answer)
        result['qra_id'] = qra.get('qra_id', qra.get('id', 'unknown'))
        results.append(result)
        level_counts[result['level']] += 1

    total = len(results) if results else 1
    return {
        'total_qras': len(results),
        'level_distribution': {
            'generic_it': {'count': level_counts[0], 'pct': level_counts[0] / total * 100},
            'space_washed': {'count': level_counts[1], 'pct': level_counts[1] / total * 100},
            'space_contextualized': {'count': level_counts[2], 'pct': level_counts[2] / total * 100},
            'space_specific': {'count': level_counts[3], 'pct': level_counts[3] / total * 100},
        },
        'brandon_grade': _compute_brandon_grade(level_counts, total),
        'avg_mechanism_score': sum(r['mechanism_score'] for r in results) / total if results else 0,
        'per_qra': results,
    }


def _compute_brandon_grade(level_counts: Dict[int, int], total: int) -> str:
    """Map space-specificity distribution to Brandon's grading scale.

    A+: <10% generic/washed, >50% space-specific
    A:  <20% generic/washed, >40% space-specific
    B:  <30% generic/washed
    C:  <50% generic/washed
    D:  <70% generic/washed
    F:  >=70% generic/washed
    """
    weak_pct = (level_counts[0] + level_counts[1]) / total * 100
    specific_pct = level_counts[3] / total * 100

    if weak_pct < 10 and specific_pct > 50:
        return 'A+'
    elif weak_pct < 20 and specific_pct > 40:
        return 'A'
    elif weak_pct < 30:
        return 'B'
    elif weak_pct < 50:
        return 'C'
    elif weak_pct < 70:
        return 'D'
    else:
        return 'F'


def score_from_db(db_path: str, sample_size: int = 500) -> Dict[str, Any]:
    """Score QRAs directly from a DuckDB database."""
    import duckdb
    conn = duckdb.connect(db_path, read_only=True)
    rows = conn.execute(f'''
        SELECT qra_id, question, answer, grounding_score, confidence
        FROM qra
        ORDER BY RANDOM()
        LIMIT {sample_size}
    ''').fetchall()
    conn.close()

    qras = [
        {'qra_id': r[0], 'question': r[1], 'answer': r[2], 'grounding_score': r[3], 'confidence': r[4]}
        for r in rows
    ]
    return score_qra_batch(qras)


if __name__ == '__main__':
    from typing import Optional as Opt
    import typer

    app = typer.Typer()

    @app.command()
    def main(
        db: Opt[str] = typer.Option(None, "--db", help="DuckDB path to score"),
        jsonl: Opt[str] = typer.Option(None, "--jsonl", help="JSONL file with QRA items to score"),
        sample: int = typer.Option(500, "--sample", help="Sample size for DB scoring"),
        output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    ):
        if db:
            result = score_from_db(db, sample)
        elif jsonl:
            qras = []
            with open(jsonl) as f:
                for line in f:
                    qras.append(json.loads(line))
            result = score_qra_batch(qras)
        else:
            typer.echo("Must provide --db or --jsonl")
            raise typer.Exit(1)

        if output_json:
            compact = {k: v for k, v in result.items() if k != 'per_qra'}
            print(json.dumps(compact, indent=2))
        else:
            print(f"\n{'='*60}")
            print(f"SPACE-SPECIFICITY ASSESSMENT ({result['total_qras']} QRAs)")
            print(f"{'='*60}")
            dist = result['level_distribution']
            print(f"  Generic IT (L0):       {dist['generic_it']['count']:>5} ({dist['generic_it']['pct']:.1f}%)")
            print(f"  Space-washed (L1):     {dist['space_washed']['count']:>5} ({dist['space_washed']['pct']:.1f}%)")
            print(f"  Contextualized (L2):   {dist['space_contextualized']['count']:>5} ({dist['space_contextualized']['pct']:.1f}%)")
            print(f"  Space-specific (L3):   {dist['space_specific']['count']:>5} ({dist['space_specific']['pct']:.1f}%)")
            print(f"  Avg mechanism score:   {result['avg_mechanism_score']:.1f}")
            print(f"  Brandon Grade:         {result['brandon_grade']}")
            print(f"{'='*60}")

            for level in [0, 1, 3]:
                examples = [r for r in result['per_qra'] if r['level'] == level][:2]
                if examples:
                    level_names = {0: 'GENERIC IT', 1: 'SPACE-WASHED', 3: 'SPACE-SPECIFIC'}
                    print(f"\n--- Example {level_names.get(level, f'L{level}')} ---")
                    for ex in examples:
                        print(f"  QRA {ex['qra_id']}: {ex['details']}")

    app()
