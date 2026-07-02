# ask Docs Project Knowledge

`$ask` no longer owns WebGPT/ChatGPT browser integration. WebGPT behavior,
project bindings, archive delivery, and review loops live in `$webgpt`.

Ask docs should describe only these browser lanes:

- `webgemini`
- `webkimi`
- `webperplexity`
- `cursor-browser`

When documenting review evidence, use one concatenated readable text bundle for
ask browser lanes. Do not document `--webgpt-*`, `webgpt-project`,
`--oracle-backend webgpt`, `$ask webgpt`, or `$ask chatgpt` as supported ask
flows except in explicit fail-closed handoff notes that point to `$webgpt`.
