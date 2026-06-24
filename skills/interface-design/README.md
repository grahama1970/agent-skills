# `/interface-design`

A receipt-backed outer DAG for interface precedent research, static HTML/CSS
mockup tournaments, component inventory, and isolated React implementation
competitors.

```bash
./run.sh init \
  --brief examples/SPARTA_CHAT_BRIEF.md \
  --surface sparta-chat \
  --target-repo /path/to/sparta \
  --output /tmp/sparta-chat-design

./run.sh status --run /tmp/sparta-chat-design
./run.sh validate --run /tmp/sparta-chat-design
```

The controller does not call providers or edit the target application. It creates
and validates the durable run contract consumed by `github-search`, `brave-search`,
`scillm`, `create-mockup`, `surf`, `review-design`, `loop`, `test-interactions`, and
the project agent.
