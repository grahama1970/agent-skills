> **Review Metadata**: Round 2 | Final Diff | Provider: github | Model: gpt-5
---

✓ List directory . (33 files)

✓ List directory commands (14 files)

✓ List directory providers (10 files)

✗ Read commands/check.py
   Path does not exist

✗ Read commands/models.py
   Path does not exist

✓ Read utils.py (263 lines)

✓ Read providers/github.py (74 lines)

✓ Read commands/review.py (136 lines)

✓ Read providers/base.py (283 lines)

✓ Read code_review.py (107 lines)

✓ Read commands/review_full.py (358 lines)

✓ Read commands/loop.py (211 lines)

✓ Read commands/bundle.py (212 lines)

✓ Read commands/basic.py (182 lines)

✓ Read commands/build.py (102 lines)

✓ Edit utils.py (+1)
   ╭──────────────────────────────────────────────────────────────────────────────────────────────╮
   │  9     from __future__ import annotations                                                    │
   │ 10                                                                                           │
   │ 11     import re                                                                             │
   │ 12  +  import os                                                                             │
   │ 13     import shutil                                                                         │
   │ 14     import subprocess                                                                     │
   │ 15     import sys                                                                            │
   ╰──────────────────────────────────────────────────────────────────────────────────────────────╯

✓ Edit commands/review_full.py (+1)
   ╭──────────────────────────────────────────────────────────────────────────────────────────────╮
   │ 3                                                                                            │
   │ 4     import asyncio                                                                         │
   │ 5     import json                                                                            │
   │ 6  +  import os                                                                              │
   │ 7     import subprocess                                                                      │
   │ 8     import sys                                                                             │
   │ 9     import time                                                                            │
   ╰──────────────────────────────────────────────────────────────────────────────────────────────╯

✓ Edit commands/basic.py (+2 -2)
   ╭──────────────────────────────────────────────────────────────────────────────────────────────╮
   │ 14                                                                                           │
   │ 15     # Handle both import modes                                                            │
   │ 16     try:                                                                                  │
   │ 17  -      from ..config import DEFAULT_PROVIDER, PROVIDERS, SCRIPT_DIR                      │
   │ 17  +      from ..config import DEFAULT_PROVIDER, PROVIDERS, SCRIPT_DIR, get_timeout         │
   │ 18         from ..providers import check_gh_auth, find_provider_cli                          │
   │ 19     except ImportError:                                                                   │
   │ 20  -      from config import DEFAULT_PROVIDER, PROVIDERS, SCRIPT_DIR                        │
   │ 20  +      from config import DEFAULT_PROVIDER, PROVIDERS, SCRIPT_DIR, get_timeout           │
   │ 21         from providers import check_gh_auth, find_provider_cli                            │
   ╰──────────────────────────────────────────────────────────────────────────────────────────────╯

