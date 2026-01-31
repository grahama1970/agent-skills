#!/usr/bin/env python3
"""
Sanity check for Horus Music Taxonomy (HMT) Verifier.

Verifies that:
1. HMT module can be imported
2. Feature extraction works on sample music entry
3. Bridge attributes are correctly identified
4. Lore connection scoring works

Exit codes:
  0 = PASS
  1 = FAIL
"""

import sys
from pathlib import Path

# Add persona path
PERSONA_PATH = Path("/home/graham/workspace/experiments/memory/persona")
sys.path.insert(0, str(PERSONA_PATH))

def test_import():
    """Test that HMT module imports correctly."""
    try:
        from bridge.horus_music_taxonomy import (
            HorusMusicTaxonomyVerifier,
            create_music_verifier,
            HMT_VOCABULARY,
            MUSIC_BRIDGE_INDICATORS,
        )
        print("✓ Import successful")
        return True
    except ImportError as e:
        print(f"✗ Import failed: {e}")
        return False


def test_feature_extraction():
    """Test feature extraction on sample music entry."""
    from bridge.horus_music_taxonomy import create_music_verifier

    verifier = create_music_verifier()

    # Chelsea Wolfe - known Dark Folk / Doom artist
    music_entry = {
        "title": "Chelsea Wolfe - Carrion Flowers",
        "artist": "Chelsea Wolfe",
        "channel": "Chelsea Wolfe",
        "tags": ["doom", "dark folk", "goth"],
    }

    features = verifier.extract_features(music_entry)

    # Verify structure
    assert "collection" in features, "Missing 'collection' field"
    assert features["collection"] == "music", f"Expected 'music', got {features['collection']}"
    assert "dimensions" in features, "Missing 'dimensions' field"
    assert "bridge_attributes" in features, "Missing 'bridge_attributes' field"
    assert "confidence" in features, "Missing 'confidence' field"

    # Chelsea Wolfe should map to Fragility bridge (delicate, acoustic, vulnerable)
    bridges = features["bridge_attributes"]
    domains = features["dimensions"].get("domain", [])

    print(f"✓ Feature extraction: bridges={bridges}, domains={domains}")
    return True


def test_bridge_indicators():
    """Test that bridge indicators are properly configured."""
    from bridge.horus_music_taxonomy import MUSIC_BRIDGE_INDICATORS

    required_bridges = ["Precision", "Resilience", "Fragility", "Corruption", "Loyalty", "Stealth"]

    for bridge in required_bridges:
        assert bridge in MUSIC_BRIDGE_INDICATORS, f"Missing bridge: {bridge}"
        indicators = MUSIC_BRIDGE_INDICATORS[bridge]
        assert "indicators" in indicators, f"Bridge {bridge} missing 'indicators'"
        assert "artists" in indicators, f"Bridge {bridge} missing 'artists'"
        assert "lore_resonance" in indicators, f"Bridge {bridge} missing 'lore_resonance'"

    print(f"✓ Bridge indicators: {len(required_bridges)} bridges configured")
    return True


def test_lore_connection():
    """Test music-to-lore connection scoring."""
    from bridge.horus_music_taxonomy import create_music_verifier

    verifier = create_music_verifier()

    # Music entry with Resilience indicators
    music_entry = {
        "title": "Sabaton - The Last Stand",
        "artist": "Sabaton",
    }

    # Lore entry about Siege of Terra (Resilience theme)
    lore_entry = {
        "full_text": "The Imperial Fists held the walls of Terra, Rogal Dorn commanding the defense against impossible odds.",
        "entities": ["Imperial Fists", "Rogal Dorn", "Terra"],
        "collection": "horus_lore"
    }

    connection = verifier.verify_music_to_lore(music_entry, lore_entry)

    assert "score" in connection, "Missing 'score' in connection result"
    assert "shared_bridges" in connection, "Missing 'shared_bridges' in connection result"
    assert connection["score"] >= 0.0, "Score should be >= 0"
    assert connection["score"] <= 1.0, "Score should be <= 1"

    print(f"✓ Lore connection: score={connection['score']:.2f}, bridges={connection['shared_bridges']}")
    return True


def test_find_music_for_scene():
    """Test finding music for a lore scene."""
    from bridge.horus_music_taxonomy import create_music_verifier

    verifier = create_music_verifier()

    candidates = [
        {"title": "Wardruna - Helvegen", "artist": "Wardruna"},
        {"title": "Sabaton - The Last Stand", "artist": "Sabaton"},
        {"title": "Chelsea Wolfe - Carrion Flowers", "artist": "Chelsea Wolfe"},
        {"title": "Two Steps From Hell - Victory", "artist": "Two Steps From Hell"},
    ]

    scene = "The Siege of Terra, Imperial Fists defending against the traitor legions"
    results = verifier.find_music_for_scene(scene, candidates)

    assert len(results) == len(candidates), "Should return results for all candidates"
    assert all("score" in r for r in results), "Each result should have a score"

    # Results should be sorted by score descending
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True), "Results should be sorted by score"

    print(f"✓ Find music for scene: top match = {results[0]['music']['title']} (score={results[0]['score']:.2f})")
    return True


def main():
    print("=== HMT Verifier Sanity Check ===\n")

    tests = [
        ("Import", test_import),
        ("Feature Extraction", test_feature_extraction),
        ("Bridge Indicators", test_bridge_indicators),
        ("Lore Connection", test_lore_connection),
        ("Find Music for Scene", test_find_music_for_scene),
    ]

    passed = 0
    failed = 0

    for name, test_fn in tests:
        try:
            if test_fn():
                passed += 1
            else:
                failed += 1
                print(f"✗ {name}: FAILED")
        except Exception as e:
            failed += 1
            print(f"✗ {name}: ERROR - {e}")

    print(f"\n=== Results: {passed}/{len(tests)} passed ===")

    if failed > 0:
        print("SANITY CHECK FAILED")
        sys.exit(1)
    else:
        print("SANITY CHECK PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
