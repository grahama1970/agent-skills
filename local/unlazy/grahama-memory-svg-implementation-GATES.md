# Gates: grahama memory SVG implementation

OWNS: site/app/page.tsx, site/app/explore/page.tsx, site/components/capability-constellation.tsx, site/app/globals.css, site/content.json, site/research-map.json, site/project-visibility.json, site/graph.json, site/scripts/gen_visibility.py, docs/assets/project-cards/memory-recall-card.svg, site/public/projects/memory-recall-card.svg, site/public/projects/thumbs/memory-recall-card.svg

Scope: apply the WebGPT-reviewed memory project card direction into the primary grahama.co site source without relying on a timestamped worktree or WebP as the visible source asset.

- [x] G1: named skill contract was read before this implementation report
  CHECK: test -s skills/unlazy/SKILL.md && test -s skills/unlazy/references/agent-skills-workflow.md && echo UNLAZY_CONTRACT_READ_OK
  EXPECT: UNLAZY_CONTRACT_READ_OK
  CWD: ../..
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/home/graham/workspace/experiments/agent-skills; path=fe435e1a01b7/29 entries; EXPECT=matched; output-sha256=132543cecf912ce4557ac112f41dbec0647cfe445d52bf32638d496c18a81424; output-bytes=24

- [x] G2: memory card is served from SVG in root and explore card renderers
  CHECK: python3 -c "from pathlib import Path; text=Path('site/app/page.tsx').read_text()+Path('site/app/explore/page.tsx').read_text(); assert text.count('memory-recall-card.svg') >= 2; assert text.count('meta.asset') >= 2; print('MEMORY_CARD_SVG_ROUTE_OK')"
  EXPECT: MEMORY_CARD_SVG_ROUTE_OK
  CWD: ../..
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/home/graham/workspace/experiments/agent-skills; path=fe435e1a01b7/29 entries; EXPECT=matched; output-sha256=94421f246b51c464a1c36d9288a262f992d3f487ebe9959db43a1cc9adeff0c5; output-bytes=25

- [x] G3: public memory SVG assets parse as XML
  CHECK: python3 -c "import xml.etree.ElementTree as ET; [ET.parse(p) for p in ['docs/assets/project-cards/memory-recall-card.svg','site/public/projects/memory-recall-card.svg','site/public/projects/thumbs/memory-recall-card.svg']]; print('MEMORY_SVG_XML_OK')"
  EXPECT: MEMORY_SVG_XML_OK
  CWD: ../..
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/home/graham/workspace/experiments/agent-skills; path=fe435e1a01b7/29 entries; EXPECT=matched; output-sha256=b4ed8ffc960356fa2dc74e87863ba733cd70908b38598b818a8970c9d39a1404; output-bytes=18

- [x] G4: generated graph marks memory and sparta as private-evidence public overviews
  CHECK: python3 -c "import json; g=json.load(open('site/graph.json')); nodes={n.get('slug'):n for n in g['nodes'] if n.get('type')=='project'}; assert nodes['memory']['visibility']=='public-overview' and nodes['memory']['evidenceAccess']=='abstract'; assert nodes['sparta-explorer']['visibility']=='public-overview' and nodes['sparta-explorer']['evidenceAccess']=='abstract'; assert g['counts']['nodes']==len(g['nodes']) and g['counts']['edges']==len(g['edges']); print('PRIVATE_OVERVIEW_GRAPH_OK')"
  EXPECT: PRIVATE_OVERVIEW_GRAPH_OK
  CWD: ../..
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/home/graham/workspace/experiments/agent-skills; path=fe435e1a01b7/29 entries; EXPECT=matched; output-sha256=ce918128549f98c1cad61ca951977afc875db5c8b6b949402ad194fa0299bb4a; output-bytes=26

- [x] G5: graph click regression guard no longer prevents anchor clicks on pointerdown
  CHECK: python3 -c "from pathlib import Path; t=Path('site/components/capability-constellation.tsx').read_text(); assert 'Math.hypot' in t and 'startX' in t and 'startY' in t; assert 'const startDrag' in t and 'ev.preventDefault();\\n    drag.current' not in t; print('GRAPH_CLICK_DRAG_THRESHOLD_OK')"
  EXPECT: GRAPH_CLICK_DRAG_THRESHOLD_OK
  CWD: ../..
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/home/graham/workspace/experiments/agent-skills; path=fe435e1a01b7/29 entries; EXPECT=matched; output-sha256=bde8a53fa76a985d0dc7a5e8c0eb6d3e3d7497df8c6116ace07c451f005ae4b4; output-bytes=30

- [x] G6: site production build passes
  CHECK: npm run build
  EXPECT: Compiled successfully
  CWD: ../../site
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/home/graham/workspace/experiments/agent-skills/site; path=fe435e1a01b7/29 entries; EXPECT=matched; output-sha256=d3e460a6cb831b35431235505db87438449774dcc9c99418bc955e40d68a2967; output-bytes=3387

- [x] G7: local CDP verification marker exists for root memory card surface
  CHECK: test -s .codex/ui-verification/latest.json && python3 -c "import json; d=json.load(open('.codex/ui-verification/latest.json')); assert d.get('name') in {'grahama-memory-svg-root-local','grahama-memory-svg-explore-local'}; print('CDP_MARKER_READBACK_OK')"
  EXPECT: CDP_MARKER_READBACK_OK
  CWD: ../..
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/home/graham/workspace/experiments/agent-skills; path=fe435e1a01b7/29 entries; EXPECT=matched; output-sha256=481adbc0e932be7ba20fecaad5f09480b11f29deab101a3e7d4dc9cc86671c9f; output-bytes=23

- [x] G8: memory graph click navigates to the memory card in the exported site
  CHECK: node -e "const { chromium } = require('playwright'); (async()=>{ const browser=await chromium.launch({headless:true}); const page=await browser.newPage({viewport:{width:1440,height:1100}}); await page.goto('http://127.0.0.1:3020/explore.html',{waitUntil:'networkidle'}); await page.locator('[data-qid=\"constellation:jump:memory\"]').click({force:true,timeout:5000}); await page.waitForFunction(()=>{ const el=document.querySelector('#project-memory'); return location.hash==='#project-memory' && el && el.getBoundingClientRect().top < 340; },{timeout:5000}); const r=await page.evaluate(()=>({hash:location.hash, top:document.querySelector('#project-memory').getBoundingClientRect().top})); await browser.close(); console.log('MEMORY_GRAPH_CLICK_OK '+JSON.stringify(r)); })().catch(e=>{ console.error(e.stack||e); process.exit(1); });"
  EXPECT: MEMORY_GRAPH_CLICK_OK
  CWD: ../../site
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/home/graham/workspace/experiments/agent-skills/site; path=fe435e1a01b7/29 entries; EXPECT=matched; output-sha256=16a16905235712d58b1cfd2081a58961d4e89d607d5c67151cc174a6dc869eb8; output-bytes=64

- [ ] G9: final report does not claim live deployment
  EVIDENCE: pending
