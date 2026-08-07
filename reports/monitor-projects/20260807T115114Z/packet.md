# Nightly skill review roundtable — 20260807

Objective: Review the skills amended in agent-skills during the last 24h for
correctness risk, best-practices compliance, composition/architecture drift,
and missed opportunities. agent-skills is a collection of skills; review the
amended skill directories only, never the repository as one project.

Immutable goal / acceptance bar: For each amended skill, either a concrete
executable improvement slice or an explicit "no action needed" with reasons.

Target artifacts (amended skills, last 24h):
- `pitchdeck` — 226 file change(s); commits: 021a68cc2 pitchdeck: record ticket sweep outcome (6 closed, 2 human-gated), 03a87ce54 pitchdeck: record UI spec backlog tickets #1244/#1247/#1248, 045d44034 pitchdeck: record-and-transcribe narration 
  description: Convert a product README into a source-controlled pitch-deck bundle and editable
- `ux-lab` — 58 file change(s); commits: 528686540 persona-dream: journal keyword extraction stopwords + numpy test dep, 8a2f30868 ux-lab + pitchdeck: graduate actionSlot into shared ChatWell; fix placeholder abuse
  description: Launch and validate canonical UX Lab adapters and shared UI owned by agent-skills.
- `monitor-opportunities` — 46 file change(s); commits: 1794927b3 monitor-opportunities: frame creative arc as color/differentiator, not headline credential (Graham 2026-08-06), 4671461b8 monitor-opportunities: fix SAM.gov probe (prod path + required date 
  description: Nightly opportunity monitor that researches a bounded set of target employers and
- `ask` — 32 file change(s); commits: 1a32c532d ask: live roundtable reliability harness + deterministic failure diagnostic, 2535a16db ask: distinct browser identity failure codes so the agent gets the actionable reason (#1259), 4e8f98e36
  description: Use when the user asks to query project memory, ask an oracle, use supported
- `persona-dream` — 10 file change(s); commits: 49bc2c45e persona-dream: stage canonical panel_001.png via stage-provider-media-local-asset, 528686540 persona-dream: journal keyword extraction stopwords + numpy test dep, 54d16ce97 persona-dream: ca
  description: Create receipt-backed persona dream packets from memory residue. Use when a
- `surf` — 7 file change(s); commits: 5804bb445 ask+surf: agentic-eval for webgpt image-reference manipulation with download, 682e8cd04 surf: live grok-sentinel verifier for #1121 (exit 0 iff no WebGPT wrapper), a0c6a61d4 surf: live kimi 
  description: Unified browser automation for AI agents. Uses surf-cli extension when available
- `best-practices-slide-design` — 6 file change(s); commits: daa6f726f best-practices-slide-design: house slide-design skill with pptx exemplars + theme templates (#1262)
  description: Slide design craft for /pitchdeck: assertion headlines, distance-legible
- `monitor-website` — 4 file change(s); commits: 6b0f3ae92 site: 'The Proof Returns' — receipt-driven lineage instrument + real bridge, 780cc8053 monitor-website: refresh command + disabled-by-default nightly service, f741e0816 monitor-website: docs
  description: Audit and sync the public site (grahama.co, site/) against the repo README. Report-only audit detects drift between README's curated projects/inventory and site/content.json, plus live-site health; apply regenerates content.json from the README. Use for "is the website current", "sync the site with the README", "website drift", or after editing the README project cards or At a Glance table.
- `browser-oracle` — 1 file change(s); commits: b29e2b086 browser-oracle+ask: reviewer windows on Desktop 2 for all seats; eval fixture (#1222)
  description: Persistent browser-oracle tab bindings and directory walk-up registry for

Current evidence:
### project-state (agent-skills, cached)
{
  "project": "agent-skills",
  "project_root": "/home/graham/workspace/experiments/agent-skills",
  "project_profile": "generic",
  "timestamp": "2026-08-07T11:51:15.318616+00:00",
  "mode": "standard",
  "phase_1_infrastructure": {
    "daemons": {
      "applicable": false,
      "reason": "target root is not an Embry-style project",
      "daemons": {},
      "up": 0,
      "total": 0
    },
    "tests": {
      "total": 0,
      "collected": false,
      "error": "tests dir missing",
      "checked_paths": [
        "/home/graham/workspace/experiments/agent-skills/tests",
        "/home/graham/workspace/experiments/agent-skills/services/tests",
        "/home/graham/workspace/experiments/agent-skills/test"
      ]
    },
    "cascade": {
      "applicable": false,
      "reason": "target root is not an Embry-style project",
      "registry": {
        "validators": 0,
        "classifiers": 0,
        "regressors": 0,
        "gpts": 0
      },
      "shadow": {
        "total": 0,
        "usable": 0
      },
      "training_data": {},
      "classifiers_on_disk": [],
      "tier_status": {
        "tier_2_teacher": "NOT_APPLICABLE",
        "tier_1_5_gpt": "NOT_APPLICABLE",
        "tier_0_5_classifier": "NOT_APPLICABLE"
      }
    },
    "daemon_cascade_wiring": {
      "applicable": false,
      "reason": "target root is not an Embry-style project",
      "wired": {}
    },
    "skills": {
      "total": 372,
      "path": "/home/graham/workspace/experiments/agent-skills/skills",
      "missing_skill_md": [
        "__pycache__",
        "audio-caption-service",
        "best-practices-approach-bakeoff",
        "best-practices-design-doc",
        "best-practices-gemini-react-design-loop",
        "best-practices-kling-scene",
        "best-practices-open-design",
        "best-practices-react-flow-dag",
        "best-practices-react-flow-dag-chart",
        "best-practices-script-writer"
      ],
      "missing_skill_md_count": 32,
      "missing_sanity": [
        "agents-registry",
        "animation-vocabulary",
        "apple-design",
        "best-practices-agent",
        "best-practices-chat",
        "best-practices-chat-ux",
        "best-practices-chatterbox-agent",
        "best-practices-converse",
        "best-practices-cots",
        "best-practices-design"
      ],
      "missing_sanity_count": 52
    },
    "frontend": {
      "exists": false
    },
    "deploy": {
      "systemd_units": 0,
      "containerfile": false,
      "docker_compose": false
    },
    "components": {
      "registered": 0,
      "projects": {},
      "note": "No component registry found"
    }
  },
  "phase_2_memory": {
    "available": true,
    "recalls": [
      {
        "query": "agent-skills features architecture deployment",
        "found": true,
        "confidence": 0.8,
        "count": 5,
        "top_items": [
          {
            "problem": "project knowledge chunk for agent-skills: Phase 1: Infrastructure (1)",
            "solution": "### Daemons (4/7 up)\n\n| Daemon | Status |\n|--------|--------|\n| state | OK |\n| voice | OK |\n| sparta | DOWN |\n| memory |"
          },
          {
            "problem": "project knowledge chunk for agent-skills: Current Understanding (43)",
            "solution": "- 2026-07-06 Watch YOLO identity status: Watch owns second-stage character identity over YOLOAnalytics person boxes; YOL"
          },
          {
            "problem": "project knowledge chunk for agent-skills: Current Understanding (13)",
            "solution": "- 2026-05-09 /project-drift is the conservative review gate between recent transcript/tool evidence and durable /project"
          }
        ]
      },
      {
        "query": "agent-skills competitive advantages unique capabilities",
        "found": true,
        "confidence": 0.667,
        "count": 5,
        "top_items": [
          {
            "problem": "project knowledge chunk for agent-skills: Current Understanding (19)",
            "solution": "- 2026-05-30 /ask control-plane competitiveness tranche added deterministic route decisions, lane health, fail-closed un"
          },
          {
            "problem": "project knowledge chunk for agent-skills: Current Understanding (39)",
            "solution": "- 2026-06-28 README/navigation and header refresh: root README now uses docs/assets/agent-skills-header.webp and clarifi"
          },
          {
            "problem": "project knowledge chunk for agent-skills: Current Understanding (28)",
            "solution": "- 2026-06-13 WebGPT reliability real maintainer E2E attempt: created clean isolated worktree /tmp/agent-skills-issue6-e2"
          }
        ]
      },
      {
        "query": "agent-skills known issues gaps missing features",
        "found": true,
        "confidence": 0.733,
        "count": 5,
        "top_items": [
          {
            "problem": "project knowledge chunk for agent-skills: Known Gaps (4)",
            "solution": "    Warmaster/Primarch/Mournival questions.\n  - Live non-truncation is not the same as memory-grounded persona quality.\n"
          },
          {
            "problem": "project knowledge chunk for agent-skills: Known Gaps (9)",
            "solution": "  `Unable to load ... libcudnn_graph.so.9` and `Invalid handle. Cannot load\n  symbol cudnnCreate`. `run_personaplex_offl"
          },
          {
            "problem": "project knowledge chunk for agent-skills: Known Gaps (1)",
            "solution": "- 2026-06-30 4-bit live WebSocket truncation investigation:\n  - The old programmatic receipts that showed empty/short te"
          }
        ]
      }
    ]
  },
  "phase_3_doc_drift": {
    "docs_checked": 7,
    "docs_found": 2,
    "drift_items": [
      {
        "file": "PROJECT_KNOWLEDGE.md",
        "issue": "planned",
        "severity": "low",
        "line": "- 2026-05-09 /hack reality verification: all planned feature and mode checks passed; artifacts under /mnt/storage12tb

### ops-workstation quick health
NOT_ESTABLISHED: command failed (rc=1): 

External research (shared identically with every seat):
### brave-search: pitchdeck
{
  "query": "pitchdeck Convert a product README into a source-controlled pitch-deck bundle and editable best practices",
  "count": 10,
  "offset": 0,
  "results": [
    {
      "title": "awesome-claude-design/recipes/pitch-deck-from-readme.md at main \u00b7 rohitg00/awesome-claude-design",
      "description": "Don&#x27;t try to make Claude write a deck from a sparse README. <strong>Tighten the README first; the deck will inherit the quality</strong>. The deck&#x27;s visual system comes from DESIGN.md, not from defaults.",
      "url": "https://github.com/rohitg00/awesome-claude-design/blob/main/recipes/pitch-deck-from-readme.md"
    },
    {
      "title": "pitch-deck/README.md at master \u00b7 joelparkerhenderson/pitch-deck",
      "description": "Pitch deck advice for startup founders who want to raise venture capital investment - pitch-deck/README.md at master \u00b7 joelparkerhenderson/pitch-deck",
      "url": "https://github.com/joelparkerhenderson/pitch-deck/blob/master/README.md"
    },
    {
      "title": "pitch-deck/README.md at master \u00b7 kuoll/pitch-deck",
      "description": "The HTML Presentation Framework. Contribute to kuoll/pitch-deck development by creating an account on GitHub.",
      "url": "https://github.com/kuoll/pitch-deck/blob/master/README.md"
    },
    {
      "title": "20+ Free Pitch Deck Templates [Fully-Customizable] | Pitch",
      "description": "Need a winning pitch deck? Choose from any of our free pitch deck templates and confidently present your product or service to investors, partners, or potential clients.",
      "url": "https://pitch.com/templates/collections/Pitch-deck"
    },
    {
      "title": "34 Inspiring Pitch Deck Examples + Templates | Figma",
      "description": "A general best practice is to <strong>reduce cognitive load by limiting text to 5 words per line, 5 lines per slide, and no more than 5 consecutive text-heavy slides</strong>.",
      "url": "https://www.figma.com/resource-library/pitch-deck-examples/"
    },
    {
      "title": "GitHub - joelparkerhenderson/pitch-deck: Pitch deck advice for startup founders who want to raise venture capital investment \u00b7 GitHub",
      "description": "Pitch deck advice for startup founders who want to raise venture capital investment - joelparkerhenderson/pitch-deck",
      "url": "https://github.com/joelparkerhenderson/pitch-deck"
    },
    {
      "title": "Pitch Deck | Guide to Winning Investor Presentations",
      "description": "Often as a founder, you&#x27;d have come across several articles that talk about certain &quot;nonpareil&quot; pitch decks that helped their respective startups raise funds during their initial years. Some of these articles walk you through the logic behind every single slide. Others advise you to emulate those pitch decks, and then there are a few who provide editable templates for the same.",
      "url": "https://www.pitchdeck.io/pitchdeck"
    },
    {
      "title": "How to build a startup pitch deck

### brave-search: ux-lab
{
  "query": "ux-lab Launch and validate canonical UX Lab adapters and shared UI owned by agent-skills. best practices",
  "count": 10,
  "offset": 0,
  "results": [
    {
      "title": "GitHub - plugin87/ux-ui-agent-skills: Turn Claude into a Senior Design Architect \u2014 DTCG design tokens, 42 components, WCAG 2.2 accessibility, any-framework code, 138 design systems, and runnable skills.",
      "description": "Adapter Protocol targets any stack \u2014 React+Tailwind, Next.js, SwiftUI, Vue, Svelte, Angular, Solid, Web Components/Lit, React Native, Flutter, Jetpack Compose, vanilla CSS, CSS-in-JS \u2014 or generates a new adapter on demand ... Maps to/from any design system (Material 3, Apple HIG, Fluent, Carbon, shadcn/ui, Radix\u2026) via a role-based crosswalk ... 17 invocable /skills + real scripts (token + contrast validators, real-render &amp; state-aware WCAG gates, axe-core a11y, focus-trap, RTL, taste audit, token build)",
      "url": "https://github.com/plugin87/ux-ui-agent-skills"
    },
    {
      "title": "Top 8 Claude Skills for UI/UX Engineers | Snyk",
      "description": "Think of it as a linter for UI/UX best practices that catches the kind of issues that would fail a WCAG audit or cause real usability problems for keyboard and screen reader users. ... git clone https://github.com/vercel-labs/agent-skills.git cp -r agent-skills/skills/web-design-guidelines ~/.claude/skills/",
      "url": "https://snyk.io/articles/top-claude-skills-ui-ux-engineers/"
    },
    {
      "title": "Design & UI/UX Skills \u2014 Best AI Agent Skills for Design & UI/UX | AgenticSkills",
      "description": "Comprehensive UI/UX design patterns, accessibility standards, and responsive design best practices.",
      "url": "https://agenticskills.io/category/design"
    },
    {
      "title": "UI UX Pro Max Skill \u2014 Design Intelligence for Claude Code",
      "description": "Best practices and anti-patterns for animation, accessibility, z-index, loading states, and more.",
      "url": "https://ui-ux-pro-max-skill.com/"
    },
    {
      "title": "GitHub - vercel-labs/agent-skills: Vercel's official collection of agent skills \u00b7 GitHub",
      "description": "Review UI code for compliance with web interface best practices. Audits your code for 100+ rules covering accessibility, performance, and UX.",
      "url": "https://github.com/vercel-labs/agent-skills"
    },
    {
      "title": "UI/UX Pro Max \u2014 AI Agent Skill by nextlevelbuilder | AgenticSkills",
      "description": "Comprehensive UI/UX design patterns, accessibility standards, and responsive design best practices.",
      "url": "https://agenticskills.io/skills/ui-ux-pro-max"
    },
    {
      "title": "GitHub - urmzd/agentspec: Universal agent skill and sub-agent manager with TUI \u00b7 GitHub",
      "description": "IR layer. Canonical representation with vendor adapters (agentskills, Claude, Gemini) plus instruction-file adapters (AGENTS.md, CLAUDE.md, llms.txt).",
     

### brave-search: monitor-opportunities
{
  "query": "monitor-opportunities Nightly opportunity monitor that researches a bounded set of target employers and best practices",
  "count": 10,
  "offset": 0,
  "results": [
    {
      "title": "BEST PRACTICES FOR EMPLOYERS AND HUMAN RESOURCES/EEO PROFESSIONALS | U.S. Equal Employment Opportunity Commission",
      "description": "<strong>Monitor for EEO compliance</strong> by conducting self-analyses to determine whether current employment practices disadvantage people of color, treat them differently, or leave uncorrected the effects of historical discrimination in the company.",
      "url": "https://www.eeoc.gov/initiatives/e-race/best-practices-employers-and-human-resourceseeo-professionals"
    },
    {
      "title": "How to Monitor Company Career Pages for New Job Openings (Without Checking Daily) - jobstrack.io",
      "description": "This tutorial covers four methods to monitor company career pages for new job openings without checking them manually every day, from free approaches that work for small target lists to automated tools that scale to 50+ companies.",
      "url": "https://jobstrack.io/blog/how-to-monitor-company-career-pages"
    },
    {
      "title": "ChangeTower: Monitor Jobs + Listings",
      "description": "Use <strong>ChangeTower</strong> to monitor jobs for new listings, new openings, updated listings, and competitor hiring practices.",
      "url": "https://changetower.com/monitor-jobs/"
    },
    {
      "title": "Opportunity Employment Best Practices - Job Quality Center of Excellence",
      "description": "<strong>The Aspen Institute Economic Opportunities Program</strong>, et al.",
      "url": "https://jobqualitycenter.org/resource/opportunity-employment-best-practices/"
    },
    {
      "title": "JobBeacon - Career Page Monitor & Job Posting Alerts",
      "description": "\u201c<strong>JobBeacon</strong> gives me instant notifications when a new opening appears at one of my target companies. That usually puts me among the first 10 applicants, which has opened up far more interview opportunities.\u201d",
      "url": "https://jobbeacon.app/"
    },
    {
      "title": "Electronic Monitoring at Work",
      "description": "Synthesizing existing research from several fields hopefully aids in developing a nu- anced understanding of this phenomenon, thereby soberly helping organizations, policymakers, and scholars make informed decisions regarding the use of <strong>electronic monitoring</strong>.",
      "url": "https://www.annualreviews.org/content/journals/10.1146/annurev-orgpsych-110622-060758?crawler=true&mimetype=application%2Fpdf"
    },
    {
      "title": "Monitoring Job Description | Velvet Jobs",
      "description": "Research and analyse applicable regulatory and exchange requirements",
      "url": "https://www.velvetjobs.com/job-descriptions/monitoring"
    },
    {
      "title": "Opportunity Stages Explained With Best Practice Recommendations",
      "description": "Combine this metric

### brave-search coverage note
Research capped at 3 skills; not researched: ask, persona-dream, surf, best-practices-slide-design, monitor-website, browser-oracle


Constraints:
- Skills must comply with best-practices-skills, best-practices-python, and
  best-practices-arangodb (ArangoDB access only via the /memory daemon).
- Recommendations must be scoped to individual skill directories.

Handlers: webgpt, webclaude, webkimi, webgrok, webgemini (concurrent, equal context, peer seats).

Questions for every seat:
1. Which amended skill carries the highest regression or drift risk, and why?
2. What best-practices violations or composition gaps do you see in the
   evidence above?
3. What is the single highest-value executable slice for tomorrow?

Expected response format (per seat):
POSITION: recommended direction.
EVIDENCE: facts, files, receipts, or external sources.
RISKS: likely failure modes and false-green traps.
QUESTIONS: only blockers requiring human/external input.
EXECUTABLE_SLICES: owner, artifact or command, acceptance check.

Proof boundary: Seat responses are advisory reviewer evidence. Local
deterministic verification by the project agent is still required before any
slice is closed.
