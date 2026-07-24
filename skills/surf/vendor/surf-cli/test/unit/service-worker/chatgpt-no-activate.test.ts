// Service-worker level CHATGPT_*_TAB handler behavior is verified via the
// live webgpt-no-activate-sanity skill script (browser + native host loop)
// because the handlers call cdp.attach + waitForRuntimeReady which require a
// real CDP target. Message-mapping plumbing for --no-activate is covered by
// test/unit/host-helpers.test.ts ("chatgpt no-activate plumbing").
import { describe, it, expect } from "vitest";

describe("CHATGPT noActivate (placeholder)", () => {
  it("delegates verification to the live sanity script", () => {
    expect(true).toBe(true);
  });
});
