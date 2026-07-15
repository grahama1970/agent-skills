goal_hash: sha256:71eb0721c70622d86df28f5451d5d071f9d21570a8fc5c3b3257a5b565be4f89
TOP_BLOCKER: skills/watch/ui/package.json does not expose the existing row-10 reducer smoke through the npm test lifecycle.
NEXT_ACTION: Add one package script invoking the existing smoke with the already-installed local tsx executable; npm runs package scripts from the package root. 
npm Docs

LIVE_STOP_CONDITION: npm --prefix skills/watch/ui test and npm --prefix skills/watch/ui run typecheck both exit 0.

Diff
diff --git a/skills/watch/ui/package.json b/skills/watch/ui/package.json
--- a/skills/watch/ui/package.json
+++ b/skills/watch/ui/package.json
@@ -11,6 +11,7 @@
     "dev:all": "concurrently \"vite\" \"tsx watch server/index.ts\"",
     "build": "vite build",
     "start": "node server/prod.js",
+    "test": "tsx scripts/watchAnnotationSession.smoke.ts",
     "typecheck": "tsc --noEmit"
   },
   "dependencies": {
