> **Review Metadata**: Round 2 | Step 1 | Provider: github | Model: gpt-5
---

Clarifying questions:
1) Do you want retries/backoff for provider subprocess invocations added now, or leave as future work behind an env flag?
2) Should we introduce TypedDicts for JSON outputs (check/models) in this patch, or keep runtime-only typing the same?
3) Is adding a CODE_REVIEW_DEBUG env-gated warning acceptable for previously silent exceptions?

```diff
standardize timeouts, add debug logging, clean imports, and clarify comment
--- a/.pi/skills/code-review/code_review.py
+++ b/.pi/skills/code-review/code_review.py
@@ -35,6 +35,6 @@
-# Handle both direct execution and module import scenarios
-# When run directly (python code_review.py), we need to add parent to sys.path
-# When run as module (python -m code_review.code_review), relative imports work
+# Handle both direct execution and module import scenarios
+# When run directly (python code_review.py), ensure this directory is on sys.path
+# When run as a module (python -m code_review.code_review), relative imports work as-is
 _SCRIPT_DIR = Path(__file__).resolve().parent
 if str(_SCRIPT_DIR) not in sys.path:
     sys.path.insert(0, str(_SCRIPT_DIR))
--- a/.pi/skills/code-review/utils.py
+++ b/.pi/skills/code-review/utils.py
@@ -11,6 +11,7 @@
 from __future__ import annotations
 
 import re
+import os
 import shutil
 import subprocess
 import sys
@@ -189,8 +190,11 @@ def check_git_status(repo_dir: Optional[Path] = None) -> dict:
-    except Exception:
-        pass
+    except Exception as e:
+        # Only log in debug mode to avoid noisy output by default
+        if os.environ.get("CODE_REVIEW_DEBUG"):
+            console.print(f"[yellow]Git status check warning: {e}[/yellow]")
 
     return result
@@ -216,7 +220,7 @@ def gather_repo_context(repo_dir: Optional[Path] = None) -> dict:
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
@@ -228,7 +232,7 @@ def gather_repo_context(repo_dir: Optional[Path] = None) -> dict:
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
@@ -236,7 +240,7 @@ def gather_repo_context(repo_dir: Optional[Path] = None) -> dict:
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
@@ -16,12 +16,12 @@ from typing import Any, Optional
-try:
-    from ..config import DEFAULT_MODEL, DEFAULT_PROVIDER, PROVIDERS, SCRIPT_DIR, SKILLS_DIR
+try:
+    from ..config import DEFAULT_PROVIDER, PROVIDERS, SCRIPT_DIR, SKILLS_DIR, get_timeout
     from ..diff_parser import extract_diff
     from ..prompts import STEP1_PROMPT, STEP2_PROMPT, STEP3_PROMPT
     from ..providers import find_provider_cli, run_provider_async
     from ..utils import create_workspace, get_effective_dirs
 except ImportError:
-    from config import DEFAULT_MODEL, DEFAULT_PROVIDER, PROVIDERS, SCRIPT_DIR, SKILLS_DIR
+    from config import DEFAULT_PROVIDER, PROVIDERS, SCRIPT_DIR, SKILLS_DIR, get_timeout
     from diff_parser import extract_diff
     from prompts import STEP1_PROMPT, STEP2_PROMPT, STEP3_PROMPT
     from providers import find_provider_cli, run_provider_async
     from utils import create_workspace, get_effective_dirs
@@ -287,7 +287,7 @@ def review_full(
-            ], capture_output=True, check=False)
+            ], capture_output=True, check=False, timeout=get_timeout())
         except Exception:
             pass
```


Total usage est:       1 Premium request
Total duration (API):  21.6s
Total duration (wall): 23.3s
Total code changes:    0 lines added, 0 lines removed
Usage by model:
    gpt-5                51.1k input, 3.1k output, 0 cache read, 0 cache write (Est. 1 Premium request)
