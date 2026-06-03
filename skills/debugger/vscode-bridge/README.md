# Debugger VS Code Bridge

This extension is the visible VS Code bridge for the `$debugger` skill.

The terminal-side skill writes a request file:

```text
.vscode/debugger-bridge/request.json
```

The extension watches that file from inside the VS Code extension host. It can:

- add source breakpoints,
- start a named launch configuration with `vscode.debug.startDebugging(...)`,
- restart a visible debug session after replacing stale breakpoints,
- continue an already stopped visible debug session,
- save dirty breakpoint source files before starting,
- observe debug adapter `stopped` events through a tracker,
- request stack, scopes, variables, and watched expressions from the active debug adapter,
- write a status/proof artifact back to disk.

The bridge does not scrape the VS Code Variables pane. It captures variable state through the Debug Adapter Protocol.
