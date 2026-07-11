# Agent Quickstart

Run this first:

```bash
./run.sh research-bakeoff smoke
```

Then inspect:

```bash
cat runs/embry_agent_smoke_001/story_assets/short_story.md
cat runs/embry_agent_smoke_001/story_assets/scenes_script.yaml
xdg-open runs/embry_agent_smoke_001/story_assets/contact_sheet_renders/embry_primary_perspectives/contact_sheet.html
```

For hosted A/V baseline:

```bash
export FAL_KEY="YOUR_FAL_KEY"  # FAL_API_KEY is also accepted.

./run.sh research-bakeoff elevenlabs
```

For full instructions, read:

```text
PROJECT_AGENT_INSTRUCTIONS.md
PROJECT_AGENT_MANIFEST.json
```
