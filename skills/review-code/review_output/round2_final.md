> **Review Metadata**: Round 2 | Final Diff | Provider: github | Model: gpt-5
---

```diff
Hardening: apply doctor exit, lock get_state, unify UA creation helper

diff --git a/.pi/skills/consume-feed/cli.py b/.pi/skills/consume-feed/cli.py
index 6b9f7a4..3e7f3f2 100644
--- a/.pi/skills/consume-feed/cli.py
+++ b/.pi/skills/consume-feed/cli.py
@@ -44,7 +44,7 @@ def doctor():
     try:
         storage = FeedStorage()
         console.print(f"[green]✓ ArangoDB connected ('{storage.db_name}')[/green]")
     except Exception as e:
         console.print(f"[red]✗ ArangoDB error: {e}[/red]")
-        # Don't exit, might be transient network issue
+        sys.exit(1)

diff --git a/.pi/skills/consume-feed/sources/base.py b/.pi/skills/consume-feed/sources/base.py
index 6e7f9c2..c8f3a1b 100644
--- a/.pi/skills/consume-feed/sources/base.py
+++ b/.pi/skills/consume-feed/sources/base.py
@@ -23,6 +23,12 @@ class BaseSource(ABC):
         self.logger_name = f"source.{self.key}"
         self.user_agent = user_agent or "ConsumeFeed/1.0"
 
+    def make_http_client(self):
+        """
+        Centralized factory to ensure all sources use consistent User-Agent and timeouts.
+        """
+        from ..util.http import HttpClient
+        return HttpClient(user_agent=self.user_agent)
     @abstractmethod
     def fetch(self) -> SourceStats:
         """
         Main entrypoint.
diff --git a/.pi/skills/consume-feed/sources/rss.py b/.pi/skills/consume-feed/sources/rss.py
index 7f9a1c1..2f9b7a0 100644
--- a/.pi/skills/consume-feed/sources/rss.py
+++ b/.pi/skills/consume-feed/sources/rss.py
@@ -22,7 +22,7 @@ class RSSSource(BaseSource):
         last_modified = state.get("last_modified")
         
         # 2. Fetch
-        with HttpClient(user_agent=self.user_agent) as client:
+        with self.make_http_client() as client:
             try:
                 status, text, headers = client.fetch_text(
                     self.config.rss_url,
                     etag=etag,
diff --git b/.pi/skills/consume-feed/storage.py a/.pi/skills/consume-feed/storage.py
index 1b2f3f1..5c6d8e2 100644
--- b/.pi/skills/consume-feed/storage.py
+++ a/.pi/skills/consume-feed/storage.py
@@ -100,10 +100,12 @@ class FeedStorage:
     def get_state(self, source_key: str) -> Dict[str, Any]:
         col = self.db.collection("feed_state")
-        if col.has(source_key):
-            return col.get(source_key)
-        return {"_key": source_key}
+        # Read lock for simple consistency after writes
+        with self._lock:
+            if col.has(source_key):
+                return col.get(source_key)
+            return {"_key": source_key}
 
     def save_state(self, source_key: str, state: Dict[str, Any]):
         state["_key"] = source_key
         state["updated_at"] = time.time()
         with self._lock:
             self.db.collection("feed_state").insert(state, overwrite=True, silent=True)
```


Total usage est:       1 Premium request
Total duration (API):  4.9s
Total duration (wall): 7.0s
Total code changes:    0 lines added, 0 lines removed
Usage by model:
    gpt-5                66.4k input, 785 output, 0 cache read, 0 cache write (Est. 1 Premium request)
