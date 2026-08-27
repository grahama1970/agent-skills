# Gates: grahama.co memory card brand-palette re-render

OWNS: skills/create-svg/references/themes/grahama-ember-v1.yml docs/assets/project-cards/ site/public/projects/memory-recall-card.svg site/public/projects/thumbs/memory-recall-card.svg site/out/projects/

Scope: Re-render the memory intent-pipeline card in grahama.co's own palette via a create-svg theme, install it on every card surface, serve it on 127.0.0.1:3020, prove it visually, and commit narrowly.

- [x] G1: named skill contracts were read before action
  CHECK: bash -c "cd /home/graham/workspace/experiments/agent-skills && grep -q 'Hard Budgets' skills/best-practices-svg-design/SKILL.md && grep -q 'two stages, never one-shot' skills/create-svg/SKILL.md && echo SKILL_CONTRACT_READBACK_OK"
  EXPECT: SKILL_CONTRACT_READBACK_OK
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/home/graham/workspace/experiments/agent-skills/skills/monitor-website/local/unlazy; path=7c36c0ef0b5d/27 entries; EXPECT=matched; output-sha256=f3c6b1b1bf9e65864724913dd42c28e326bbcd3d04de384f648511c490e6f310; output-bytes=27

- [x] G2: brand theme exists and derives from site tokens
  CHECK: bash -c "cd /home/graham/workspace/experiments/agent-skills && grep -q e2ac62 skills/create-svg/references/themes/grahama-ember-v1.yml && grep -q e2ac62 site/app/globals.css && echo THEME_TOKENS_OK"
  EXPECT: THEME_TOKENS_OK
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/home/graham/workspace/experiments/agent-skills/skills/monitor-website/local/unlazy; path=7c36c0ef0b5d/27 entries; EXPECT=matched; output-sha256=5a7f1a7b6eabd1345fd6eaaae3dc4bbcaa42cfe672ddac13a9be95f4e603993b; output-bytes=16

- [x] G3: adopted webgpt-v2 card passes create-svg validate (hand-authored, no scene)
  CHECK: bash -c "cd /home/graham/workspace/experiments/agent-skills && test \"$(skills/create-svg/run.sh validate docs/assets/project-cards/memory-recall-card.svg 2>/dev/null | tail -1)\" = PASS && echo VALIDATE_PASS_OK"
  EXPECT: VALIDATE_PASS_OK
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/home/graham/workspace/experiments/agent-skills/skills/monitor-website/local/unlazy; path=7c36c0ef0b5d/27 entries; EXPECT=matched; output-sha256=c26de83abdc9496cd1301470918ec39ecca1cf389ef0ae1c6504da1800d1c431; output-bytes=5

- [x] G4: identical artifact installed on all four card surfaces
  CHECK: bash -c "cd /home/graham/workspace/experiments/agent-skills && python3 skills/monitor-website/local/unlazy/scripts/gate_hash_check.py"
  EXPECT: INSTALL_UNIFORM_OK
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/home/graham/workspace/experiments/agent-skills/skills/monitor-website/local/unlazy; path=7c36c0ef0b5d/27 entries; EXPECT=matched; output-sha256=0401c5380b45b1d3ffe3bea021576c86f281c1bed50cf2631c5ff0b4865fd369; output-bytes=19

- [x] G5: live local server serves the same artifact
  CHECK: bash -c "cd /home/graham/workspace/experiments/agent-skills && curl -sf -m 5 http://127.0.0.1:3020/projects/memory-recall-card.svg | sha256sum | cut -d' ' -f1 > /tmp/served.sha && sha256sum site/public/projects/memory-recall-card.svg | cut -d' ' -f1 > /tmp/src.sha && cmp -s /tmp/served.sha /tmp/src.sha && echo SERVED_MATCH_OK"
  EXPECT: SERVED_MATCH_OK
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/home/graham/workspace/experiments/agent-skills/skills/monitor-website/local/unlazy; path=7c36c0ef0b5d/27 entries; EXPECT=matched; output-sha256=4f90a92d84482935ec93f5b9ee5e62ee1e13d2d869de30e812491dfde0c4464a; output-bytes=16

