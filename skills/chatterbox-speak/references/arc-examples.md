# Conversation-arc examples — working vs non-working

Each example starts from **the request**, shows the **sourced inputs**, the
**working arc** (real `conversation_arc.py plan` output), and the **non-working**
variant a naive agent might produce with *why it's wrong* (each cites a rule the
banks/SKILL already enforce). Use this to check your composition against reality.

See `conversation-arc.md` for the recipe and `arc_scenarios.py chart --id <id>`
to render any of these graphically.

---

## Example 1 — simple: "Morning, Embry."

**Sourced inputs:** latency 1500ms (`/execution-stats` — greetings are cheap),
emotion `happy`, intensity 3, complexity 1.

**Working arc** (`answer` arc, low band):
```
    0ms fused_hmm     fused-low-10   "Hmm, let me look at that."   <- opener
 2240ms progress      progress:answer
 3640ms answer_phase  arc:answer:careful_concerned
 ...   answer_phase   calm_precise / memory_confident / playful_light
```

**Non-working, and why:**
- ❌ Putting a **hum bed** under a 1.5s greeting. Hums fill waits **>7s**
  (latency budget); a hum under a trivial turn is filler theater.
- ❌ Routing to **high band / v3 whole-sentence** for "Morning." High band is for
  intensity ≥8 or complexity ≥3; a greeting is low band (SKILL emotion table).
- ⚠️ **Known open item:** even the working arc over-covers here (~10.8s for a
  greeting) because the answer arc always runs full phases. This is the tuning
  question the audible pass exists to answer — a simple turn likely needs a
  trimmed arc (opener + one answer phase), not four phases. Flag, don't fake.

---

## Example 2 — medium: "I'm worried we'll miss the deadline."

**Sourced inputs:** latency 10000ms, emotion `fear` (from `/intent`
`delivery_context`), intensity 6, complexity 2.

**Working arc** (`reassure` arc, medium band — gaps <7s so pauses, no hum):
```
    0ms fused_hmm     fused-hi-01
 2320ms progress      progress:intent
 3720ms pause         pause:beat
 4320ms progress      progress:recall     (recall -> searching, each + pause)
 ...
 9720ms answer_phase  arc:reassure:careful_concerned -> neutral_warm -> relieved
```

**Non-working, and why:**
- ❌ Routing worry/fear to the **`answer`** arc ending in `playful_light`.
  Distress/fear/grief must route to **`reassure`** (SKILL: quiet support is the
  fallback; positive-peak delivery is preference-gated, never forced).
- ❌ Opening with a **joke** to lighten the mood. Sarcasm/humor gate to BENIGN
  `/deflect` only; never on genuine distress (mockery escalates).
- ⚠️ The `fused-hi-01` opener on a *medium* turn is a **fallback**: the fused-hmm
  bank has only `low`/`high` bands, so medium borrows. Acceptable, but a
  dedicated medium opener would be truer.

---

## Example 3 — complex + emotional: "I keep thinking about Kai… anyway, what does SC-7 require?"

**Sourced inputs:** latency 28000ms (3-control-class solve), emotion `grief`,
intensity 4, complexity 3.

**Working arc** (`reassure` arc, high band — long gaps get memory-linked hum beds):
```
    0ms fused_hmm     fused-hi-04    "Hmmmm... [sighs] let me dig into that."
 3520ms progress      progress:intent
 4920ms hum           hum:st-louis-blues   (>7s gap -> bone-dry bed, -3dB, memory_links -> Kai/surf)
16920ms progress      progress:recall
18320ms hum           hum:st-louis-blues
27400ms progress      progress:searching
28800ms pause         pause:beat
29400ms progress      progress:answer
30800ms answer_phase  arc:reassure:careful_concerned -> neutral_warm -> relieved
```

**Non-working, and why (all are documented rejected patterns):**
- ❌ **Plural tag on Turbo** (`[sighs]`) on a progress line — Turbo speaks the
  literal word "sighs". Plurals are v3-clone only; the fused opener above uses
  the clone, progress lines stay plain.
- ❌ An **isolated "hmm" clip** as the opener — rejected in every synthesized
  form; fuse the hmmmm into a whole clone line (as `fused-hi-04` does).
- ❌ A **reverby / vintage** hum bed — hums must be bone-dry, no era cues,
  loudness-normalized (`hum_render.py`).
- ❌ Writing the plan's render text (with `[sighs]`) into **`$memory`** canonical
  text — renderer tags corrupt memory; tags live only on the render line.
- ❌ **Splicing a sob mid-clause** or mixing a loud sob under flat Turbo speech —
  whole sentences only; insert emotion must not exceed the speaking voice.
