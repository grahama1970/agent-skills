# Deck architecture — measured, 2026-08-13

Source: the five real decks in the style corpus (263 slides total). Numbers
produced by `scripts/measure_deck_architecture.py` reading the .pptx files
directly (python-pptx); archetype per slide is classified from measured
features (word count, picture count, large centred text, title text), the same
feature basis as `$best-practices-slide-design`.

| Deck | Slides | Opening | Closing | Dividers | Section lengths (median) |
|---|---|---|---|---|---|
| ACERT_Darpa_PI_Meeting_FtWorth | 80 | cover, divider, content, art-only | content, close, close | 15 | 6 |
| ReqML_GE_Presentation | 67 | cover, content, divider, content | divider, content, art-rich | 16 | 3 |
| SpartaAI_CyberSummitv_v3 | 59 | cover, toc, content, dense-reference | content, close, close | 9 | 6 |
| SpartaAI_SBIR | 48 | cover, content, toc, dense-reference | divider, close, close | 10 | 4 |
| Rack_Assurance_Ecosystem_RAES_v1 | 9 | cover, art-rich, art-rich, close | art-rich, dense-reference, art-rich | 1 | — |

## What the numbers say

1. **Cover is universal** (5/5, slide 1).
2. **TOC is optional and early**: present in the two SpartaAI decks at slide
   2-3; absent from ACERT/ReqML/RAES. A TOC is a choice, not a requirement.
3. **Close pages usually double**: `close, close` ends 3/5 decks. The mini
   deck (RAES, 9 slides) ends on art instead — short decks close warm without
   a dedicated pair.
4. **Sections are short**: median 3-6 slides between dividers; the longest
   observed run is 12.
5. **Dividers are frequent and often paired**: consecutive divider slides
   appear in 4/5 decks (ACERT 14-15, 21-22; ReqML 12-13; SBIR 32-33;
   CyberSummit 52-53) — a section title page followed by a framing page.
6. **Divider titles are short, often questions**: "ACERT Overview", "Why was
   ACERT created?", "How ACERT Works", "What's the point, again?", "SPARTA
   (Resource)", "SpartaAI".
7. **Real decks are LONG** (48-80) except the 9-slide mini. A 15-20 slide deck
   is a *short* deck by house standards and should carry proportionally fewer
   sections (3-5), not a compressed version of a 60-slide arc.

## Honest limits of this measurement

- Archetype classification here is heuristic (feature thresholds), not the
  hand-verified classification in DESIGN_SLIDES; treat counts as ±1 slide.
- "Section length" assumes dividers delimit sections. Decks that use a
  content page as a de-facto section opener are not captured.
- Five decks is a small corpus. Every law above is a tendency with its
  counterexample named, not an invariant.
