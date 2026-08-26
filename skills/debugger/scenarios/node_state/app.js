// Nested/cyclic/oversized state for the Node/TypeScript bounded-expansion eval.
// Same shape as scenarios/variable_state/nested.py, through the js-debug adapter.

function build() {
  const payload = { user: { name: "ada", roles: ["admin", "dev"] }, count: 3 };
  const loop = [];
  loop.push(loop); // self-referential: expansion must mark a cycle
  const blob = "B".repeat(50000); // oversized: truncate with metadata
  const apiToken = "sk-abcdefghijklmnop1234"; // secret-shaped: redact by value
  const unrelated = "must not appear in capture";
  const total = payload.count + loop.length;
  return total; // breakpoint on this line
}

build();
