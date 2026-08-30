# tau-scillm-provider

Local Pi provider extension for the Tau-owned SciLLM sidecar.

It registers provider `tau-scillm`, pointed at `http://127.0.0.1:4001/v1` by default, and writes provider-call receipts under:

```text
~/.pi/agent/receipts/tau-scillm-provider/latest.json
~/.pi/agent/receipts/tau-scillm-provider/requests.jsonl
```

## Configuration

Environment variables:

```text
PI_SCILLM_PROVIDER_ID   default: tau-scillm
PI_SCILLM_BASE_URL      default: http://127.0.0.1:4001/v1
PI_SCILLM_API_KEY       preferred explicit key
PI_SCILLM_RECEIPT_DIR   default: ~/.pi/agent/receipts/tau-scillm-provider
```

If `PI_SCILLM_API_KEY` is absent, the extension reads the running `docker-scillm-proxy-1` container environment first, then falls back to `SCILLM_MASTER_KEY`, `LITELLM_MASTER_KEY`, `SCILLM_PROXY_KEY`, and finally the dev default. This avoids stale shell-level proxy keys overriding the live container key. It never prints the key; status output shows only a SHA-256 fingerprint prefix.

## Use

```text
/model tau-scillm/gpt-5.5
/tau-scillm-provider
```

Or non-interactive smoke:

```bash
pi --provider tau-scillm --model local-text -p 'Say OK.'
```

## Boundary

This is a direct SciLLM provider adapter. It is not yet a full Tau DAG runner. Tau/SciLLM receipts are local provider-call receipts only: request hash, model id, response status, key source fingerprint, and live/mocked boundary.
