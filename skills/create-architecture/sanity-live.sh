#!/usr/bin/env bash
set -euo pipefail
skill_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$skill_dir/sanity.sh" live
bash "$skill_dir/sanity.sh" gsn
exec bash "$skill_dir/sanity.sh" adversarial
