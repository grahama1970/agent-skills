goal_hash: sha256:4ebc5120573df7d704e60a7d9887332e1767c0e6fb58712b0522e84c0444aa0d
TOP_BLOCKER: No repeatable package command sends the real Marcus crop through the Watch API to live Memory/Qdrant while proving the row-9 accepted-label receipt remains byte-for-byte unchanged.
NEXT_ACTION: Add one live smoke that reads the crop, snapshots the receipt, launches the existing Watch server with Node’s asynchronous subprocess API, calls the Watch proxy, validates live Qdrant/Arango proof scope, and compares the receipt afterward; expose it as an npm package script. 
Node.js
+2
Node.js
+2

LIVE_STOP_CONDITION: npm --prefix skills/watch/ui run test:memory-suggestion-live, npm --prefix skills/watch/ui test, and npm --prefix skills/watch/ui run typecheck all exit 0.

diff --git a/skills/watch/ui/package.json b/skills/watch/ui/package.json
--- a/skills/watch/ui/package.json
+++ b/skills/watch/ui/package.json
@@ -12,6 +12,7 @@
"start": "node server/prod.js",
"test": "tsx scripts/watchAnnotationSession.smoke.ts && tsx scripts/watchYoloLabelReceiptReplay.smoke.ts",
"test:yolo-label-receipt": "tsx scripts/watchYoloLabelReceiptReplay.smoke.ts",

