> **Review Metadata**: Round 1 | Final Diff | Provider: github | Model: gpt-5
---

```
Harden ops-chutes: zoneinfo, deps cleanup, robust reset, file validation, install retry

diff --git a/.pi/skills/ops-chutes/pyproject.toml b/.pi/skills/ops-chutes/pyproject.toml
index 3d9b5b1..a6f8f9c 100644
--- a/.pi/skills/ops-chutes/pyproject.toml
+++ b/.pi/skills/ops-chutes/pyproject.toml
@@ -6,9 +6,7 @@ requires-python = ">=3.11"
 dependencies = [
     "typer>=0.9.0",
     "rich>=13.0.0",
-    "httpx>=0.24.0",
-    "python-dateutil>=2.8.0",
-    "pytz>=2023.3",
+    "httpx>=0.24.0",
 ]
 
 [build-system]
diff --git a/.pi/skills/ops-chutes/SKILL.md b/.pi/skills/ops-chutes/SKILL.md
index 6b7b5f3..9f3f6a1 100644
--- a/.pi/skills/ops-chutes/SKILL.md
+++ b/.pi/skills/ops-chutes/SKILL.md
@@ -1,6 +1,6 @@
 ---
 name: ops-chutes
 description: >
-  Manage Chutes.ai resources, show configured daily limit, and monitor API health.
-  Integrates with scheduler; budget gating is best-effort unless explicit usage source is provided.
+  Manage Chutes.ai resources, show configured daily limit, and monitor API health.
+  Integrates with scheduler; budget gating is best-effort unless explicit usage source is provided and RateLimit headers may not be present.
 triggers:
   - check chutes
   - chutes usage
@@ -25,12 +25,12 @@ Manage Chutes.ai resources and provide budget visibility.
 ## Commands
 
 ```bash
 # Check model status (hot/cold/down)
 ./run.sh status
 
-# Show configured usage limit and reset time (does not guarantee exact remaining)
+# Show configured usage limit and reset time (best-effort; exact remaining not guaranteed)
 ./run.sh usage
 
 # Run sanity check (API reachability)
 ./run.sh sanity --model <model_name>
 
