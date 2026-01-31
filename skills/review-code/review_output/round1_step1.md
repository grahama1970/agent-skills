> **Review Metadata**: Round 1 | Step 1 | Provider: github | Model: gpt-5
---

✓ Read .pi/skills/ops-chutes/SKILL.md (53 lines)

✓ Read .pi/skills/ops-chutes/pyproject.toml (33 lines)

✓ Read .pi/skills/ops-chutes/manager.py (105 lines)

✓ Read .pi/skills/ops-chutes/util.py (83 lines)

✓ Read .pi/skills/ops-chutes/run.sh (20 lines)

✓ Read .pi/skills/ops-chutes/sanity/test_auth.py (43 lines)

✓ Read .pi/skills/ops-chutes/pyproject.toml (33 lines)

✓ Read .pi/skills/ops-chutes/sanity/test_auth.py (43 lines)

✓ Edit .pi/skills/ops-chutes/util.py (+18 -28)
   ╭──────────────────────────────────────────────────────────────────────────────────────────────╮
   │  1     import os                                                                             │
   │  2     import httpx                                                                          │
   │  3     from typing import Optional, Dict, Any, List                                          │
   │  4  -  from datetime import datetime, time, timezone                                         │
   │  4  +  from datetime import datetime, timezone                                               │
   │  5     import pytz                                                                           │
   │  6                                                                                           │
   │  7     API_BASE = "https://api.chutes.ai"                                                    │
   │ ──────────────────────────────────────────────────────────────────────────────────────────── │
   │ 21                                                                                           │
   │ 22         def get_chute_status(self, chute_id_or_name: str) -> Dict[str, Any]:              │
   │ 23             """Get status of a specific chute."""                                         │
   │ 24  -          # Note: API might use different path structure, assuming standard             │
   │        /chutes/{id}                                                                          │
   │ 24             resp = self.client.get(f"/chutes/{chute_id_or_name}")                         │
   │ 25             resp.raise_for_status()                                                       │
   │ 26             return resp.json()                                                            │
   │ 27                                                                                           │
   │ 28         def list_chutes(self) -> List[Dict[str, Any]]:                                    │
   │ 29             """List all accessible chutes."""                                             │
   │ 31  -          resp = self.client.get("/chutes/")                                            │
   │ 30  +          resp = self.client.get("/chutes")                                             │
   │ 31             resp.raise_for_status()                                                       │
   │ 32             return resp.json()                                                            │
   │ 33                                                                                           │
   │ 34         def get_user_usage(self) -> Dict[str, Any]:                                       │
   │ 35             """                                                                           │
   │ 37  -          Attempt to get usage metrics.                                                 │
   │ 38  -          Since a direct 'daily remaining' endpoint might not exist,                    │
   │ 39  -          we look for invocation counts if available.                                   │
   │ 36  +          Attempt to get usage metrics.                                                 │
   │ 37  +          If not available, return an informative placeholder.                          │
   │ 38             """                                                                           │
   │ 39             try:                                                                          │
   │ 40                 # Try specific export endpoint if available from docs or fallback to user │
   │         info                                                                                 │
   │ 37             we look for invocation counts if available.                                   │
   │ 38             """                                                                           │
   │ 39             try:                                                                          │
   │ 42  -              # Try specific export endpoint if available from docs or fallback to user │
   │         info                                                                                 │
   │ 43  -              # Based on research: GET /invocations/exports/recent might exist          │
   │ 44  -              resp = self.client.get("/invocations/exports/recent")                     │
   │ 40  +              resp = self.client.get("/invocations/exports/recent")                     │
   │ 41                 if resp.status_code == 200:                                               │
   │ 42                     return resp.json()                                                    │
   │ 47  -              else:                                                                     │
   │ 48  -                  return {"type": "unknown", "msg": "Usage endpoint not standard"}      │
   │ 43  +              return {"type": "unknown", "msg": "No standard usage endpoint"}           │
   │ 44             except Exception as e:                                                        │
   │ 45                 return {"error": str(e)}                                                  │
   │ 46                                                                                           │
   │ 44             except Exception as e:                                                        │
   │ 45                 return {"error": str(e)}                                                  │
   │ 46                                                                                           │
   │ 52  -      def check_sanity(self, image: str = "chutes/generic-inference", payload: Dict =   │
   │        None) -> bool:                                                                        │
   │ 53  -          """Run a simple sanity inference."""                                          │
   │ 54  -          # Generic health check usually involves hitting a known model                 │
   │ 55  -          # or the /ping endpoint if we just want API health                            │
   │ 47  +      def check_sanity(self) -> bool:                                                   │
   │ 48  +          """API reachability check via /ping."""                                       │
   │ 49             try:                                                                          │
   │ 50                 resp = self.client.get("/ping")                                           │
   │ 51                 return resp.status_code == 200                                            │
   │ ──────────────────────────────────────────────────────────────────────────────────────────── │
   │ 59  -          except:                                                                       │
   │ 52  +          except Exception                                                              │
   │ 53                 return False                                                              │
   │ 54                                                                                           │
   │ 55         def get_day_reset_time(self) -> datetime:                                         │
   │ 53                 return False                                                              │
   │ 54                                                                                           │
   │ 55         def get_day_reset_time(self) -> datetime:                                         │
   │ ──────────────────────────────────────────────────────────────────────────────────────────── │
   │ 63  -          """Get the next 7PM EST reset time in UTC."""                                 │
   │ 64  -          est = pytz.timezone('US/Eastern')                                             │
   │ 56  +          """Return the next 7PM US/Eastern reset time as an aware datetime in UTC."""  │
   │ 57  +          est = pytz.timezone("US/Eastern")                                             │
   │ 58             now_est = datetime.now(est)                                                   │
   │ ──────────────────────────────────────────────────────────────────────────────────────────── │
   │ 66  -                                                                                        │
   │ 67  -          # Reset is 7PM EST (19:00)                                                    │
   │ 68  -          reset_today = now_est.replace(hour=19, minute=0, second=0, microsecond=0)     │
   │ 69  -                                                                                        │
   │ 70  -          if now_est >= reset_today:                                                    │
   │ 71  -               # If strictly after 19:00, reset is tomorrow                             │
   │ 72  -               # Note logic: if budget exhausted, wait until THIS time                  │
   │ 73  -               pass                                                                     │
   │ 74  -                                                                                        │
   │ 75  -          return reset_today # Returns aware datetime                                   │
   │ 59  +          reset_est = now_est.replace(hour=19, minute=0, second=0, microsecond=0)       │
   │ 60  +          if now_est >= reset_est:                                                      │
   │ 61  +              reset_est = reset_est + est.utcoffset(now_est) * 0 + (reset_est -         │
   │        reset_est)  # no-op to keep tzinfo                                                    │
   │ 62  +              reset_est = reset_est + pytz.timedelta(days=1)                            │
   │ 63  +              reset_est = est.localize(reset_est.replace(tzinfo=None))                  │
   │ 64  +          reset_utc = reset_est.astimezone(pytz.UTC)                                    │
   │ 65  +          return reset_utc                                                              │
   │ 66                                                                                           │
   │ 67         def close(self):                                                                  │
   │ 68             self.client.close()                                                           │
   ╰──────────────────────────────────────────────────────────────────────────────────────────────╯

✓ Edit .pi/skills/ops-chutes/manager.py (+28 -31)
   ╭──────────────────────────────────────────────────────────────────────────────────────────────╮
   │ 12     console = Console()                                                                   │
   │ 13                                                                                           │
   │ 14     DAILY_LIMIT = int(os.environ.get("CHUTES_DAILY_LIMIT", 5000))                         │
   │ 15  +  BUDGET_FILE = os.environ.get("CHUTES_BUDGET_FILE")                                    │
   │ 16                                                                                           │
   │ 17     @app.command()                                                                        │
   │ 18     def status():                                                                         │
   │ 20         try:                                                                              │
   │ 21             client = ChutesClient()                                                       │
   │ 22             chutes = client.list_chutes()                                                 │
   │ 22  -                                                                                        │
   │ 23  -          table = Table("ID", "Name", "Status", "Image"                                 │
   │ 23  +          table = Table("ID", "Name", "Status")                                         │
   │ 24             for c in chutes:                                                              │
   │ 25  -              # Adjust fields based on actual API response structure                    │
   │ 26  -              c_id = c.get("id", "??")                                                  │
   │ 27  -              name = c.get("name", "??")                                                │
   │ 28  -              status = c.get("status", "unknown")                                       │
   │ 29  -              image = c.get("image", "")                                                │
   │ 30  -                                                                                        │
   │ 31  -              style = "green" if status == "running" else "red"                         │
   │ 32  -              table.add_row(c_id, name, f"[{style}]{status}[/{style}]", image           │
   │ 33  -                                                                                        │
   │ 25  +              c_id = str(c.get("id", "??"))                                             │
   │ 26  +              name = str(c.get("name", "??"))                                           │
   │ 27  +              status = str(c.get("status", "unknown"))                                  │
   │ 28  +              style = "green" if status.lower() in {"running", "ready", "hot"} else     │
   │        "red"                                                                                 │
   │ 29  +              table.add_row(c_id, name, f"[{style}]{status}[/{style}]")                 │
   │ 30             console.print(table)                                                          │
   │ 31         except Exception as e:                                                            │
   │ 32             console.print(f"[red]Failed to list chutes: {e}[/red]")                       │
   │ 34                                                                                           │
   │ 35     @app.command()                                                                        │
   │ 36     def usage():                                                                          │
   │ 41  -      """Check API usage and estimated budget."""                                       │
   │ 37  +      """Show configured limit, reset time, and any rate-limit headers."""              │
   │ 38         try:                                                                              │
   │ 39             client = ChutesClient()                                                       │
   │ 44  -          # Note: Since there is no direct quota endpoint, we infer or just show limits │
   │ 40             reset_time = client.get_day_reset_time()                                      │
   │ 41                                                                                           │
   │ 42             console.print(f"[bold]Daily Limit:[/bold] {DAILY_LIMIT}")                     │
   │ 38             client = ChutesClient()                                                       │
   │ 39             # Note: Since there is no direct quota endpoint, we infer or just show limits │
   │ 40             reset_time = client.get_day_reset_time()                                      │
   │ 46  -                                                                                        │
   │ 41             console.print(f"[bold]Daily Limit:[/bold] {DAILY_LIMIT}")                     │
   │ ──────────────────────────────────────────────────────────────────────────────────────────── │
   │ 48  -          console.print(f"[bold]Reset Time:[/bold] {reset_time.strftime('%Y-%m-%d       │
   │        %H:%M:%S %Z')}")                                                                      │
   │ 49  -                                                                                        │
   │ 50  -          # In a real implementation, we would fetch actual usage here.                 │
   │ 51  -          # For now, we report the configuration.                                       │
   │ 52  -          console.print("[dim]Note: Exact remaining calls requires accumulation from    │
   │        RateLimit headers.[/dim]")                                                            │
   │ 53  -                                                                                        │
   │ 42  +          console.print(f"[bold]Reset Time (UTC):[/bold] {reset_time.strftime('%Y-%m-%d │
   │         %H:%M:%S %Z')}")                                                                     │
   │ 43  +          # Try to surface current rate-limit headers via a lightweight call            │
   │ 44  +          try:                                                                          │
   │ 45  +              resp = client.client.get("/ping")                                         │
   │ 46  +              remaining = resp.headers.get("X-RateLimit-Remaining") or                  │
   │        resp.headers.get("RateLimit-Remaining")                                               │
   │ 47  +              limit = resp.headers.get("X-RateLimit-Limit") or                          │
   │        resp.headers.get("RateLimit-Limit")                                                   │
   │ 48  +              if remaining or limit:                                                    │
   │ 49  +                  console.print(f"[bold]RateLimit:[/bold] remaining={remaining},        │
   │        limit={limit}")                                                                       │
   │ 50  +              else:                                                                     │
   │ 51  +                  console.print("[dim]No rate-limit headers present; exact remaining    │
   │        unknown.[/dim]")                                                                      │
   │ 52  +          except Exception:                                                             │
   │ 53  +              console.print("[dim]Unable to read rate-limit headers from /ping.[/dim]") │
   │ 54         except Exception as e:                                                            │
   │ 55             console.print(f"[red]Error checking usage: {e}[/red]")                        │
   │ 56             sys.exit(1)                                                                   │
   │ 60         """                                                                               │
   │ 61         Exit code 0 if budget OK.                                                         │
   │ 62         Exit code 1 if budget exhausted.                                                  │
   │ 63  -      Used by scheduler.                                                                │
   │ 63  +      Uses CHUTES_BUDGET_FILE if provided (expects integer count).                      │
   │ 64         """                                                                               │
   │ 65         try:                                                                              │
   │ 66  -          # TODO: Implement persistent storage for call counting to make this real.     │
   │ 67  -          # For now, we assume budget is always OK unless we hit a 429 externally.      │
   │ 68  -          # If we had a shared counter (e.g. in Memory or a local file), we check it    │
   │        here.                                                                                 │
   │ 69  -                                                                                        │
   │ 70  -          # Placeholder logic: Check a local file or env var if we were tracking it     │
   │ 71  -          # usage = get_stored_usage()                                                  │
   │ 72  -          usage = 0                                                                     │
   │ 73  -                                                                                        │
   │ 66  +          usage = 0                                                                     │
   │ 67  +          if BUDGET_FILE and os.path.isfile(BUDGET_FILE):                               │
   │ 68  +              try:                                                                      │
   │ 69  +                  with open(BUDGET_FILE, "r") as f:                                     │
   │ 70  +                      usage = int(f.read().strip() or "0")                              │
   │ 71  +              except Exception as e:                                                    │
   │ 72  +                  console.print(f"[yellow]Warning: failed to read budget file:          │
   │        {e}[/yellow]")                                                                        │
   │ 73             if usage >= DAILY_LIMIT:                                                      │
   │ 74                 console.print(f"[red]Budget Exhausted ({usage}/{DAILY_LIMIT})[/red]")     │
   │ 75                 sys.exit(1)                                                               │
   │ 73             if usage >= DAILY_LIMIT:                                                      │
   │ 74                 console.print(f"[red]Budget Exhausted ({usage}/{DAILY_LIMIT})[/red]")     │
   │ 75                 sys.exit(1)                                                               │
   │ 77  -                                                                                        │
   │ 76             console.print(f"[green]Budget OK ({usage}/{DAILY_LIMIT})[/green]")            │
   │ 77             sys.exit(0)                                                                   │
   │ 78         except Exception as e:                                                            │
   │ ──────────────────────────────────────────────────────────────────────────────────────────── │
   │ 89             else:                                                                         │
   │ 90                 console.print("[red]❌ Chutes API ping failed[/red]")                     │
   │ 91                 sys.exit(1)                                                               │
   │ 94  -                                                                                        │
   │ 92         except Exception as e:                                                            │
   │ 93             console.print(f"[red]Sanity check crashed: {e}[/red]")                        │
   │ 94             sys.exit(1)                                                                   │
   ╰──────────────────────────────────────────────────────────────────────────────────────────────╯

✓ Edit .pi/skills/ops-chutes/run.sh (+15 -4)
   ╭──────────────────────────────────────────────────────────────────────────────────────────────╮
   │  1     #!/bin/bash                                                                           │
   │  2  -  # Wrapper to run ops-chutes commands with uv                                          │
   │  2  +  # Wrapper to run ops-chutes commands with uv (fallback to python if uv missing)       │
   │  3  +                                                                                        │
   │  4  +  set -euo pipefail                                                                     │
   │  5                                                                                           │
   │  6     # Determine skill directory                                                           │
   │  7     SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"                             │
   │  8     cd "$SKILL_DIR"                                                                       │
   │  9  +                                                                                        │
   │ 10  +  has_uv() { command -v uv >/dev/null 2>&1; }                                           │
   │ 11                                                                                           │
   │ 12     # Ensure dependencies are installed                                                   │
   │ 13     if [ ! -d ".venv" ]; then                                                             │
   │ 11                                                                                           │
   │ 12     # Ensure dependencies are installed                                                   │
   │ 13     if [ ! -d ".venv" ]; then                                                             │
   │ 10  -      uv venv                                                                           │
   │ 11  -      uv pip install .                                                                  │
   │ 14  +      if has_uv; then                                                                   │
   │ 15  +          uv venv && uv pip install .                                                   │
   │ 16  +      else                                                                              │
   │ 17  +          python3 -m venv .venv && . .venv/bin/activate && pip install .                │
   │ 18  +      fi                                                                                │
   │ 19     fi                                                                                    │
   │ 20                                                                                           │
   │ 21     # Run the manager                                                                     │
   │ 15  -  uv run manager.py "$@"                                                                │
   │ ──────────────────────────────────────────────────────────────────────────────────────────── │
   │ 22  +  if has_uv; then                                                                       │
   │ 23  +      uv run manager.py "$@"                                                            │
   │ 24  +  else                                                                                  │
   │ 25  +      . .venv/bin/activate && python3 manager.py "$@"                                   │
   │ 26  +  fi                                                                                    │
   ╰──────────────────────────────────────────────────────────────────────────────────────────────╯

✓ Edit .pi/skills/ops-chutes/SKILL.md (+12 -11)
   ╭──────────────────────────────────────────────────────────────────────────────────────────────╮
   │  1     ---                                                                                   │
   │  2     name: ops-chutes                                                                      │
   │  3     description: >                                                                        │
   │  4  -    Manage Chutes.ai resources, track 5000/day API limit, and monitor model health.     │
   │  5  -    Integrates with scheduler to pause operations when budget is exhausted.             │
   │  4  +    Manage Chutes.ai resources, show configured daily limit, and monitor API health.    │
   │  5  +    Integrates with scheduler; budget gating is best-effort unless explicit usage       │
   │        source is provided.                                                                   │
   │  6     triggers:                                                                             │
   │  7       - check chutes                                                                      │
   │  8       - chutes usage                                                                      │
   │ 11       - check chutes health                                                               │
   │ 12       - chutes api check                                                                  │
   │ 13     metadata:                                                                             │
   │ 14  -    short-description: Chutes.ai API management and budget tracking                     │
   │ 14  +    short-description: Chutes.ai API management and budget visibility                   │
   │ 15     ---                                                                                   │
   │ 16                                                                                           │
   │ 17     # Ops Chutes Skill                                                                    │
   │ 18                                                                                           │
   │ 19  -  Manage Chutes.ai resources and enforce budget limits.                                 │
   │ 19  +  Manage Chutes.ai resources and provide budget visibility.                             │
   │ 20                                                                                           │
   │ 21     ## Triggers                                                                           │
   │ 22                                                                                           │
   │ ──────────────────────────────────────────────────────────────────────────────────────────── │
   │ 30     # Check model status (hot/cold/down)                                                  │
   │ 31     ./run.sh status                                                                       │
   │ 32                                                                                           │
   │ 33  -  # Check usage against 5000/day limit                                                  │
   │ 33  +  # Show configured usage limit and reset time (does not guarantee exact remaining)     │
   │ 34     ./run.sh usage                                                                        │
   │ 35                                                                                           │
   │ 36  -  # Run sanity check (inference)                                                        │
   │ 36  +  # Run sanity check (API reachability)                                                 │
   │ 37     ./run.sh sanity --model <model_name>                                                  │
   │ 38                                                                                           │
   │ 39     # Check budget (exit code 1 if exhausted) - for scheduler                             │
   │ 36     # Run sanity check (inference)                                                        │
   │ 37     ./run.sh sanity --model <model_name>                                                  │
   │ 38                                                                                           │
   │ 39  -  # Check budget (exit code 1 if exhausted) - for scheduler                             │
   │ 39  +  # Budget gate (exit 1 if exhausted) - requires CHUTES_BUDGET_FILE or external counter │
   │ 40     ./run.sh budget-check                                                                 │
   │ 41     ```                                                                                   │
   │ 42                                                                                           │
   │ 43     ## Environment Variables                                                              │
   │ 44                                                                                           │
   │ 45  -  | Variable             | Description                         |                        │
   │ 46  -  | -------------------- | ----------------------------------- |                        │
   │ 47  -  | `CHUTES_API_TOKEN`   | API Token for authentication        |                        │
   │ 48  -  | `CHUTES_DAILY_LIMIT` | Daily request limit (default: 5000) |                        │
   │ 45  +  | Variable               | Description                                                │
   │        |                                                                                     │
   │ 46  +  | ---------------------- | ---------------------------------------------------------  │
   │        |                                                                                     │
   │ 47  +  | `CHUTES_API_TOKEN`     | API Token for authentication                               │
   │        |                                                                                     │
   │ 48  +  | `CHUTES_DAILY_LIMIT`   | Daily request limit (default: 5000)                        │
   │        |                                                                                     │
   │ 49  +  | `CHUTES_BUDGET_FILE`   | Optional path to integer counter used by `budget-check`    │
   │        |                                                                                     │
   ╰──────────────────────────────────────────────────────────────────────────────────────────────╯

Clarifying questions:
- Should budget enforcement rely on a shared counter file (CHUTES_BUDGET_FILE), a centralized store, or RateLimit headers, and is 7PM US/Eastern the definitive daily reset?
- What is the authoritative Chutes API path structure for listing chutes and health (e.g., /chutes vs /chutes/, /ping), and which fields map to status semantics (“running”, “hot”, etc.)?
- Is uv guaranteed to be available in deployment environments, or should Python venv fallback be the default?

```
*** Begin Patch
*** Update File: .pi/skills/ops-chutes/SKILL.md
@@
-name: ops-chutes
-description: >
-  Manage Chutes.ai resources, track 5000/day API limit, and monitor model health.
-  Integrates with scheduler to pause operations when budget is exhausted.
+name: ops-chutes
+description: >
+  Manage Chutes.ai resources, show configured daily limit, and monitor API health.
+  Integrates with scheduler; budget gating is best-effort unless explicit usage source is provided.
 triggers:
   - check chutes
   - chutes usage
   - chutes budget
   - chutes status
   - check chutes health
   - chutes api check
 metadata:
-  short-description: Chutes.ai API management and budget tracking
+  short-description: Chutes.ai API management and budget visibility
 ---
 
 # Ops Chutes Skill
 
-Manage Chutes.ai resources and enforce budget limits.
+Manage Chutes.ai resources and provide budget visibility.
 
 ## Triggers
 
 - "Check chutes status" -> `status`
 - "How much chutes budget left?" -> `usage`
 - "Is chutes working?" -> `sanity`
 
 ## Commands
 
 ```bash
 # Check model status (hot/cold/down)
 ./run.sh status
 
-# Check usage against 5000/day limit
+# Show configured usage limit and reset time (does not guarantee exact remaining)
 ./run.sh usage
 
-# Run sanity check (inference)
+# Run sanity check (API reachability)
 ./run.sh sanity --model <model_name>
 
-# Check budget (exit code 1 if exhausted) - for scheduler
+# Budget gate (exit 1 if exhausted) - requires CHUTES_BUDGET_FILE or external counter
 ./run.sh budget-check
 ```
 
 ## Environment Variables
 
-| Variable             | Description                         |
-| -------------------- | ----------------------------------- |
-| `CHUTES_API_TOKEN`   | API Token for authentication        |
-| `CHUTES_DAILY_LIMIT` | Daily request limit (default: 5000) |
+| Variable               | Description                                               |
+| ---------------------- | --------------------------------------------------------- |
+| `CHUTES_API_TOKEN`     | API Token for authentication                              |
+| `CHUTES_DAILY_LIMIT`   | Daily request limit (default: 5000)                       |
+| `CHUTES_BUDGET_FILE`   | Optional path to integer counter used by `budget-check`   |
*** End Patch
```

```
*** Begin Patch
*** Update File: .pi/skills/ops-chutes/util.py
@@
-import os
-import httpx
-from typing import Optional, Dict, Any, List
-from datetime import datetime, time, timezone
-import pytz
+import os
+import httpx
+from typing import Optional, Dict, Any, List
+from datetime import datetime, timezone
+import pytz
 
 API_BASE = "https://api.chutes.ai"
 
 class ChutesClient:
     def __init__(self, token: Optional[str] = None):
         self.token = token or os.environ.get("CHUTES_API_TOKEN")
         if not self.token:
             raise ValueError("CHUTES_API_TOKEN not found in environment")
         
         self.headers = {
             "Authorization": f"Bearer {self.token}",
             "Accept": "application/json",
             "User-Agent": "OpsChutes/1.0"
         }
         self.client = httpx.Client(base_url=API_BASE, headers=self.headers, timeout=30.0)
 
     def get_chute_status(self, chute_id_or_name: str) -> Dict[str, Any]:
         """Get status of a specific chute."""
-        # Note: API might use different path structure, assuming standard /chutes/{id}
         resp = self.client.get(f"/chutes/{chute_id_or_name}")
         resp.raise_for_status()
         return resp.json()
 
     def list_chutes(self) -> List[Dict[str, Any]]:
         """List all accessible chutes."""
-        resp = self.client.get("/chutes/")
+        resp = self.client.get("/chutes")
         resp.raise_for_status()
         return resp.json()
     
     def get_user_usage(self) -> Dict[str, Any]:
         """
