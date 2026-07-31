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

  it("does not abort when stale page-level capacity text coexists with current sentinel response", () => {
    expect(
      kimiClient.shouldAbortForProviderBusy(
        {
          text: "2+2=4\n<<<KIMI_DONE:test>>>",
          providerBusyInPage: true,
          providerBusyInResponse: false,
        },
        "previous answer",
        true,
      ),
    ).toBe(false);
  });

  it("aborts when the current assistant response is a fresh capacity message", () => {
    expect(
      kimiClient.shouldAbortForProviderBusy(
        {
          text: "System is currently busy. Please try again later.",
          providerBusyInPage: true,
          providerBusyInResponse: true,
        },
        "previous answer",
        false,
      ),
    ).toBe(true);
  });

  it("does not treat prompt text mentioning provider capacity as Kimi capacity evidence", () => {
    expect(
      kimiClient.textLooksKimiProviderBusy(
        "If Kimi provider capacity is busy, preserve a recovery packet.",
      ),
    ).toBe(false);
  });

  it("exports a bounded composer insertion retry timeout", () => {
    expect(kimiClient.COMPOSER_INSERT_TIMEOUT_MS).toBeGreaterThanOrEqual(1000);
    expect(kimiClient.COMPOSER_INSERT_TIMEOUT_MS).toBeLessThanOrEqual(120000);
  });

});
