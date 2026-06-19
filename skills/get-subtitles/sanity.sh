#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

unset VIRTUAL_ENV
UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/tmp/get-subtitles-venv}" uv run python - <<'PY'
from pathlib import Path
import re

skill = Path("SKILL.md").read_text()
assert skill.startswith("---\n"), "SKILL.md must start with frontmatter"
assert "\ncomposes:\n  - brave-search\n" in skill, "must compose brave-search"
assert "\n  - memory\n" in skill, "must compose memory"
assert "\n  - ingest-movie\n" in skill, "must compose ingest-movie"
assert "triggers:" in skill and "provides:" in skill and "complies:" in skill
assert re.search(r"^name: get-subtitles$", skill, re.M), "name must match directory"
PY

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
touch "$tmp/sample.mkv"
printf '1\n00:00:00,000 --> 00:00:01,000\nHello.\n' > "$tmp/sample.en.srt"

./run.sh verify-file --media-path "$tmp/sample.mkv" --language en --json | python -c '
import json, sys
data = json.load(sys.stdin)
assert data["status"] == "verified", data
assert data["subtitle_path"].endswith(".en.srt"), data
assert data["primary_subtitle_format"] == "srt", data
assert any(item["format"] == "srt" for item in data["subtitle_files"]), data
'

rm "$tmp/sample.en.srt"
./run.sh verify-file --media-path "$tmp/sample.mkv" --language en --json | python -c '
import json, sys
data = json.load(sys.stdin)
assert data["status"] == "not_verified", data
assert data["safe_default"] == "do_not_process_for_watch_or_orpheus", data
'

./run.sh discover --actor "Kristen Stewart" --genre comedy --emotion laugh --dry-run --json | python -c '
import json, sys
data = json.load(sys.stdin)
assert data["status"] == "planned", data
assert data["composed_skill"] == "brave-search", data
assert len(data["queries"]) >= 3, data
assert "handoff" in data, data
'

set +e
api_output="$(./run.sh api-search-download --series-id 123 --episode-id 456 --language en --preferred-formats vtt,ass,srt --dry-run --json 2>/dev/null)"
api_status=$?
set -e
printf '%s' "$api_output" | python -c '
import json, sys
data = json.load(sys.stdin)
if data["status"] == "not_available":
    assert "generic_subtitle_search_download_endpoints_not_exposed" in data["reason"], data
    assert "/api/providers/movies" in data["available_alternative"], data
else:
    assert data["status"] in {"planned", "not_verified"}, data
'
test "$api_status" -eq 0 -o "$api_status" -eq 2

printf '1\n00:00:02,500 --> 00:00:04,000\n(LAUGHS)\n\n2\n00:00:05,000 --> 00:00:06,000\n[PEOPLE CHATTERING]\n\n3\n00:00:07,000 --> 00:00:08,500\nLISA CONTINUES LAUGHING\n' > "$tmp/emotions.en.srt"
./run.sh scan-srt --subtitle "$tmp/emotions.en.srt" --emotion laugh,chuckle --targeted-emotions --json | python -c '
import json, sys
data = json.load(sys.stdin)
assert data["status"] == "has_orpheus_tags", data
assert data["counts"]["laugh"] == 2, data
assert data["counts"]["chuckle"] == 0, data
match = data["matches"][0]
assert match["timecode"] == "00:00:02,500 --> 00:00:04,000", match
assert match["start_seconds"] == 2.5, match
assert match["end_seconds"] == 4.0, match
action = data["matches"][1]
assert action["timecode"] == "00:00:07,000 --> 00:00:08,500", action
assert action["speaker"] == "Lisa", action
assert action["cue_type"] == "subtitle_action_line", action
'

printf 'WEBVTT\n\n00:00:01.000 --> 00:00:02.250\n<v Willie>(CHUCKLES)</v>\n' > "$tmp/emotions.en.vtt"
./run.sh scan-srt --subtitle "$tmp/emotions.en.vtt" --emotion chuckle --targeted-emotions --json | python -c '
import json, sys
data = json.load(sys.stdin)
assert data["status"] == "has_orpheus_tags", data
assert data["metadata"]["format"] == "vtt", data
assert data["metadata"]["speaker_metadata_status"] == "structured_vtt_voice_tags", data
assert data["metadata"]["vtt_speakers"] == ["Willie"], data
match = data["matches"][0]
assert match["emotion"] == "chuckle", match
assert match["speaker"] == "Willie", match
assert match["timecode"] == "00:00:01.000 --> 00:00:02.250", match
assert match["start_seconds"] == 1.0, match
assert match["end_seconds"] == 2.25, match
'

