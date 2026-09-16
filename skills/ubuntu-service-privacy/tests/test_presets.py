"""Self-check for privacy presets: presets toggle OPTIONAL identity items only,
never the code-gated RUNTIME_READ_FILES baseline in models.py."""
from service_privacy.cli import _OPTIONAL_IDENTITY, _PRESETS
from service_privacy.models import RUNTIME_READ_FILES


def test_compliance_safe_removes_nothing():
    assert _PRESETS['compliance-safe'] == frozenset()


def test_minimal_identity_removes_machine_id():
    assert '/etc/machine-id' in _PRESETS['minimal-identity']


def test_locked_down_is_superset_of_minimal_identity():
    assert _PRESETS['minimal-identity'] <= _PRESETS['locked-down']
    assert _PRESETS['locked-down'] <= set(_OPTIONAL_IDENTITY)


def test_presets_never_touch_models_baseline():
    # The presets live in cli.py policy JSON space; models.py RUNTIME_READ_FILES
    # must be untouched by design (presets are a policy-file concern only).
    assert '/etc/machine-id' in RUNTIME_READ_FILES  # baseline stays code-gated
    assert all(p in set(RUNTIME_READ_FILES) | {'/etc/kolide-k2/installer-info.json'}
               for p in _OPTIONAL_IDENTITY)
