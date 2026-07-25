# Path B — proof (arc_state -> spoken line), corrected

2026-07-25. Goal G2: make the persona's ACCUMULATED self audible in the voice.

## Verified in-code result (supersedes the earlier browser-mediated note)

Running the real entrypoint through the sanctioned /tau text-reasoning path (zero
direct scillm):

  dream_voice_weights.py --dream-key dream_dream_successor_943b01ecd9a3 --arc-voice

produces, from Embry's real arc_state:
- fallback_used: FALSE
- line: "If you're available, Kai, I'd prefer your assessment before I proceed."
- why: professional distance carrying a guarded request to be witnessed

Hash-bound receipt committed alongside this file:
`project_state_review/r1/arc_voice_profile.receipt.json` (the
dream_voice_weight_profile.v1.json with arc_voice.provenance.fallback_used:false).

## History (do not mislead)

The first attempts fell back (fallback_used:true, "adapter returned no
spoken_line"). Root cause was a CONTRACT MISMATCH in our prompt — it asked the
model to speak a bare line while the output_contract demanded JSON, so scillm
returned a 502 json_validation_error. It was NOT a /tau or scillm outage (/tau
verified healthy, 200/PASS). Fixing the prompt to return the JSON the contract
expects made the in-code run succeed with fallback_used:false (above). An earlier
version of this file described a browser-mediated line produced before the fix;
that is superseded by the in-code receipt.

## Still open (per the 3-seat project-state review)

- --arc-voice is now wired into the default cycle render
  (autonomous_dream_cycle.py step 8); a full-cycle receipt showing
  fallback_used:false + a rendered WAV sha is the next artifact to commit.
- Audio-level evolution (fixed-probe: same sentence epoch-0 vs epoch-N, shuffled-
  delta control, ablation, blind ABX) is NOT yet demonstrated.
