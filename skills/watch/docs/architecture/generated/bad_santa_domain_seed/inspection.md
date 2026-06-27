# Bad Santa Domain Seed Inspection

Status: ACCEPTED_AS_DOMAIN_PRIOR_ONLY
Created: 2026-06-27

## Artifact

`brave_bad_santa_cast_search.json`

## Command

```bash
python3 skills/brave-search/brave_search.py web \
  "Bad Santa 2003 cast Tony Cox Marcus Billy Bob Thornton Willie" \
  --count 5 \
  > skills/watch/docs/architecture/generated/bad_santa_domain_seed/brave_bad_santa_cast_search.json
```

## Result Summary

The raw Brave Search response returned five results:

1. IMDb full cast and crew
2. Wikipedia page for *Bad Santa*
3. IMDb title page
4. Netflix title page
5. TMDB cast page

## What This Proves

- A bounded web/domain search artifact exists for the Bad Santa movie-domain
  canary.
- The artifact is suitable for seeding movie-domain candidate records such as
  `Billy Bob Thornton -> Willie` and `Tony Cox -> Marcus`.
- The artifact can be cited by `movie_domain_entities` as domain corroboration.

## What This Does Not Prove

- It does not prove any character appears in any specific Watch segment.
- It does not prove a VLM label is correct.
- It does not prove a tracker identity assignment is correct.
- It does not replace frame, clip, transcript, tracker, or human-review
  evidence.

## Source Truth Boundary

Brave Search output is a domain prior only. If Watch cannot support a segment
claim with extracted video evidence, the correct result is `INCONCLUSIVE` or
`COVERAGE_GAP`, not a verified answer.
