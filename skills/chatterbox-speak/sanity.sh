#!/usr/bin/env bash
# Offline-safe sanity: frontmatter, CLI loads, bad-input fails closed.
set -euo pipefail
cd "$(dirname "$0")"

python3 - <<'EOF'
import yaml, pathlib
text = pathlib.Path("SKILL.md").read_text()
assert text.startswith("---\n"), "frontmatter must open on line 1"
fm = yaml.safe_load(text.split("---\n")[1])
for k in ("name", "description", "triggers", "provides", "composes", "complies"):
    assert fm.get(k), f"missing frontmatter field: {k}"
assert fm["name"] == "chatterbox-speak"
print("frontmatter OK")
EOF

./run.sh speak --help >/dev/null && echo "CLI OK"

python3 scripts/pronounce.py && echo "pronounce OK"
python3 scripts/pauses.py && echo "pauses OK"

# negative control: unknown voice must exit non-zero without touching the service
if ./run.sh speak --text hi --voice nosuchvoice 2>/dev/null; then
  echo "FAIL: unknown voice accepted"; exit 1
fi
echo "negative control OK"

# live positive control only when the service is up (skipped != pass)
if curl -sf -m 2 http://127.0.0.1:8018/health >/dev/null 2>&1; then
  out=$(./run.sh speak --text 'sanity check' --voice embry --tone neutral_warm)
  wav=$(echo "$out" | python3 -c "import json,sys; print(json.load(sys.stdin)['wav'])")
  test -s "$wav" && echo "live render OK: $wav"
else
  echo "live render NOT_ESTABLISHED (service down)"
fi
