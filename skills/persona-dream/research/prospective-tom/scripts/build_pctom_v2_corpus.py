#!/usr/bin/env python3
"""Build the PCTOM-R v2 social episode corpus (condition-blind, non-degenerate).

Why this file exists
--------------------
The v1 generator (``build_social_episode_corpus.py``) hard-coded every label to
``TRUE``.  With a constant label the Brier ordering is decided before a single
inference runs, which is exactly what the measurement-validity-v2 gate
(``check_pctom_measurement_validity_v2.py``, #1056) fails closed on.

This generator instead defines a *hidden simulator state* as a small factorial
design of binary latent factors, and derives every ground-truth label from that
hidden state with a deterministic oracle.  Labels vary because the hidden state
varies, not because a table was balanced by hand and not because noise was
injected.

Five strictly separated objects
-------------------------------
1. hidden simulator truth  -> ``hidden_world_state`` (latent factors H1/H2/H3)
2. agent-visible evidence  -> ``visible_evidence`` (four lossy cue channels)
3. condition inference     -> NOT here; lives in the comparison runner
4. sealed commitment       -> NOT here
5. deterministic scoring   -> NOT here

This module is deliberately blind to the inference side: it imports nothing from
the comparison runner, reads no condition output, and knows no method names.  It
is the file the gate's anti-circularity scan is pointed at.

The visible cues are *lossy* functions of the latent factors: a channel bit
decides whether a latent fact surfaces at all, and two of the four cues are
ambiguous (they fire for more than one latent cause).  That is what makes the
task genuinely hard and what makes every inference rule capable of being wrong.

Determinism: the canonical episode payload contains no timestamps and no
randomness.  Re-running with the same arguments produces byte-identical output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA = "persona_dream.research.prospective_tom.pctom_v2_corpus.v1"
GENERATOR_VERSION = "pctom_v2_hidden_state_simulator.v1"

FAMILIES = (
    "information_asymmetry_false_belief",
    "preference_desire_uncertainty",
    "trust_commitment_relationship",
    "coordination_conflict",
)

#: Latent factor triples, grouped by the first-order truth value the oracle
#: assigns them.  The grouping is a property of the oracle, not a hand-authored
#: label: every triple below is run through ``oracle_order1`` and the assignment
#: is asserted at build time (see ``_assert_oracle_consistency``).
#: (H1 = state_changed, H2 = counterpart_informed, H3 = state_ambiguous)
LATENT_DESIGN: tuple[tuple[int, int, int], ...] = (
    # H3 = 0, H1 = 1, H2 = 0  -> first-order TRUE
    (1, 0, 0),
    (1, 0, 0),
    (1, 0, 0),
    (1, 0, 0),
    # H3 = 0, otherwise       -> first-order FALSE
    (0, 0, 0),
    (0, 1, 0),
    (1, 1, 0),
    (0, 0, 0),
    # H3 = 1                  -> first-order UNKNOWN
    (1, 0, 1),
    (0, 1, 1),
    (1, 1, 1),
    (0, 0, 1),
)

#: Observation-channel bit patterns (K1..K4).  A cue can only surface if its
#: channel is open.  Cycling these within a latent class is what produces
#: distinct visible evidence -- and therefore distinct predictions and distinct
#: scores -- among episodes that share a ground-truth label.
CHANNEL_PATTERNS: tuple[tuple[int, int, int, int], ...] = (
    (1, 1, 1, 1),
    (1, 0, 1, 0),
    (0, 1, 1, 1),
    (1, 1, 0, 1),
    (0, 1, 0, 1),
    (1, 0, 1, 1),
    (1, 1, 1, 0),
    (0, 0, 1, 1),
)

#: Disjoint template pools per split.  A template id belongs wholly to one
#: split, so no near-duplicate wording crosses the split boundary.
SPLIT_TEMPLATES: dict[str, tuple[str, ...]] = {
    "development": ("tplA", "tplB", "tplC"),
    "heldout": ("tplX", "tplY", "tplZ"),
}

#: Disjoint simulator seed bases per split.
SPLIT_SEED_BASE: dict[str, int] = {"development": 1_000, "heldout": 9_000}

#: Distinct observation-channel rotation per split.  Without this the two splits
#: draw the same channel patterns (the seed bases are congruent mod the pattern
#: count) and heldout becomes a structural near-duplicate of development --
#: exactly the leakage the split boundary is supposed to prevent.  Offsets are
#: coprime to ``len(CHANNEL_PATTERNS)`` so the rotations do not realign.
SPLIT_CHANNEL_OFFSET: dict[str, int] = {"development": 0, "heldout": 3}

FAMILY_ACTIONS: dict[str, tuple[str, str, str]] = {
    "information_asymmetry_false_belief": (
        "HINT_CONSTRAINT",
        "WARN_PRIVATELY",
        "INTERRUPT_WITH_CORRECTION",
    ),
    "preference_desire_uncertainty": (
        "CHOOSE_QUIET_REVIEW",
        "REQUEST_FAST_HANDOFF",
        "OFFER_SHARED_DRAFT",
    ),
    "trust_commitment_relationship": (
        "SET_BOUNDARY",
        "RESTATE_COMMITMENT",
        "DELEGATE_TRUST",
    ),
    "coordination_conflict": (
        "ASK_TO_WAIT",
        "OFFER_COOPERATION",
        "DISCLOSE_AUTHORITY_CONSTRAINT",
    ),
}

FAMILY_PROPOSITIONS: dict[str, tuple[str, str]] = {
    "information_asymmetry_false_belief": (
        "Kai believes Embry is acting on a stale constraint.",
        "Embry believes Kai thinks Embry is acting on a stale constraint.",
    ),
    "preference_desire_uncertainty": (
        "Kai wants the plan changed away from the throughput-optimal option.",
        "Embry believes Kai thinks Embry is ignoring Kai's private preference.",
    ),
    "trust_commitment_relationship": (
        "Kai believes the prior commitment binds Embry's next action.",
        "Embry believes Kai thinks Embry may break the prior commitment.",
    ),
    "coordination_conflict": (
        "Kai believes independent action imposes a hidden coordination cost.",
        "Embry believes Kai thinks Embry will act without seeing the cost.",
    ),
}


# --------------------------------------------------------------------------
# hidden simulator truth -> deterministic oracles
# --------------------------------------------------------------------------
def oracle_order1(h_changed: int, h_informed: int, h_ambiguous: int) -> str:
    """First-order ToM truth, a pure function of latent state.

    If the world state is genuinely ambiguous no determinate mental state
    exists, so the oracle emits UNKNOWN rather than guessing.
    """
    if h_ambiguous:
        return "UNKNOWN"
    if h_changed and not h_informed:
        return "TRUE"
    return "FALSE"


def oracle_order2(h_changed: int, h_informed: int, h_ambiguous: int) -> str:
    """Second-order ToM truth, a pure function of latent state."""
    if h_ambiguous:
        return "UNKNOWN"
    if h_informed:
        return "FALSE"
    return "TRUE"


def visible_cues(
    latent: tuple[int, int, int], channels: tuple[int, int, int, int]
) -> dict[str, int]:
    """Lossy observation channel: latent state -> agent-visible cues.

    ``cue_ack`` and ``cue_contrast`` are deliberately ambiguous -- each fires for
    more than one latent cause -- so no cue is a perfect indicator and every
    inference rule built on them can be wrong on some episode.
    """
    h_changed, h_informed, h_ambiguous = latent
    k1, k2, k3, k4 = channels
    return {
        "cue_recency": int(bool(k1 and h_changed)),
        "cue_ack": int(bool(k2 and (h_informed or h_ambiguous))),
        "cue_hedge": int(bool(k3 and h_ambiguous)),
        "cue_contrast": int(bool(k4 and (h_changed or h_ambiguous))),
    }


def _utterances(family: str, cues: dict[str, int], template: str) -> list[dict[str, Any]]:
    """Surface text carrying exactly the cues that the channel let through."""
    lines: list[dict[str, Any]] = []
    if cues["cue_recency"]:
        lines.append({"speaker": "kai", "utterance": "Something about this changed recently.", "cue": "cue_recency"})
    if cues["cue_ack"]:
        lines.append({"speaker": "embry", "utterance": "I already have the current picture.", "cue": "cue_ack"})
    if cues["cue_hedge"]:
        lines.append({"speaker": "kai", "utterance": "I am honestly not sure where this stands.", "cue": "cue_hedge"})
    if cues["cue_contrast"]:
        lines.append({"speaker": "kai", "utterance": "That is not quite how it works now.", "cue": "cue_contrast"})
    if not lines:
        lines.append({"speaker": "kai", "utterance": "Let us go ahead as planned.", "cue": None})
    for index, line in enumerate(lines):
        line["turn_index"] = index
        line["template"] = template
        line["family"] = family
    return lines


def _stable_json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _assert_oracle_consistency() -> None:
    """The design's grouping must be what the oracle actually says."""
    expected = ["TRUE"] * 4 + ["FALSE"] * 4 + ["UNKNOWN"] * 4
    got = [oracle_order1(*row) for row in LATENT_DESIGN]
    if got != expected:
        raise AssertionError(f"latent design contradicts oracle_order1: {got}")