✓ Edit commands/basic.py (+1 -1)
   ╭──────────────────────────────────────────────────────────────────────────────────────────────╮
   │ 157                                                                                          │
   │ 158     # Run interactively                                                                  │
   │ 159     try:                                                                                 │
   │ 160  -      result = subprocess.run(cmd)                                                     │
   │ 160  +      result = subprocess.run(cmd, timeout=get_timeout()                               │
   │ 161         if result.returncode == 0:                                                       │
   │ 162             typer.echo("\nAuthentication successful!", err=True)                         │
   ╰──────────────────────────────────────────────────────────────────────────────────────────────╯

✓ Edit utils.py (+3 -2)
   ╭──────────────────────────────────────────────────────────────────────────────────────────────╮
   │ 193                 except ValueError:                                                       │
   │ 194                     pass                                                                 │
   │ 195                                                                                          │
   │ 196  -  except Exception:                                                                    │
   │ 197  -      pass                                                                             │
   │ 196  +  except Exception as e                                                                │
   │ 197  +      if os.environ.get("CODE_REVIEW_DEBUG"):                                          │
   │ 198  +          console.print(f"[yellow]Git status check warning: {e}[/yellow]")             │
   │ 199                                                                                          │
   │ 200     return result                                                                        │
   ╰──────────────────────────────────────────────────────────────────────────────────────────────╯

✓ Edit commands/review_full.py (+2 -2)
   ╭──────────────────────────────────────────────────────────────────────────────────────────────╮
   │ 14                                                                                           │
   │ 15     # Handle both import modes                                                            │
   │ 16     try:                                                                                  │
   │ 17  -      from ..config import DEFAULT_MODEL, DEFAULT_PROVIDER, PROVIDERS, SCRIPT_DIR,      │
   │        SKILLS_DIR                                                                            │
   │ 17  +      from ..config import DEFAULT_MODEL, DEFAULT_PROVIDER, PROVIDERS, SCRIPT_DIR,      │
   │        SKILLS_DIR, get_timeout                                                               │
   │ 18         from ..diff_parser import extract_diff                                            │
   │ 19         from ..prompts import STEP1_PROMPT, STEP2_PROMPT, STEP3_PROMPT                    │
   │ 20         from ..providers import find_provider_cli, run_provider_async                     │
   │ 21         from ..utils import create_workspace, get_effective_dirs                          │
   │ 22     except ImportError:                                                                   │
   │ 23  -      from config import DEFAULT_MODEL, DEFAULT_PROVIDER, PROVIDERS, SCRIPT_DIR,        │
   │        SKILLS_DIR                                                                            │
   │ 23  +      from config import DEFAULT_MODEL, DEFAULT_PROVIDER, PROVIDERS, SCRIPT_DIR,        │
   │        SKILLS_DIR, get_timeout                                                               │
   │ 24         from diff_parser import extract_diff                                              │
   │ 25         from prompts import STEP1_PROMPT, STEP2_PROMPT, STEP3_PROMPT                      │
   │ 26         from providers import find_provider_cli, run_provider_async                       │
   ╰──────────────────────────────────────────────────────────────────────────────────────────────╯

✓ Edit utils.py (+1 -1)
   ╭──────────────────────────────────────────────────────────────────────────────────────────────╮
   │ 217     # Remote URL -> Owner/Repo                                                           │
   │ 218     res = subprocess.run(                                                                │
   │ 219         ["git", "remote", "get-url", "origin"],                                          │
   │ 220  -      capture_output=True, text=True, cwd=cwd, timeout=5                               │
   │ 220  +      capture_output=True, text=True, cwd=cwd, timeout=get_timeout()                   │
   │ 221     )                                                                                    │
   │ 222     if res.returncode == 0:                                                              │
   │ 223         url = res.stdout.strip()                                                         │
   ╰──────────────────────────────────────────────────────────────────────────────────────────────╯

✓ Edit commands/review_full.py (+4 -3)
   ╭──────────────────────────────────────────────────────────────────────────────────────────────╮
   │ 292                 "--state", str(state_file),                                              │
   │ 293                 "--total", str(rounds),                                                  │
   │ 294                 "--desc", f"Code Review: {file.name}"                                    │
   │ 295  -          ], capture_output=True, check=False)                                         │
   │ 296  -      except Exception:                                                                │
   │ 297  -          pass                                                                         │
   │ 295  +          ], capture_output=True, check=False, timeout=get_timeout()                   │
   │ 296  +      except Exception as e                                                            │
   │ 297  +          if os.environ.get("CODE_REVIEW_DEBUG"):                                      │
   │ 298  +              typer.echo(f"Monitor register warning: {e}", err=True)                   │
   │ 299                                                                                          │
   │ 300     typer.echo(f"Using provider: {provider} ({actual_model})", err=True)                 │
   ╰──────────────────────────────────────────────────────────────────────────────────────────────╯

