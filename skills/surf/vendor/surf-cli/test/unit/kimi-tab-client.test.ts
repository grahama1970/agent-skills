import { describe, expect, it } from "vitest";

// @ts-expect-error - CommonJS module without type definitions
import * as kimiClient from "../../native/kimi-tab-client.cjs";

describe("kimi-tab-client", () => {
  it("normalizes downstream Instant and High preference targets", () => {
    expect(kimiClient.preferenceTargets("model", "Instant")).toEqual(["instant"]);
    expect(kimiClient.preferenceTargets("reasoning", "High")).toEqual([
      "reasoninghigh",
      "thinkinghigh",
      "high",
    ]);
  });

});