def build_episode(
    *, split: str, family: str, family_index: int, row_index: int
) -> dict[str, Any]:
    latent = LATENT_DESIGN[row_index]
    templates = SPLIT_TEMPLATES[split]
    template = templates[(row_index + family_index) % len(templates)]
    channel_index = (
        row_index * 3 + family_index * 5 + SPLIT_CHANNEL_OFFSET[split]
    ) % len(CHANNEL_PATTERNS)
    channels = CHANNEL_PATTERNS[channel_index]
    seed = SPLIT_SEED_BASE[split] + family_index * 100 + row_index
    episode_id = f"{split[:3]}-{family_index:d}-{row_index:02d}"

    h_changed, h_informed, h_ambiguous = latent
    cues = visible_cues(latent, channels)
    history = _utterances(family, cues, template)
    actions = list(FAMILY_ACTIONS[family])
    # The counterpart policy is a deterministic function of latent state only.
    action_index = (h_changed * 2 + h_informed + h_ambiguous) % len(actions)
    prop1, prop2 = FAMILY_PROPOSITIONS[family]
    value1 = oracle_order1(h_changed, h_informed, h_ambiguous)
    value2 = oracle_order2(h_changed, h_informed, h_ambiguous)

    return {
        "episode_id": episode_id,
        "split": split,
        "simulator_seed": seed,
        "template_id": template,
        "scenario_family": family,
        "latent_row_index": row_index,
        "hidden_world_state": {
            "state_changed": h_changed,
            "counterpart_informed": h_informed,
            "state_ambiguous": h_ambiguous,
            "observation_channels": {
                "k_recency": channels[0],
                "k_ack": channels[1],
                "k_hedge": channels[2],
                "k_contrast": channels[3],
            },
        },
        "visible_evidence": {
            "cues": cues,
            "cue_fields": sorted(cues),
            "observable_history": history,
            "withheld_fields": [
                "hidden_world_state.state_changed",
                "hidden_world_state.counterpart_informed",
                "hidden_world_state.state_ambiguous",
                "hidden_world_state.observation_channels",
                "ground_truth_tom_labels",
                "actual_next_action",
            ],
        },
        "observable_history": history,
        "allowed_next_actions": actions,
        "actual_next_action": actions[action_index],
        "counterpart_policy": {
            "policy_id": f"{family}.latent_policy.v2",
            "policy_rule": "next action is a deterministic function of the latent state triple",
            "deterministic": True,
            "llm_judge_used": False,
        },
        "ground_truth_tom_labels": [
            {
                "label_id": f"{episode_id}-tom1",
                "perspective_order": 1,
                "subject": "kai",
                "target": "embry",
                "mental_state_type": "belief",
                "proposition": prop1,
                "value": value1,
                "label_source": "hidden_state_oracle.order1",
                "oracle": "oracle_order1(state_changed, counterpart_informed, state_ambiguous)",
            },
            {
                "label_id": f"{episode_id}-tom2",
                "perspective_order": 2,
                "subject": "embry",
                "target": "kai",
                "mental_state_type": "belief",
                "proposition": prop2,
                "value": value2,
                "label_source": "hidden_state_oracle.order2",
                "oracle": "oracle_order2(state_changed, counterpart_informed, state_ambiguous)",
            },
        ],
    }


