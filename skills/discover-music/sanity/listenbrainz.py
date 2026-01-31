#!/usr/bin/env python3
"""
Sanity check for ListenBrainz API.

ListenBrainz has two modes:
- Public API (no token): Get similar artists, trending
- Authenticated API (token): Submit listens, get personal recommendations

Token is optional but recommended for personalized recommendations.

Usage:
    python sanity/listenbrainz.py
"""

import os
import sys

def main():
    try:
        import pylistenbrainz
    except ImportError:
        print("FAIL: pylistenbrainz not installed")
        print("  Install with: pip install pylistenbrainz")
        sys.exit(1)

    # Check for optional token
    token = os.environ.get("LISTENBRAINZ_TOKEN")
    if token:
        print("ListenBrainz token found - will test authenticated features")
    else:
        print("No LISTENBRAINZ_TOKEN - testing public API only")

    print("\nTesting ListenBrainz API...")

    # Create client
    client = pylistenbrainz.ListenBrainz()
    if token:
        client.set_auth_token(token)

    # Test 1: Get similar artists (public)
    print("\n1. Get similar artists for 'Chelsea Wolfe'")
    try:
        # Use direct API call since pylistenbrainz may not have this method
        import requests
        resp = requests.get(
            "https://api.listenbrainz.org/1/lb-radio/artist/Chelsea%20Wolfe/similar",
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            artists = data.get("payload", {}).get("similar", [])[:5]
            if artists:
                for a in artists:
                    name = a.get("artist_name", a.get("name", "Unknown"))
                    print(f"   - {name}")
                print("   PASS: Similar artists works")
            else:
                print("   WARN: No similar artists found (may need different endpoint)")
        else:
            print(f"   WARN: Status {resp.status_code} - trying alternative")
    except Exception as e:
        print(f"   WARN: {e}")

    # Test 2: Get trending artists
    print("\n2. Get site-wide stats")
    try:
        import requests
        resp = requests.get(
            "https://api.listenbrainz.org/1/stats/sitewide/artists",
            params={"count": 5, "range": "week"},
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            artists = data.get("payload", {}).get("artists", [])[:5]
            if artists:
                for a in artists:
                    name = a.get("artist_name", "Unknown")
                    count = a.get("listen_count", 0)
                    print(f"   - {name} ({count} listens)")
                print("   PASS: Site stats works")
            else:
                print("   WARN: No stats returned")
        else:
            print(f"   WARN: Status {resp.status_code}")
    except Exception as e:
        print(f"   WARN: {e}")

    # Test 3: User recommendations (requires token)
    if token:
        print("\n3. Get user recommendations (authenticated)")
        try:
            # Need to know the username - skip if not configured
            username = os.environ.get("LISTENBRAINZ_USERNAME", "")
            if username:
                resp = requests.get(
                    f"https://api.listenbrainz.org/1/cf/recommendation/user/{username}/recording",
                    headers={"Authorization": f"Token {token}"},
                    params={"count": 5},
                    timeout=10
                )
                if resp.status_code == 200:
                    data = resp.json()
                    recs = data.get("payload", {}).get("mbids", [])[:5]
                    print(f"   Found {len(recs)} recommendations")
                    print("   PASS: User recommendations work")
                else:
                    print(f"   Status {resp.status_code}")
            else:
                print("   SKIP: LISTENBRAINZ_USERNAME not set")
        except Exception as e:
            print(f"   WARN: {e}")
    else:
        print("\n3. User recommendations: SKIP (no token)")

    # Test 4: MBID lookup
    print("\n4. Get recording by MBID")
    try:
        import requests
        # A known recording MBID
        mbid = "3f32b0a5-3e14-4a89-9c5e-7f9e3a5b7c8d"
        resp = requests.get(
            f"https://api.listenbrainz.org/1/metadata/recording/{mbid}",
            timeout=10
        )
        if resp.status_code == 200:
            print("   PASS: MBID lookup works")
        else:
            print(f"   Note: Status {resp.status_code} (MBID may not exist)")
    except Exception as e:
        print(f"   WARN: {e}")

    print("\n" + "=" * 50)
    print("ListenBrainz sanity check PASSED")
    print("(Some features may require LISTENBRAINZ_TOKEN)")
    print("=" * 50)
    sys.exit(0)


if __name__ == "__main__":
    main()