✓ Edit utils.py (+1 -1)
   ╭──────────────────────────────────────────────────────────────────────────────────────────────╮
   │ 229     # Branch                                                                             │
   │ 230     res = subprocess.run(                                                                │
   │ 231         ["git", "branch", "--show-current"],                                             │
   │ 232  -      capture_output=True, text=True, cwd=cwd, timeout=5                               │
   │ 232  +      capture_output=True, text=True, cwd=cwd, timeout=get_timeout()                   │
   │ 233     )                                                                                    │
   │ 234     if res.returncode == 0:                                                              │
   │ 235         context["branch"] = res.stdout.strip()                                           │
   ╰──────────────────────────────────────────────────────────────────────────────────────────────╯

✓ Edit utils.py (+1 -1)
   ╭──────────────────────────────────────────────────────────────────────────────────────────────╮
   │ 237     # Modified files (staged and unstaged)                                               │
   │ 238     res = subprocess.run(                                                                │
   │ 239         ["git", "diff", "--name-only", "HEAD"],                                          │
   │ 240  -      capture_output=True, text=True, cwd=cwd, timeout=5                               │
   │ 240  +      capture_output=True, text=True, cwd=cwd, timeout=get_timeout()                   │
   │ 241     )                                                                                    │
   │ 242     if res.returncode == 0 and res.stdout.strip():                                       │
   │ 243         context["modified_files"] = res.stdout.strip().splitlines()                      │
   ╰──────────────────────────────────────────────────────────────────────────────────────────────╯

Show changes and run sanity.sh for code-review
   $ git --no-pager diff -- .pi/skills/code-review | cat && cd .pi/skills/code-review && ./sanity.sh

   ↪ 2 lines...

✓ Show diff and run top-level sanity.sh in skill dir
   $ git --no-pager diff -- .pi/skills/code-review | cat && ./sanity.sh
   ↪ 53 lines...

Clarifying answers:
1) Yes—added CODE_REVIEW_DEBUG-gated warnings to utils.check_git_status and review_full monitor registration; others can be extended similarly later.
2) Kept runtime typing as-is; no TypedDicts added in this patch per guidance.
3) Dual import mode retained; no changes beyond safe import additions where needed.