cat > "$tmp/emotions.en.ass" <<'ASS'
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:03.00,0:00:04.50,Default,Willie,0,0,0,,(SIGHS)
ASS
./run.sh scan-srt --subtitle "$tmp/emotions.en.ass" --emotion sigh --targeted-emotions --json | python -c '
import json, sys
data = json.load(sys.stdin)
assert data["status"] == "has_orpheus_tags", data
assert data["metadata"]["format"] == "ass", data
assert data["metadata"]["speaker_metadata_status"] == "structured_ass_name_field", data
assert data["metadata"]["ass_speakers"] == ["Willie"], data
match = data["matches"][0]
assert match["emotion"] == "sigh", match
assert match["speaker"] == "Willie", match
assert match["timecode"] == "0:00:03.00 --> 0:00:04.50", match
assert match["start_seconds"] == 3.0, match
assert match["end_seconds"] == 4.5, match
'

UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/tmp/get-subtitles-venv}" uv run python - <<'PY'
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory

spec = importlib.util.spec_from_file_location("get_subtitles_cli", Path("scripts/cli.py"))
assert spec and spec.loader
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)

def fake_discovery_queries(actor, genre, emotions):
    assert actor == "Kristen Stewart"
    assert genre == "comedy"
    return [f"{actor} {genre} {emotion}" for emotion in emotions]

def fake_extract_movie_candidates_with_queries(*args, **kwargs):
    return [
        {
            "title": "Local Laugh Movie",
            "year": 2020,
            "status": "candidate_seed_not_verified",
            "target_emotions": ["laugh"],
            "source_queries": [{"query": "Kristen Stewart comedy laugh"}],
        },
        {
            "title": "External Sigh Movie",
            "year": 2021,
            "status": "candidate_seed_not_verified",
            "target_emotions": ["sigh"],
            "source_queries": [{"query": "Kristen Stewart comedy sigh"}],
        },
    ]

class FakeRun:
    returncode = 0
    stderr = ""
    stdout = json.dumps({"q0": {"web": {"results": [{"title": "Local Laugh Movie (2020)", "url": "https://example.test/local"}]}}})

def fake_subprocess_run(*args, **kwargs):
    return FakeRun()

def fake_bazarr_local_matches(candidate):
    if candidate["title"] == "Local Laugh Movie":
        return [{
            "radarrId": 4242,
            "title": "Local Laugh Movie",
            "year": 2020,
            "path": "/media/Local Laugh Movie (2020)/movie.mkv",
            "sceneName": "Local.Laugh.Movie.2020.WEB-DL",
        }]
    return []

async def fake_ensure_and_scan_one(radarr_id, language, emotions, download):
    assert radarr_id == 4242
    assert language == "en"
    assert download is True
    return {
        "radarr_id": radarr_id,
        "subtitle_receipt": {
            "status": "verified",
            "language": "en",
            "subtitle_path": "/tmp/local-laugh-movie.en.srt",
            "primary_subtitle_format": "srt",
            "subtitle_files": [{
                "path": "/tmp/local-laugh-movie.en.srt",
                "format": "srt",
                "verified": True,
                "speaker_metadata_status": "inline_text_labels",
            }],
            "media_path": "/media/Local Laugh Movie (2020)/movie.mkv",
            "radarr_id": radarr_id,
            "movie_title": "Local Laugh Movie",
            "movie_year": 2020,
            "source": "bazarr",
            "safe_default": "allow_watch_processing",
        },
        "scan": {
            "status": "has_orpheus_tags",
            "counts": {"laugh": 1, "sigh": 0},
            "missing": ["sigh"],
            "matches": [{
                "emotion": "laugh",
                "marker": "(LAUGHS)",
                "timecode": "00:02:24,000 --> 00:02:25,000",
                "start_seconds": 144.0,
                "end_seconds": 145.0,
                "speaker": "Kristen",
                "line": "Kristen: (LAUGHS)",
            }],
        },
    }

def fake_external_subtitle_probe_plan(candidates, emotions, limit):
    return [{
        "candidate_index": 1,
        "candidate": {"title": "External Sigh Movie", "year": 2021},
        "emotion": "sigh",
        "query": "\"External Sigh Movie\" \"2021\" subtitles SRT transcript \"sigh\"",
    }]