-# Budget gate (exit 1 if exhausted) - requires CHUTES_BUDGET_FILE or external counter
+# Budget gate (exit 1 if exhausted) - requires CHUTES_BUDGET_FILE or external counter; file must contain non-negative integer
 ./run.sh budget-check
 ```
 
diff --git a/.pi/skills/ops-chutes/util.py b/.pi/skills/ops-chutes/util.py
index 36a5f0a..b33b4ac 100644
--- a/.pi/skills/ops-chutes/util.py
+++ b/.pi/skills/ops-chutes/util.py
@@ -1,10 +1,10 @@
 import os
 import httpx
 from typing import Optional, Dict, Any, List
-from datetime import datetime, timezone
-import pytz
+from datetime import datetime, timedelta, timezone
+from zoneinfo import ZoneInfo
 
 API_BASE = "https://api.chutes.ai"
 
 class ChutesClient:
@@ -18,31 +18,43 @@ class ChutesClient:
             "User-Agent": "OpsChutes/1.0"
         }
-        self.client = httpx.Client(base_url=API_BASE, headers=self.headers, timeout=30.0)
+        # Use per-call clients to avoid leaking sockets and allow context management.
+        self.timeout = 30.0
 
     def get_chute_status(self, chute_id_or_name: str) -> Dict[str, Any]:
         """Get status of a specific chute."""
-        resp = self.client.get(f"/chutes/{chute_id_or_name}")
-        resp.raise_for_status()
-        return resp.json()
+        with httpx.Client(base_url=API_BASE, headers=self.headers, timeout=self.timeout) as client:
+            resp = client.get(f"/chutes/{chute_id_or_name}")
+            resp.raise_for_status()
+            try:
+                return resp.json()
+            except Exception as e:
+                raise RuntimeError(f"Non-JSON response for chute {chute_id_or_name}: {e}")
 
     def list_chutes(self) -> List[Dict[str, Any]]:
         """List all accessible chutes."""
-        resp = self.client.get("/chutes")
-        resp.raise_for_status()
-        return resp.json()
+        with httpx.Client(base_url=API_BASE, headers=self.headers, timeout=self.timeout) as client:
+            resp = client.get("/chutes")
+            resp.raise_for_status()
+            try:
+                return resp.json()
+            except Exception as e:
+                raise RuntimeError(f"Non-JSON response when listing chutes: {e}")
     
     def get_user_usage(self) -> Dict[str, Any]:
         """
         Attempt to get usage metrics.
         If not available, return an informative placeholder.
         """
         try:
-            resp = self.client.get("/invocations/exports/recent")
+            with httpx.Client(base_url=API_BASE, headers=self.headers, timeout=self.timeout) as client:
+                resp = client.get("/invocations/exports/recent")
             if resp.status_code == 200:
                 return resp.json()
             return {"type": "unknown", "msg": "No standard usage endpoint"}
         except Exception as e:
             return {"error": str(e)}
 
     def check_sanity(self) -> bool:
         """API reachability check via /ping."""
         try:
-            resp = self.client.get("/ping")
+            with httpx.Client(base_url=API_BASE, headers=self.headers, timeout=self.timeout) as client:
+                resp = client.get("/ping")
             return resp.status_code == 200
         except Exception:
             return False
@@ -50,13 +62,17 @@ class ChutesClient:
-    def get_day_reset_time(self) -> datetime:
-        """Return the next 7PM US/Eastern reset time as an aware datetime in UTC."""
-        est = pytz.timezone("US/Eastern")
-        now_est = datetime.now(est)
-        reset_est = now_est.replace(hour=19, minute=0, second=0, microsecond=0)
-        if now_est >= reset_est:
-            # next day at 19:00 EST
-            reset_est = est.localize(reset_est.replace(tzinfo=None))  # ensure tz-aware
-            reset_est = reset_est + pytz.timedelta(days=1)
-        reset_utc = reset_est.astimezone(pytz.UTC)
-        return reset_utc
+    def get_day_reset_time(self) -> datetime:
+        """Return the next 7PM US/Eastern reset time as an aware UTC datetime, DST-safe."""
+        eastern = ZoneInfo("America/New_York")
+        now_est = datetime.now(tz=eastern)
+        reset_est = now_est.replace(hour=19, minute=0, second=0, microsecond=0)
+        if now_est >= reset_est:
+            # move to next day at 19:00 local time; zoneinfo handles DST transitions
+            reset_est = (reset_est + timedelta(days=1)).replace(tzinfo=eastern)
+        return reset_est.astimezone(timezone.utc)
 
-    def close(self):
-        self.client.close()
+    def close(self):
+        # No persistent client to close; method kept for API compatibility.
+        return
diff --git a/.pi/skills/ops-chutes/manager.py b/.pi/skills/ops-chutes/manager.py
index 8b0b8f5..5e9d6a2 100644
--- a/.pi/skills/ops-chutes/manager.py
+++ b/.pi/skills/ops-chutes/manager.py
@@ -1,15 +1,14 @@
 import typer
 import sys
 import os
 from typing import Optional
 from rich.console import Console
 from rich.table import Table
 from util import ChutesClient
 from datetime import datetime
-import pytz
 
 app = typer.Typer(help="Ops Chutes Manager")
 console = Console()
 
 DAILY_LIMIT = int(os.environ.get("CHUTES_DAILY_LIMIT", 5000))
 BUDGET_FILE = os.environ.get("CHUTES_BUDGET_FILE")
@@ -33,7 +32,7 @@ def status():
         for c in chutes:
             c_id = str(c.get("id", "??"))
             name = str(c.get("name", "??"))
             status = str(c.get("status", "unknown"))
-            style = "green" if status.lower() in {"running", "ready", "hot"} else "red"
+            style = "green" if status.lower() in {"running", "ready", "hot"} else "red"
             table.add_row(c_id, name, f"[{style}]{status}[/{style}]")
             
         console.print(table)
     except Exception as e:
@@ -50,15 +49,22 @@ def usage():
     """Show configured limit, reset time, and any rate-limit headers."""
     try:
         client = ChutesClient()
         reset_time = client.get_day_reset_time()
 
         console.print(f"[bold]Daily Limit:[/bold] {DAILY_LIMIT}")
         console.print(f"[bold]Reset Time (UTC):[/bold] {reset_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
         # Try to surface current rate-limit headers via a lightweight call
         try:
-            resp = client.client.get("/ping")
+            import httpx
+            with httpx.Client(base_url="https://api.chutes.ai", headers=client.headers, timeout=client.timeout) as hc:
+                resp = hc.get("/ping")
             remaining = resp.headers.get("X-RateLimit-Remaining") or resp.headers.get("RateLimit-Remaining")
             limit = resp.headers.get("X-RateLimit-Limit") or resp.headers.get("RateLimit-Limit")
             if remaining or limit:
                 console.print(f"[bold]RateLimit:[/bold] remaining={remaining}, limit={limit}")
             else:
                 console.print("[dim]No rate-limit headers present; exact remaining unknown.[/dim]")
         except Exception:
             console.print("[dim]Unable to read rate-limit headers from /ping.[/dim]")
@@ -70,17 +76,25 @@ def budget_check():
     Uses CHUTES_BUDGET_FILE if provided (expects integer count).
     """
     try:
         usage = 0
         if BUDGET_FILE and os.path.isfile(BUDGET_FILE):
             try:
                 with open(BUDGET_FILE, "r") as f:
-                    usage = int(f.read().strip() or "0")
+                    raw = f.read().strip()
+                    usage = int(raw or "0")
+                    if usage < 0:
+                        console.print("[yellow]Warning: budget file contains negative value; treating as 0[/yellow]")
+                        usage = 0
+                    # Guard against absurdly large values
+                    if usage > 10_000_000:
+                        console.print("[yellow]Warning: budget file value unusually large; capping[/yellow]")
+                        usage = 10_000_000
             except Exception as e:
                 console.print(f"[yellow]Warning: failed to read budget file: {e}[/yellow]")
         if usage >= DAILY_LIMIT:
             console.print(f"[red]Budget Exhausted ({usage}/{DAILY_LIMIT})[/red]")
             sys.exit(1)
         console.print(f"[green]Budget OK ({usage}/{DAILY_LIMIT})[/green]")
         sys.exit(0)
     except Exception as e:
         console.print(f"[red]Error: {e}[/red]")
         sys.exit(1)
diff --git a/.pi/skills/ops-chutes/run.sh b/.pi/skills/ops-chutes/run.sh
index 6c9a2f7..0b9f7ea 100755
--- a/.pi/skills/ops-chutes/run.sh
+++ b/.pi/skills/ops-chutes/run.sh
@@ -1,24 +1,36 @@
 #!/bin/bash
 # Wrapper to run ops-chutes commands with uv (fallback to python if uv missing)
 
 set -euo pipefail
 
 # Determine skill directory
 SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
 cd "$SKILL_DIR"
 
 has_uv() { command -v uv >/dev/null 2>&1; }
 
 # Ensure dependencies are installed
 if [ ! -d ".venv" ]; then
     if has_uv; then
         uv venv && uv pip install .
     else
-        python3 -m venv .venv && . .venv/bin/activate && pip install .
+        python3 -m venv .venv && . .venv/bin/activate
+        # Basic retry for network flakiness
+        max_tries=3
+        try=1
+        while true; do
+          if python -m pip install .; then
+            break
+          fi
+          if [ "$try" -ge "$max_tries" ]; then
+            echo "ERROR: Failed to install dependencies after $max_tries attempts" >&2
+            exit 1
+          fi
+          try=$((try+1))
+          sleep 2
+        done
     fi
 fi
 
 # Run the manager
 if has_uv; then
     uv run manager.py "$@"
 else
     . .venv/bin/activate && python3 manager.py "$@"
 fi
```


Total usage est:       1 Premium request
Total duration (API):  17.2s
Total duration (wall): 19.4s
Total code changes:    0 lines added, 0 lines removed
Usage by model:
    gpt-5                47.4k input, 3.2k output, 0 cache read, 0 cache write (Est. 1 Premium request)
