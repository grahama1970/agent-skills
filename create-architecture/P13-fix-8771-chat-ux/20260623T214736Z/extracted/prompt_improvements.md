# Prompt improvements

1. Explicitly require a server-side env injection shim whenever a browser-only static page must use a secret-backed browser API.
2. Require the page to contain no pasted-secret UI and no committed key material.
3. Require visual parity references to be converted into class names and layout requirements, not screenshots or prose only.
4. Require the golden_state_server protocol to be treated as tolerant/best-effort unless a precise schema is included in the bundle.
5. Require deterministic static tests for the anti-regression items: no key input, required real_* flags, ChatWell classes, and server injection path.