def fake_run_brave_batch(queries, workers, timeout_seconds):
    assert queries == ["\"External Sigh Movie\" \"2021\" subtitles SRT transcript \"sigh\""]
    return {"q0": {"web": {"results": [{
        "title": "Subtitle lead only",
        "url": "https://example.test/subtitle-lead",
        "description": "00:01:00 --> 00:01:01 (SIGHS) subtitle snippet",
    }]}}}

def fake_external_evidence(probes, results):
    return [{
        "candidate": {"title": "External Sigh Movie", "year": 2021},
        "status": "external_subtitle_candidate_not_verified",
        "evidence_level": "external_search_snippet_only",
        "evidence_policy": "brave_snippets_are_not_subtitle_files",
        "target_emotions": ["sigh"],
        "evidence": [{
            "emotion": "sigh",
            "query": probes[0]["query"],
            "has_subtitle_signal": True,
            "has_emotion_signal": True,
            "title": "Subtitle lead only",
            "url": "https://example.test/subtitle-lead",
            "description": "00:01:00 --> 00:01:01 (SIGHS) subtitle snippet",
        }],
        "safe_default": "do_not_recommend_movie_download_until_subtitle_file_is_downloaded_and_scanned",
    }]

def fake_bazarr_nonlocal_subtitle_probe(candidate, *, create_radarr_stub, sync_wait_seconds):
    assert create_radarr_stub is True
    assert sync_wait_seconds == 1.0
    return {
        "candidate": candidate,
        "status": "subtitle_provider_vetted",
        "bazarr_title_search": {"status": "ok", "result_count": 0, "results": []},
        "radarr_stub": {
            "status": "added_unmonitored_metadata_stub",
            "radarr_id": 5252,
            "monitored": False,
            "has_file": False,
            "search_for_movie": False,
        },
        "bazarr_sync": {"status": "started", "status_code": 204},
        "bazarr_movie": {"status": "found", "attempts": [{"status_code": 200, "row_count": 1}], "records": []},
        "provider_probe": {"status": "provider_results_found", "provider_count": 2, "providers": [{"provider": "OpenSubtitles"}]},
        "safe_default": "do_not_recommend_movie_download_until_subtitle_text_is_downloaded_and_scanned",
    }

def fake_fetch_external_subtitle_artifact(candidate, evidence):
    return {
        "status": "fetched",
        "candidate": candidate,
        "source_url": evidence["url"],
        "final_url": "https://example.test/external-sigh-movie.en.srt",
        "download_url": None,
        "artifact_path": "/tmp/external-sigh-movie.en.srt",
        "format": "srt",
        "byte_count": 128,
        "has_timecodes": True,
        "evidence": evidence,
        "safe_default": "scan_before_recommendation",
    }

def fake_scan_external_artifact(fetch_receipt, emotions):
    return {
        "status": "scanned",
        "fetch": fetch_receipt,
        "scan": {
            "status": "has_orpheus_tags",
            "counts": {"laugh": 0, "sigh": 1},
            "missing": ["laugh"],
            "matches": [{
                "emotion": "sigh",
                "marker": "(SIGHS)",
                "timecode": "00:01:00,000 --> 00:01:01,000",
                "start_seconds": 60.0,
                "end_seconds": 61.0,
                "speaker": None,
                "line": "(SIGHS)",
            }],
        },
        "has_timecoded_orpheus_hits": True,
        "safe_default": "recommendation_allowed_only_for_timecoded_hits",
    }

cli.discovery_queries = fake_discovery_queries
cli.extract_movie_candidates_with_queries = fake_extract_movie_candidates_with_queries
cli.subprocess.run = fake_subprocess_run
cli.bazarr_local_matches_for_candidate = fake_bazarr_local_matches
cli.ensure_and_scan_one = fake_ensure_and_scan_one
cli.external_subtitle_probe_plan = fake_external_subtitle_probe_plan
cli.run_brave_batch = fake_run_brave_batch
cli.external_subtitle_evidence_from_results = fake_external_evidence
cli.bazarr_nonlocal_subtitle_probe = fake_bazarr_nonlocal_subtitle_probe
cli.fetch_external_subtitle_artifact = fake_fetch_external_subtitle_artifact
cli.scan_external_artifact = fake_scan_external_artifact

with TemporaryDirectory() as td:
    output = Path(td) / "orpheus-sanity.json"
    cli.orpheus_sanity(
        actor="Kristen Stewart",
        genre="comedy",
        emotion="laugh,sigh",
        all_orpheus_emotions=False,
        download=True,
        external_subtitle_probes=True,
        external_probe_limit=4,
        fetch_external_subtitles=True,
        max_external_fetches=2,
        probe_nonlocal_bazarr=True,
        create_radarr_stubs=True,
        max_nonlocal_probes=2,
        bazarr_sync_wait_seconds=1.0,
        count=3,
        candidate_limit=10,
        output=output,
        json_output=True,
    )
    data = json.loads(output.read_text())

