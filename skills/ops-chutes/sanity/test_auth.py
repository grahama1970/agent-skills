import sys
import os
from pathlib import Path

# Add skill root to path
SKILL_ROOT = Path(__file__).parent.parent
sys.path.append(str(SKILL_ROOT))

# Mock ChutesClient for testing logic without real creds if needed, 
# but for sanity we usually want real creds if available.
from util import ChutesClient

def test_auth():
    print("Testing ChutesClient authentication...")
    if not os.environ.get("CHUTES_API_TOKEN"):
        # Allow pass if no token, scanning robots might not have it
        print("⚠️ No CHUTES_API_TOKEN found, skipping actual auth test.")
        return True
        
    try:
        client = ChutesClient()
        # Ping is usually unauthenticated or minimal auth
        # To test auth, we should try listing chutes or user info
        try:
            client.list_chutes()
            print("✅ Auth successful (list_chutes worked)")
        except Exception as e:
            print(f"❌ Auth failed: {e}")
            return False
            
        return True
    except Exception as e:
        print(f"❌ Client init failed: {e}")
        return False

if __name__ == "__main__":
    if not test_auth():
        sys.exit(1)