"test:memory-suggestion-live": "tsx scripts/watchMemorySuggestionLive.smoke.ts",
"typecheck": "tsc --noEmit"
},
"dependencies": {
diff --git a/skills/watch/ui/scripts/watchMemorySuggestionLive.smoke.ts b/skills/watch/ui/scripts/watchMemorySuggestionLive.smoke.ts
new file mode 100644
--- /dev/null
+++ b/skills/watch/ui/scripts/watchMemorySuggestionLive.smoke.ts
@@ -0,0 +1,245 @@
+import assert from 'node:assert/strict'
+import { spawn, type ChildProcess } from 'node:child_process'
+import { once } from 'node:events'
+import { readFile } from 'node:fs/promises'
+import { createServer } from 'node:net'
+import type { AddressInfo } from 'node:net'
+import path from 'node:path'
+import { setTimeout as delay } from 'node:timers/promises'
+import { fileURLToPath } from 'node:url'

+type ProofScope = {

mocked?: boolean

live?: boolean

proves?: unknown[]
+}

+type MemorySuggestionPayload = {

schema?: string

found?: boolean

confidence?: number

proof_scope?: ProofScope
+}

+type WatchSuggestionResponse = {

schema?: string

status?: string

track_id?: string

suggestion?: {

character_name?: string

actor_name?: string

confidence?: number

tentative?: boolean

display_label?: string

} | null

memory?: MemorySuggestionPayload
+}

+const scriptDir = path.dirname(fileURLToPath(import.meta.url))
+const uiRoot = path.resolve(scriptDir, '..')
+const watchRoot = path.resolve(uiRoot, '..')
+
+const memoryBaseUrl = 'http://127.0.0.1:8601
'
+const assetUid = 'bad_santa_unrated_2003_brrip_xvidhd_720p_npw'
+const rowIndex = 9
+const trackId = 'track_2'
+
+const cropPath = path.join(

watchRoot,

'docs',

'architecture',

'generated',

'watch_identity_qdrant_marcus_eval',

'20260704T172759115162Z_yolo_track_2_only',

'crops',

'sample_15_12.515_marcus_detector_9_track_2_interpolated.png',
+)

+const row9ReceiptPath = path.join(

watchRoot,

'docs',

'architecture',

'generated',

'watch_yolo_track_labels',

${assetUid}_row0009.json,
+)

+async function readOptionalFile(filePath: string): Promise<Buffer | null> {

try {

return await readFile(filePath)

} catch (error) {

if ((error as NodeJS.ErrnoException).code === 'ENOENT') return null

throw error

}
+}

+async function unusedLocalPort(): Promise<number> {

const reservation = createServer()

await new Promise<void>((resolve, reject) => {

reservation.once('error', reject)

reservation.listen(0, '127.0.0.1', resolve)

})

const address = reservation.address() as AddressInfo | null

assert.ok(address && Number.isInteger(address.port), 'failed to reserve a Watch API port')

await new Promise<void>((resolve, reject) => {

reservation.close((error) => error ? reject(error) : resolve())

})

return address.port
+}

+async function assertLiveMemoryHealth(): Promise<void> {

let response: Response

try {

response = await fetch(${memoryBaseUrl}/health)

} catch (error) {

throw new Error(live Memory daemon unavailable at ${memoryBaseUrl}: ${String(error)})

}

const body = await response.text()

assert.equal(response.status, 200, Memory health returned ${response.status}: ${body})

const health = JSON.parse(body) as { ok?: boolean; status?: string }

assert.ok(

health.ok === true || health.status === 'ok',

Memory health did not report ready/ok: ${body},

)
+}

+async function waitForWatchApi(

baseUrl: string,

child: ChildProcess,

diagnostics: () => string,

spawnFailure: () => Error | null,
+): Promise<void> {

const readinessRoute =

'/api/projects/watch/yolo-labels?asset_uid=memory_suggestion_readiness&row_index=999999'

for (let attempt = 0; attempt < 80; attempt += 1) {

const failure = spawnFailure()

if (failure) throw failure

if (child.exitCode !== null) {

 throw new Error(
   `Watch API exited before readiness with ${child.exitCode}\n${diagnostics()}`,
 )

}

try {

 const response = await fetch(`${baseUrl}${readinessRoute}`)
 if (response.ok) return

} catch {

 // The child has not bound its socket yet.

}

await delay(50)

}

throw new Error(Watch API did not become ready\n${diagnostics()})
+}

+async function stopChild(child: ChildProcess): Promise<void> {

if (child.exitCode !== null) return

const gracefulClose = once(child, 'close')

child.kill('SIGTERM')

await Promise.race([gracefulClose, delay(2_000)])

if (child.exitCode === null) {

const forcedClose = once(child, 'close')

child.kill('SIGKILL')

await forcedClose

}
+}

+async function requestSuggestion(

baseUrl: string,

imageDataUrl: string,
+): Promise<WatchSuggestionResponse> {

const response = await fetch(${baseUrl}/api/projects/watch/identity-suggestions, {

method: 'POST',

headers: {

 'Content-Type': 'application/json',

},

body: JSON.stringify({

 asset_uid: assetUid,
 row_index: rowIndex,
 track_id: trackId,
 time_seconds: 12.515,
 image_data_url: imageDataUrl,

}),

})

const body = await response.text()

assert.equal(

response.status,
+ 200,

Watch identity-suggestions returned ${response.status}: ${body},

)

return JSON.parse(body) as WatchSuggestionResponse
+}

+async function main(): Promise<void> {

await assertLiveMemoryHealth()

const cropBytes = await readFile(cropPath)

assert.ok(cropBytes.length > 0, Marcus crop is empty: ${cropPath})

const imageDataUrl = data:image/png;base64,${cropBytes.toString('base64')}

const receiptBefore = await readOptionalFile(row9ReceiptPath)

const apiPort = await unusedLocalPort()

const baseUrl = http://127.0.0.1:${apiPort}

let stdout = ''

let stderr = ''

let spawnError: Error | null = null

const tsxCommand = process.platform === 'win32' ? 'tsx.cmd' : 'tsx'

const child = spawn(tsxCommand, ['server/index.ts'], {

cwd: uiRoot,

env: {

 ...process.env,
 WATCH_API_PORT: String(apiPort),
 MEMORY_DAEMON_URL: memoryBaseUrl,

},

stdio: ['ignore', 'pipe', 'pipe'],

})

child.stdout?.setEncoding('utf-8')

child.stderr?.setEncoding('utf-8')

child.stdout?.on('data', (chunk: string) => {

stdout = ${stdout}${chunk}.slice(-8_000)

})

child.stderr?.on('data', (chunk: string) => {

stderr = ${stderr}${chunk}.slice(-8_000)

})

child.on('error', (error) => {

spawnError = error

})

try {

await waitForWatchApi(

 baseUrl,
 child,
 () => `${stdout}\n${stderr}`,
 () => spawnError,

)

const result = await requestSuggestion(baseUrl, imageDataUrl)

assert.equal(result.schema, 'watch.identity_suggestions.v1')

assert.equal(result.status, 'ok')

assert.equal(result.track_id, trackId)

assert.ok(result.suggestion, 'Watch returned no tentative identity suggestion')

assert.equal(result.suggestion.character_name, 'Marcus')

assert.equal(result.suggestion.tentative, true)

assert.ok(

 typeof result.suggestion.confidence === 'number'
   && result.suggestion.confidence >= 0.82,
 `Marcus confidence below 0.82: ${String(result.suggestion.confidence)}`,

)

if (result.suggestion.display_label !== undefined) {

 assert.match(result.suggestion.display_label, /Marcus\?/)

}

assert.equal(result.memory?.schema, 'memory.watch_identity_crop_recall.v1')

assert.equal(result.memory?.found, true)

assert.equal(result.memory?.proof_scope?.mocked, false)

assert.equal(result.memory?.proof_scope?.live, true)

const proofText = JSON.stringify(result.memory?.proof_scope?.proves ?? [])

assert.match(proofText, /Qdrant/i)

assert.match(proofText, /Arango|hydrat/i)

} finally {

await stopChild(child)

}

const receiptAfter = await readOptionalFile(row9ReceiptPath)

assert.deepEqual(

receiptAfter,

receiptBefore,

'identity suggestion query mutated the persisted row-9 YOLO label receipt',

)
+}

+main()

.then(() => {

console.log('watchMemorySuggestionLive smoke passed')

})

.catch((error) => {

console.error(error)

process.exitCode = 1

})