```diff
extend timeouts and debug logging across commands and utils per feedback
--- a/.pi/skills/code-review/utils.py
+++ b/.pi/skills/code-review/utils.py
@@ -8,11 +8,12 @@
 from __future__ import annotations
 
 import re
+import os
 import shutil
 import subprocess
 import sys
 import tempfile
 from contextlib import contextmanager
 from pathlib import Path
 from typing import Generator, Optional
@@ -193,8 +194,9 @@ def check_git_status(repo_dir: Optional[Path] = None) -> dict:
-    except Exception:
-        pass
+    except Exception as e:
+        if os.environ.get("CODE_REVIEW_DEBUG"):
+            console.print(f"[yellow]Git status check warning: {e}[/yellow]")
 
     return result
@@ -220,7 +222,7 @@ def gather_repo_context(repo_dir: Optional[Path] = None) -> dict:
-        res = subprocess.run(
-            ["git", "remote", "get-url", "origin"],
-            capture_output=True, text=True, cwd=cwd, timeout=5
-        )
+        res = subprocess.run(
+            ["git", "remote", "get-url", "origin"],
+            capture_output=True, text=True, cwd=cwd, timeout=get_timeout()
+        )
         if res.returncode == 0:
             url = res.stdout.strip()
             # Parse git@github.com:owner/repo.git or https://github.com/owner/repo
@@ -232,7 +234,7 @@ def gather_repo_context(repo_dir: Optional[Path] = None) -> dict:
-        res = subprocess.run(
-            ["git", "branch", "--show-current"],
-            capture_output=True, text=True, cwd=cwd, timeout=5
-        )
+        res = subprocess.run(
+            ["git", "branch", "--show-current"],
+            capture_output=True, text=True, cwd=cwd, timeout=get_timeout()
+        )
         if res.returncode == 0:
             context["branch"] = res.stdout.strip()
@@ -240,7 +242,7 @@ def gather_repo_context(repo_dir: Optional[Path] = None) -> dict:
-        res = subprocess.run(
-            ["git", "diff", "--name-only", "HEAD"],
-            capture_output=True, text=True, cwd=cwd, timeout=5
-        )
+        res = subprocess.run(
+            ["git", "diff", "--name-only", "HEAD"],
+            capture_output=True, text=True, cwd=cwd, timeout=get_timeout()
+        )
         if res.returncode == 0 and res.stdout.strip():
             context["modified_files"] = res.stdout.strip().splitlines()
 
--- a/.pi/skills/code-review/commands/review_full.py
+++ b/.pi/skills/code-review/commands/review_full.py
@@ -3,6 +3,7 @@ from __future__ import annotations
 
 import asyncio
 import json
+import os
 import subprocess
 import sys
 import time
@@ -14,12 +15,12 @@ import typer
 
 try:
-    from ..config import DEFAULT_MODEL, DEFAULT_PROVIDER, PROVIDERS, SCRIPT_DIR, SKILLS_DIR
+    from ..config import DEFAULT_MODEL, DEFAULT_PROVIDER, PROVIDERS, SCRIPT_DIR, SKILLS_DIR, get_timeout
     from ..diff_parser import extract_diff
     from ..prompts import STEP1_PROMPT, STEP2_PROMPT, STEP3_PROMPT
     from ..providers import find_provider_cli, run_provider_async
     from ..utils import create_workspace, get_effective_dirs
 except ImportError:
-    from config import DEFAULT_MODEL, DEFAULT_PROVIDER, PROVIDERS, SCRIPT_DIR, SKILLS_DIR
+    from config import DEFAULT_MODEL, DEFAULT_PROVIDER, PROVIDERS, SCRIPT_DIR, SKILLS_DIR, get_timeout
     from diff_parser import extract_diff
     from prompts import STEP1_PROMPT, STEP2_PROMPT, STEP3_PROMPT
     from providers import find_provider_cli, run_provider_async
     from utils import create_workspace, get_effective_dirs
@@ -287,9 +288,11 @@ def review_full(
-            subprocess.run([
+            subprocess.run([
                 "python3", str(SKILLS_DIR / "task-monitor" / "monitor.py"),
                 "register",
                 "--name", f"review-{file.stem}",
                 "--state", str(state_file),
                 "--total", str(rounds),
                 "--desc", f"Code Review: {file.name}"
-            ], capture_output=True, check=False)
-        except Exception:
-            pass
+            ], capture_output=True, check=False, timeout=get_timeout())
+        except Exception as e:
+            if os.environ.get("CODE_REVIEW_DEBUG"):
+                typer.echo(f"Monitor register warning: {e}", err=True)
 
--- a/.pi/skills/code-review/commands/basic.py
+++ b/.pi/skills/code-review/commands/basic.py
@@ -17,11 +17,11 @@ from typing import Optional
 import typer
 
 try:
-    from ..config import DEFAULT_PROVIDER, PROVIDERS, SCRIPT_DIR
+    from ..config import DEFAULT_PROVIDER, PROVIDERS, SCRIPT_DIR, get_timeout
     from ..providers import check_gh_auth, find_provider_cli
 except ImportError:
-    from config import DEFAULT_PROVIDER, PROVIDERS, SCRIPT_DIR
+    from config import DEFAULT_PROVIDER, PROVIDERS, SCRIPT_DIR, get_timeout
     from providers import check_gh_auth, find_provider_cli
@@ -157,7 +157,7 @@ def login(
-    try:
-        result = subprocess.run(cmd)
+    try:
+        result = subprocess.run(cmd, timeout=get_timeout())
         if result.returncode == 0:
             typer.echo("\nAuthentication successful!", err=True)
```


Total usage est:       1 Premium request
Total duration (API):  45.0s
Total duration (wall): 49.0s
Total code changes:    17 lines added, 13 lines removed
Usage by model:
    gpt-5                348.0k input, 6.9k output, 0 cache read, 0 cache write (Est. 1 Premium request)