-        Attempt to get usage metrics. 
-        Since a direct 'daily remaining' endpoint might not exist, 
-        we look for invocation counts if available.
+        Attempt to get usage metrics.
+        If not available, return an informative placeholder.
         """
         try:
-            # Try specific export endpoint if available from docs or fallback to user info
-            # Based on research: GET /invocations/exports/recent might exist
-            resp = self.client.get("/invocations/exports/recent") 
-            if resp.status_code == 200:
-                return resp.json()
-            else:
-                return {"type": "unknown", "msg": "Usage endpoint not standard"}
+            resp = self.client.get("/invocations/exports/recent")
+            if resp.status_code == 200:
+                return resp.json()
+            return {"type": "unknown", "msg": "No standard usage endpoint"}
         except Exception as e:
             return {"error": str(e)}
 
-    def check_sanity(self, image: str = "chutes/generic-inference", payload: Dict = None) -> bool:
-        """Run a simple sanity inference."""
-        # Generic health check usually involves hitting a known model
-        # or the /ping endpoint if we just want API health
-        try:
-            resp = self.client.get("/ping")
-            return resp.status_code == 200
-        except:
-            return False
+    def check_sanity(self) -> bool:
+        """API reachability check via /ping."""
+        try:
+            resp = self.client.get("/ping")
+            return resp.status_code == 200
+        except Exception:
+            return False
 
     def get_day_reset_time(self) -> datetime:
-        """Get the next 7PM EST reset time in UTC."""
-        est = pytz.timezone('US/Eastern')
-        now_est = datetime.now(est)
-        
-        # Reset is 7PM EST (19:00)
-        reset_today = now_est.replace(hour=19, minute=0, second=0, microsecond=0)
-        
-        if now_est >= reset_today:
-             # If strictly after 19:00, reset is tomorrow
-             # Note logic: if budget exhausted, wait until THIS time
-             pass 
-        
-        return reset_today # Returns aware datetime
+        """Return the next 7PM US/Eastern reset time as an aware datetime in UTC."""
+        est = pytz.timezone("US/Eastern")
+        now_est = datetime.now(est)
+        reset_est = now_est.replace(hour=19, minute=0, second=0, microsecond=0)
+        if now_est >= reset_est:
+            # next day at 19:00 EST
+            reset_est = est.localize(reset_est.replace(tzinfo=None))  # ensure tz-aware
+            reset_est = reset_est + pytz.timedelta(days=1)
+        reset_utc = reset_est.astimezone(pytz.UTC)
+        return reset_utc
 
     def close(self):
         self.client.close()
*** End Patch
```

```
*** Begin Patch
*** Update File: .pi/skills/ops-chutes/manager.py
@@
-import typer
-import sys
-import os
-from typing import Optional
-from rich.console import Console
-from rich.table import Table
-from util import ChutesClient
-from datetime import datetime
-import pytz
+import typer
+import sys
+import os
+from typing import Optional
+from rich.console import Console
+from rich.table import Table
+from util import ChutesClient
+from datetime import datetime
+import pytz
 
 app = typer.Typer(help="Ops Chutes Manager")
 console = Console()
 
 DAILY_LIMIT = int(os.environ.get("CHUTES_DAILY_LIMIT", 5000))
+BUDGET_FILE = os.environ.get("CHUTES_BUDGET_FILE")
 
 @app.command()
 def status():
     """List status of accessible chutes."""
     try:
         client = ChutesClient()
         chutes = client.list_chutes()
-        
-        table = Table("ID", "Name", "Status", "Image")
+        table = Table("ID", "Name", "Status")
         for c in chutes:
-            # Adjust fields based on actual API response structure
-            c_id = c.get("id", "??")
-            name = c.get("name", "??") 
-            status = c.get("status", "unknown")
-            image = c.get("image", "")
-            
-            style = "green" if status == "running" else "red"
-            table.add_row(c_id, name, f"[{style}]{status}[/{style}]", image)
+            c_id = str(c.get("id", "??"))
+            name = str(c.get("name", "??"))
+            status = str(c.get("status", "unknown"))
+            style = "green" if status.lower() in {"running", "ready", "hot"} else "red"
+            table.add_row(c_id, name, f"[{style}]{status}[/{style}]")
             
         console.print(table)
     except Exception as e:
         console.print(f"[red]Failed to list chutes: {e}[/red]")
         sys.exit(1)
 
 @app.command()
 def usage():
-    """Check API usage and estimated budget."""
+    """Show configured limit, reset time, and any rate-limit headers."""
     try:
         client = ChutesClient()
-        # Note: Since there is no direct quota endpoint, we infer or just show limits
         reset_time = client.get_day_reset_time()
-        
         console.print(f"[bold]Daily Limit:[/bold] {DAILY_LIMIT}")
-        console.print(f"[bold]Reset Time:[/bold] {reset_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
-        
-        # In a real implementation, we would fetch actual usage here.
-        # For now, we report the configuration.
-        console.print("[dim]Note: Exact remaining calls requires accumulation from RateLimit headers.[/dim]")
-        
+        console.print(f"[bold]Reset Time (UTC):[/bold] {reset_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
+        # Try to surface current rate-limit headers via a lightweight call
+        try:
+            resp = client.client.get("/ping")
+            remaining = resp.headers.get("X-RateLimit-Remaining") or resp.headers.get("RateLimit-Remaining")
+            limit = resp.headers.get("X-RateLimit-Limit") or resp.headers.get("RateLimit-Limit")
+            if remaining or limit:
+                console.print(f"[bold]RateLimit:[/bold] remaining={remaining}, limit={limit}")
+            else:
+                console.print("[dim]No rate-limit headers present; exact remaining unknown.[/dim]")
+        except Exception:
+            console.print("[dim]Unable to read rate-limit headers from /ping.[/dim]")
     except Exception as e:
         console.print(f"[red]Error checking usage: {e}[/red]")
         sys.exit(1)
 
 @app.command("budget-check")
 def budget_check():
     """
     Exit code 0 if budget OK.
     Exit code 1 if budget exhausted.
