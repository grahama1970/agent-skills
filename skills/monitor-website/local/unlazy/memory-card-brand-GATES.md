# Gates: grahama.co memory card brand-palette re-render

OWNS: skills/create-svg/references/themes/grahama-ember-v1.yml docs/assets/project-cards/ site/public/projects/memory-recall-card.svg site/public/projects/thumbs/memory-recall-card.svg site/out/projects/

Scope: Re-render the memory intent-pipeline card in grahama.co's own palette via a create-svg theme, install it on every card surface, serve it on 127.0.0.1:3020, prove it visually, and commit narrowly.

- [ ] G1: named skill contracts were read before action
  CHECK: grep -q "Hard Budgets" skills/best-practices-svg-design/SKILL.md && grep -q "two stages, never one-shot" skills/create-svg/SKILL.md && echo SKILL_CONTRACT_READBACK_OK
  EXPECT: SKILL_CONTRACT_READBACK_OK
  EVIDENCE: pending

- [ ] G2: brand theme exists and derives from site tokens
  CHECK: grep -q "e2ac62" skills/create-svg/references/themes/grahama-ember-v1.yml && grep -q "e2ac62" site/app/globals.css && echo THEME_TOKENS_OK
  EXPECT: THEME_TOKENS_OK
  EVIDENCE: pending

- [ ] G3: rendered card passes create-svg verify with receipt
  CHECK: skills/create-svg/run.sh verify docs/assets/project-cards/memory-recall-card.scene.yml docs/assets/project-cards/memory-recall-card.svg --receipt docs/assets/project-cards/memory-recall-card.receipt.json >/dev/null && python3 -c "import json;r=json.load(open('docs/assets/project-cards/memory-recall-card.receipt.json'));print('RECEIPT_'+r['status'])"
  EXPECT: RECEIPT_PASS
  EVIDENCE: pending

- [ ] G4: identical artifact installed on all four card surfaces
  CHECK: python3 -c "import hashlib,sys;h={hashlib.sha256(open(p,'rb').read()).hexdigest() for p in ['docs/assets/project-cards/memory-recall-card.svg','site/public/projects/memory-recall-card.svg','site/public/projects/thumbs/memory-recall-card.svg','site/out/projects/memory-recall-card.svg','site/out/projects/thumbs/memory-recall-card.svg']};print('INSTALL_UNIFORM_OK' if len(h)==1 else 'INSTALL_DRIFT '+str(h))"
  EXPECT: INSTALL_UNIFORM_OK
  EVIDENCE: pending

- [ ] G5: live local server serves the same artifact
  CHECK: bash -c "curl -sf -m 5 http://127.0.0.1:3020/projects/memory-recall-card.svg | sha256sum | cut -d' ' -f1 > /tmp/served.sha && sha256sum site/public/projects/memory-recall-card.svg | cut -d' ' -f1 > /tmp/src.sha && cmp -s /tmp/served.sha /tmp/src.sha && echo SERVED_MATCH_OK"
  EXPECT: SERVED_MATCH_OK
  EVIDENCE: pending

- [ ] G6: fresh rendered screenshot of the card exists for visual inspection
  CHECK: bash -c "test -s /tmp/claude-1000/-home-graham-workspace-experiments-agent-skills/5e6a6422-febb-4d0d-9b66-2199157e6396/scratchpad/brand-card-full.png && test -s /tmp/claude-1000/-home-graham-workspace-experiments-agent-skills/5e6a6422-febb-4d0d-9b66-2199157e6396/scratchpad/brand-card-400.png && echo SCREENSHOTS_EXIST_OK"
  EXPECT: SCREENSHOTS_EXIST_OK
  EVIDENCE: pending

- [ ] G7: retained agentic eval for the governing skill is READY
  CHECK: python3 -c "import json;r=json.load(open('skills/best-practices-svg-design/fixtures/agentic_eval.latest-result.json'));print('EVAL_'+r['readiness'])"
  EXPECT: EVAL_READY
  EVIDENCE: pending

- [ ] G8: narrow commit retained locally
  CHECK: bash -c "git log -1 --name-only --pretty=format:%s | grep -q 'grahama-ember' && echo COMMIT_RETAINED_OK"
  EXPECT: COMMIT_RETAINED_OK
  EVIDENCE: pending

- [ ] G9: MANUAL - human accepts the brand-palette design (create-svg Stage-2 gate)
  Human review of the rendered card at full and 400px sizes. Until Graham
  approves, final status is Immutable Goal: NOT_MET (design acceptance
  outstanding). Push to origin/main is out of scope per HANDOFF.md (divergent
  branch, ahead/behind).
  EVIDENCE: pending