assert data["status"] == "ok", data
assert data["mode"] == "subtitle_discovery_bazarr_local_recovery_nonlocal_bazarr_probe", data
assert data["brave_query_count"] == 2, data
assert data["candidate_count"] == 2, data
assert data["local_bazarr_match_count"] == 1, data
assert data["bazarr_download_enabled"] is True, data
assert data["bazarr_download_attempted"] is True, data
assert data["bazarr_download_radarr_ids"] == [4242], data
assert data["nonlocal_bazarr_probe_enabled"] is True, data
assert data["nonlocal_radarr_stub_creation_enabled"] is True, data
assert data["nonlocal_bazarr_probe_count"] == 1, data
assert data["external_subtitle_download_supported"] is True, data
assert data["external_subtitle_download_attempted"] is True, data
assert data["external_subtitle_fetch_count"] == 1, data
assert data["verified_subtitles"][0]["path"].endswith(".srt"), data
assert data["emotion_coverage"] == {"laugh": 1, "sigh": 0}, data
assert data["external_emotion_coverage"] == {"laugh": 0, "sigh": 1}, data
assert data["combined_emotion_coverage"] == {"laugh": 1, "sigh": 1}, data
assert data["unfound_emotion_tags"] == [], data
assert data["local_verified_hits"][0]["emotion"] == "laugh", data
assert data["external_verified_hits"][0]["emotion"] == "sigh", data
assert data["local_verified_hits"][0]["timecode"] == "00:02:24,000 --> 00:02:25,000", data
assert data["movie_recommendation_count"] == 3, data
assert data["local_movie_recommendation_count"] == 1, data
assert data["nonlocal_movie_recommendation_count"] == 2, data
assert data["ingest_movie_handoff_count"] == 2, data
local_handoff = data["ingest_movie_handoff"][0]
assert local_handoff["title"] == "Local Laugh Movie", local_handoff
assert local_handoff["year"] == 2020, local_handoff
assert local_handoff["requires_ingest_movie"] is False, local_handoff
assert local_handoff["subtitle_evidence"]["cue_windows"][0]["emotion"] == "laugh", local_handoff
external_handoff = [
    item for item in data["ingest_movie_handoff"]
    if item["title"] == "External Sigh Movie" and item["requires_ingest_movie"] is True
][0]
assert external_handoff["preferred_release_query"] == "External Sigh Movie 2021 WEB-DL English Subs SRT SDH CC", external_handoff
assert external_handoff["subtitle_evidence"]["cue_windows"][0]["timecode"] == "00:01:00,000 --> 00:01:01,000", external_handoff
assert "skills/ops-nzbgeek/run.sh search" in external_handoff["nzbgeek_search"]["commands"][0], external_handoff
assert all(item["subtitle_evidence"]["subtitle_path"] for item in data["ingest_movie_handoff"]), data
assert len(data["movie_download_recommendations"]) == 1, data
assert data["movie_download_recommendations"][0]["movie"] == "Local Laugh Movie (2020)", data
assert len(data["nonlocal_movie_download_recommendations"]) == 2, data
external_recommendations = [
    item for item in data["nonlocal_movie_download_recommendations"]
    if item["evidence_level"] == "external_subtitle_file_fetched_and_scanned_with_timecodes"
]
assert len(external_recommendations) == 1, data
assert external_recommendations[0]["movie"] == "External Sigh Movie (2021)", data
assert external_recommendations[0]["target_emotions"] == ["sigh"], data
assert data["recommended_ingest_movie_actions"] == data["ingest_movie_handoff"], data
blocked = data["blocked_or_unverified_candidates"]
assert blocked and blocked[0]["status"] == "not_in_local_bazarr_inventory", data
assert "recommended_action" not in blocked[0], blocked[0]
assert blocked[0]["safe_default"] == "do_not_recommend_movie_download", blocked[0]
external = data["external_subtitle_candidates"]
assert external["status"] == "external_search_leads_only", external
assert external["evidence_policy"] == "brave_snippets_are_not_subtitle_files", external
assert data["unvetted_external_leads"], data
assert data["movie_download_recommendations"][0]["safe_default"] == "usable_only_after_local_media_and_subtitle_are_verified", data
PY

echo "get-subtitles sanity passed"