-    Used by scheduler.
+    Uses CHUTES_BUDGET_FILE if provided (expects integer count).
     """
     try:
-        # TODO: Implement persistent storage for call counting to make this real.
-        # For now, we assume budget is always OK unless we hit a 429 externally.
-        # If we had a shared counter (e.g. in Memory or a local file), we check it here.
-        
-        # Placeholder logic: Check a local file or env var if we were tracking it
-        # usage = get_stored_usage()
-        usage = 0 
-        
+        usage = 0
+        if BUDGET_FILE and os.path.isfile(BUDGET_FILE):
+            try:
+                with open(BUDGET_FILE, "r") as f:
+                    usage = int(f.read().strip() or "0")
+            except Exception as e:
+                console.print(f"[yellow]Warning: failed to read budget file: {e}[/yellow]")
         if usage >= DAILY_LIMIT:
             console.print(f"[red]Budget Exhausted ({usage}/{DAILY_LIMIT})[/red]")
             sys.exit(1)
             
         console.print(f"[green]Budget OK ({usage}/{DAILY_LIMIT})[/green]")
         sys.exit(0)
     except Exception as e:
         console.print(f"[red]Error: {e}[/red]")
         sys.exit(1)
 
 @app.command()
 def sanity(model: str = typer.Option(None, help="Specific model/chute to test")):
     """Run a sanity check/ping."""
     try:
         client = ChutesClient()
         if client.check_sanity():
             console.print("[green]✅ Chutes API is reachable[/green]")
         else:
             console.print("[red]❌ Chutes API ping failed[/red]")
             sys.exit(1)
             
     except Exception as e:
         console.print(f"[red]Sanity check crashed: {e}[/red]")
         sys.exit(1)
 
 if __name__ == "__main__":
     app()
*** End Patch
```

```
*** Begin Patch
*** Update File: .pi/skills/ops-chutes/run.sh
@@
-#!/bin/bash
-# Wrapper to run ops-chutes commands with uv
-
-# Determine skill directory
-SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
-cd "$SKILL_DIR"
-
-# Ensure dependencies are installed
-if [ ! -d ".venv" ]; then
-    uv venv
-    uv pip install .
-fi
-
-# Run the manager
-uv run manager.py "$@"
+#!/bin/bash
+# Wrapper to run ops-chutes commands with uv (fallback to python if uv missing)
+
+set -euo pipefail
+
+# Determine skill directory
+SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
+cd "$SKILL_DIR"
+
+has_uv() { command -v uv >/dev/null 2>&1; }
+
+# Ensure dependencies are installed
+if [ ! -d ".venv" ]; then
+    if has_uv; then
+        uv venv && uv pip install .
+    else
+        python3 -m venv .venv && . .venv/bin/activate && pip install .
+    fi
+fi
+
+# Run the manager
+if has_uv; then
+    uv run manager.py "$@"
+else
+    . .venv/bin/activate && python3 manager.py "$@"
+fi
*** End Patch
```


Total usage est:       1 Premium request
Total duration (API):  47.4s
Total duration (wall): 49.7s
Total code changes:    73 lines added, 74 lines removed
Usage by model:
    gpt-5                41.1k input, 8.6k output, 0 cache read, 0 cache write (Est. 1 Premium request)