- [x] G6: fresh rendered screenshot of the card exists for visual inspection
  CHECK: bash -c "test -s /tmp/claude-1000/-home-graham-workspace-experiments-agent-skills/5e6a6422-febb-4d0d-9b66-2199157e6396/scratchpad/brand-card-full.png && test -s /tmp/claude-1000/-home-graham-workspace-experiments-agent-skills/5e6a6422-febb-4d0d-9b66-2199157e6396/scratchpad/brand-card-400.png && echo SCREENSHOTS_EXIST_OK"
  EXPECT: SCREENSHOTS_EXIST_OK
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/home/graham/workspace/experiments/agent-skills/skills/monitor-website/local/unlazy; path=7c36c0ef0b5d/27 entries; EXPECT=matched; output-sha256=ed6f19ef7af7e2d8b069118feb48868c4e11e9e141a8f2014e6891afb4893539; output-bytes=21

- [x] G7: retained agentic eval for the governing skill is READY
  CHECK: bash -c "cd /home/graham/workspace/experiments/agent-skills && python3 -c \"import json;r=json.load(open('skills/best-practices-svg-design/fixtures/agentic_eval.latest-result.json'));print('EVAL_'+r['readiness'])\""
  EXPECT: EVAL_READY
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/home/graham/workspace/experiments/agent-skills/skills/monitor-website/local/unlazy; path=7c36c0ef0b5d/27 entries; EXPECT=matched; output-sha256=b4ad7ee7794c3634c4682b9aa35f72f4152babaaa378db5cd005afde619b6bbb; output-bytes=11

- [x] G8: narrow commit retained locally
  CHECK: bash -c "git log -1 --name-only --pretty=format:%s | grep -q 'grahama-ember' && echo COMMIT_RETAINED_OK"
  EXPECT: COMMIT_RETAINED_OK
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/home/graham/workspace/experiments/agent-skills/skills/monitor-website/local/unlazy; path=7c36c0ef0b5d/27 entries; EXPECT=matched; output-sha256=09da1e64d5917172ee85dc4aaab91fbe107f6e65d94c32b0e3bc9df0d4ed66d8; output-bytes=19

- [x] G10: artwork-level even spacing is deterministic and OK
  CHECK: bash -c "cd /home/graham/workspace/experiments/agent-skills && python3 skills/best-practices-svg-design/scripts/check_svg_spacing.py docs/assets/project-cards/memory-recall-card.svg"
  EXPECT: SPACING_OK
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/home/graham/workspace/experiments/agent-skills/skills/monitor-website/local/unlazy; path=7c36c0ef0b5d/27 entries; EXPECT=matched; output-sha256=6cc982206e766031d0ac42a30552ac42efe9a4662ed530564ddf3b2336576309; output-bytes=431

- [x] G11: grid manifest matches the solved uniform grid
  CHECK: bash -c "cd /home/graham/workspace/experiments/agent-skills && python3 skills/best-practices-svg-design/scripts/check_grid.py docs/assets/project-cards/memory-recall-card.grid.json"
  EXPECT: GRID_OK
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/home/graham/workspace/experiments/agent-skills/skills/monitor-website/local/unlazy; path=7c36c0ef0b5d/27 entries; EXPECT=matched; output-sha256=cb4e2b04b7209384c3b282e2456cc495c77c537c0104dddfcab82a81c40ca26e; output-bytes=171

- [x] G12: served page references the current card via versioned URL
  CHECK: bash -c "cd /home/graham/workspace/experiments/agent-skills && V=$(sha256sum site/out/projects/memory-recall-card.svg | cut -c1-8) && curl -s http://127.0.0.1:3020/explore.html | grep -q \"memory-recall-card.svg?v=\" && curl -s http://127.0.0.1:3020/projects/memory-recall-card.svg | sha256sum | grep -q \"^$(sha256sum docs/assets/project-cards/memory-recall-card.svg | cut -d' ' -f1)\" && echo SERVED_VERSIONED_OK"
  EXPECT: SERVED_VERSIONED_OK
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/home/graham/workspace/experiments/agent-skills/skills/monitor-website/local/unlazy; path=7c36c0ef0b5d/27 entries; EXPECT=matched; output-sha256=31f50f8107a28dfc2da6246b96169625ad25dc7a160890ec9ef4ef5bb3aca358; output-bytes=187

- [ ] G9: MANUAL - human accepts the brand-palette design (create-svg Stage-2 gate)
  Human review of the rendered card at full and 400px sizes. Until Graham
  approves, final status is Immutable Goal: NOT_MET (design acceptance
  outstanding). Push to origin/main is out of scope per HANDOFF.md (divergent
  branch, ahead/behind).
  EVIDENCE: pending
