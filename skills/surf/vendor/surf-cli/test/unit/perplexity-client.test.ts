// @ts-expect-error - CommonJS module without type definitions
import * as perplexityClient from "../../native/perplexity-client.cjs";

type FakeEl = { innerText: string };

function withFakeDom(matches: Record<string, string[]>, run: () => void): void {
  const doc = {
    querySelectorAll(selector: string): FakeEl[] {
      return (matches[selector] || []).map((innerText) => ({ innerText }));
    },
  };
  const prev = (globalThis as { document?: unknown }).document;
  (globalThis as { document?: unknown }).document = doc;
  try {
    run();
  } finally {
    (globalThis as { document?: unknown }).document = prev;
  }
}

describe("perplexity-client", () => {
  describe("extractPerplexityResponseText", () => {
    it("prefers the answer container over individual prose sub-blocks", () => {
      withFakeDom(
        {
          '[id^="markdown-content"]': [
            "Ganymede is largest.\nCallisto is cratered.\nIo is volcanic.",
          ],
          ".prose": ["Ganymede is largest.", "Callisto is cratered.", "Io is volcanic."],
        },
        () => {
          expect(perplexityClient.extractPerplexityResponseText()).toBe(
            "Ganymede is largest.\nCallisto is cratered.\nIo is volcanic.",
          );
        },
      );
    });

    it("returns the most recent answer when multiple containers exist", () => {
      withFakeDom({ '[id^="markdown-content"]': ["first answer", "second answer"] }, () => {
        expect(perplexityClient.extractPerplexityResponseText()).toBe("second answer");
      });
    });

    it("falls back to prose when no answer container is present", () => {
      withFakeDom({ ".prose": ["only prose block"] }, () => {
        expect(perplexityClient.extractPerplexityResponseText()).toBe("only prose block");
      });
    });
  });

  describe("waitForResponse", () => {
    it("completes when a short response is no longer generating", async () => {
      await expect(
        perplexityClient.waitForResponse(async (expr: string) => {
          if (expr === "location.href") {
            return { result: { value: "https://www.perplexity.ai/search/test" } };
          }
          return {
            result: {
              value: {
                text: "pong",
                generating: false,
                hasActions: true,
                hasRelated: false,
                hasFollowUp: false,
                sourcesCount: 0,
                url: "https://www.perplexity.ai/search/test",
              },
            },
          };
        }, 5000),
      ).resolves.toMatchObject({
        text: "pong",
        sources: 0,
      });
    });
  });
});
