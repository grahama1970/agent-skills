#!/usr/bin/env bash
# Symlink Battle spectator static assets into a host public directory.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BATTLE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ASSETS="$BATTLE_DIR/assets/sprites/pixijs"
FIXTURES_PARENT="$BATTLE_DIR/local/battle-004-parent-spawn-pixi-replay"
FIXTURES_KILL="$BATTLE_DIR/local/battle-004-kill-shot-pixi-replay"
HOST_PUBLIC="${1:?usage: sync-host-battle-static.sh <host-public-dir>}"

SPRITES_DIR="$HOST_PUBLIC/battle-sprites/pixijs"
FIXTURE_DIR="$HOST_PUBLIC/battle-fixtures/battle-004-parent-spawn-pixi-replay"
KILL_FIXTURE_DIR="$HOST_PUBLIC/battle-fixtures/battle-004-kill-shot-pixi-replay"
mkdir -p "$SPRITES_DIR" "$FIXTURE_DIR" "$KILL_FIXTURE_DIR"

for f in "$ASSETS"/*; do
  base="$(basename "$f")"
  ln -sfn "$f" "$SPRITES_DIR/$base"
done

ln -sfn "$FIXTURES_PARENT/battle.normalized_ux_fixture.json" \
  "$FIXTURE_DIR/battle.normalized_ux_fixture.json"

ln -sfn "$FIXTURES_KILL" "$KILL_FIXTURE_DIR"

echo "Synced battle static assets into $HOST_PUBLIC"
