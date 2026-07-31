"""RelayForge V16 Blue patch manifest.

This replacement file is intentionally declarative: the live topology selection
authority applies controls from the public action catalog, and this module
exposes the selected Blue controls without provider commands, headers, URLs,
filesystem paths, or private implementation assumptions.
"""

PUBLIC_ENTRYPOINT = "/api/v1"
SELECTION_AUTHORITY = "BATTLE"
PROVIDER_COMMAND_EXECUTION = False

BLUE_PATCH_MANIFEST = {
    "artifact_type": "blue_patch",
    "target_id": "battle-v16-relayforge-a",
    "selected_controls": [
        {
            "operation": "cache-principal-partition",
            "parameters": {"enabled": True},
            "purpose": "Partition report and recent-observation cache lookups by caller principal so an observed opaque reference cannot be used across ownership boundaries.",
        },
        {
            "operation": "capability-audience-policy",
            "parameters": {"enabled": True},
            "purpose": "Bind preview and report-profile capabilities to their intended audience while preserving documented valid workflows.",
        },
    ],
    "preserve_functionality_contract": [
        "regular-package-import",
        "in-bound-transformed-object",
        "tenant-owned-report",
        "valid-external-preview",
        "safe-report-profile",
        "legacy-conversion",
    ],
    "rejected_controls": [
        "broad-quarantine",
        "legacy-convert-disable",
    ],
}


def get_blue_patch_manifest():
    """Return the public Blue patch manifest for the arena harness."""
    return BLUE_PATCH_MANIFEST


def application(environ, start_response):
    """Minimal WSGI-compatible responder exposing that the patch is loaded."""
    body = b'{"status":"blue_patch_loaded","selection_authority":"BATTLE"}'
    start_response(
        "200 OK",
        [
            ("Content-Type", "application/json"),
            ("Content-Length", str(len(body))),
        ],
    )
    return [body]
