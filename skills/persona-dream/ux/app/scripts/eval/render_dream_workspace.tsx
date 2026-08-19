/** Eval: server-render DreamWorkspace and assert the workspace skeleton exists.
 *
 * Guards the 2026-08-19 incident where the 99-file DreamWorkspace split left
 * `loadPhase02MediaGate` unexported: the component threw a ReferenceError at
 * first render, React unmounted to a blank page, and nothing caught it because
 * ui/src is @ts-nocheck and no consumer executed the component. renderToString
 * executes the full component body, so any render-time ReferenceError fails
 * this script with a non-zero exit.
 */
import './ssr_dom_shim'
import React from 'react'
import { renderToString } from 'react-dom/server'

// 'pd-ui' resolves via esbuild alias in render_dream_workspace.mjs; PD_UI_SRC
// lets the fail-before-fix proof point it at a deliberately broken copy.
import { DreamWorkspace } from 'pd-ui'

const html = renderToString(React.createElement(DreamWorkspace))
const markers = ['dream:workspace']
const missing = markers.filter((m) => !html.includes(m))
if (missing.length > 0) {
  console.error(`RENDER_MISSING_WORKSPACE_MARKERS: ${missing.join(', ')} (rendered ${html.length} chars)`)
  process.exit(1)
}
if (html.length < 2000) { console.error(`RENDER_SUSPICIOUSLY_SMALL: ${html.length} chars`); process.exit(1) }
console.log(`WORKSPACE_RENDER_OK chars=${html.length} phases=${(html.match(/Phase \d\d:/g) ?? []).length}`)
