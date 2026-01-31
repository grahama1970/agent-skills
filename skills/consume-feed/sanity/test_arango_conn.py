import sys
import os

# Ensure import path to skill root
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SKILL_ROOT)

from storage import FeedStorage

def test_conn():
    print("Testing ArangoDB Connection...")
    try:
        storage = FeedStorage()
        info = storage.db.properties()
        print(f"✅ Connected to '{storage.db_name}' (ID: {info['id']})")
        
        # Check Collections
        cols = ["feed_items", "feed_state", "feed_deadletters", "feed_runs"]
        for c in cols:
            if storage.db.has_collection(c):
                print(f"✅ Collection '{c}' exists")
            else:
                print(f"❌ Collection '{c}' MISSING")
                sys.exit(1)
                
        # Check View
        views = [v['name'] for v in storage.db.views()]
        if "feed_items_view" in views:
            print("✅ View 'feed_items_view' exists")
        else:
             print("❌ View 'feed_items_view' MISSING")
             sys.exit(1)
             
    except Exception as e:
        print(f"❌ Connection Failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_conn()