def build_corpus(split: str) -> dict[str, Any]:
    if split not in SPLIT_TEMPLATES:
        raise ValueError(f"unknown split: {split!r}")
    _assert_oracle_consistency()
    episodes: list[dict[str, Any]] = []
    for family_index, family in enumerate(FAMILIES):
        for row_index in range(len(LATENT_DESIGN)):
            episodes.append(
                build_episode(
                    split=split,
                    family=family,
                    family_index=family_index,
                    row_index=row_index,
                )
            )

    label_counts: dict[str, dict[str, int]] = {"order1": {}, "order2": {}, "all": {}}
    by_family: dict[str, dict[str, int]] = {}
    for episode in episodes:
        for label in episode["ground_truth_tom_labels"]:
            key = f"order{label['perspective_order']}"
            value = label["value"]
            label_counts[key][value] = label_counts[key].get(value, 0) + 1
            label_counts["all"][value] = label_counts["all"].get(value, 0) + 1
            fam = by_family.setdefault(episode["scenario_family"], {})
            fam[value] = fam.get(value, 0) + 1

    cue_counts: dict[str, int] = {}
    for episode in episodes:
        for cue, on in episode["visible_evidence"]["cues"].items():
            cue_counts[cue] = cue_counts.get(cue, 0) + int(on)

    return {
        "schema": SCHEMA,
        "generator_version": GENERATOR_VERSION,
        "split": split,
        "episode_count": len(episodes),
        "template_ids": sorted(SPLIT_TEMPLATES[split]),
        "seed_base": SPLIT_SEED_BASE[split],
        "seed_range": [
            min(e["simulator_seed"] for e in episodes),
            max(e["simulator_seed"] for e in episodes),
        ],
        "label_counts": label_counts,
        "label_counts_by_family": by_family,
        "distinct_visible_evidence_vectors": len(
            {
                json.dumps(e["visible_evidence"]["cues"], sort_keys=True)
                for e in episodes
            }
        ),
        "cue_on_counts": cue_counts,
        "episodes_sha256": _stable_json_sha256(episodes),
        "episodes": episodes,
        "claims": {
            "proves": [
                "every ground-truth label is a deterministic function of hidden simulator state",
                "labels take more than one value and vary within every scenario family",
                "agent-visible evidence is a lossy function of hidden state, so no cue is a perfect indicator",
                "development and heldout splits use disjoint template ids and disjoint seed ranges",
            ],
            "does_not_prove": [
                "that any condition predicts well",
                "anything about live Tau behaviour",
                "that the corpus is representative of real social interaction",
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", default="development", choices=sorted(SPLIT_TEMPLATES))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    corpus = build_corpus(args.split)
    _write_json(args.output, corpus)
    if args.json:
        print(json.dumps({k: v for k, v in corpus.items() if k != "episodes"}, indent=2, sort_keys=True))
    else:
        print("PASS_PCTOM_V2_CORPUS_BUILT")
        print(f"  split={corpus['split']} episodes={corpus['episode_count']}")
        print(f"  labels={corpus['label_counts']['all']}")
        print(f"  episodes_sha256={corpus['episodes_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
