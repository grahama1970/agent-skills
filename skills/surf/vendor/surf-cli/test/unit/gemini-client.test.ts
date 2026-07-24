import { afterEach, vi } from "vitest";
// @ts-expect-error - CommonJS module without type definitions
import * as geminiClient from "../../native/gemini-client.cjs";

const asChromeOutput = (value: string) => ({ output: JSON.stringify(value) });

const promptTyped = (code: string) => code.includes("document.execCommand('insertText'");
const baselineCollected = (code: string) => code.includes("return JSON.stringify(baselineKeys)");
const sendClicked = (code: string) => code.includes('button[aria-label="Send message"]');
const imagesPolled = (code: string) => code.includes("window.__surfGeminiBlobImageIndexes");
const blobExtracted = (code: string) => code.includes("window.__surfGeminiBlobImages?.[0]");

type ScriptHandler = (code: string) => unknown;
type ScriptMatcher = (code: string) => boolean;

const routeJsEval = (
  code: string,
  handlers: {
    type?: ScriptHandler;
    baseline?: ScriptHandler;
    send?: ScriptHandler;
    poll?: ScriptHandler;
    blob?: ScriptHandler;
  },
) => {
  const matchers: Array<[ScriptMatcher, ScriptHandler | undefined]> = [
    [promptTyped, handlers.type],
    [baselineCollected, handlers.baseline],
    [sendClicked, handlers.send],
    [imagesPolled, handlers.poll],
    [blobExtracted, handlers.blob],
  ];
  const handler = matchers.find(([match]) => match(code))?.[1];
  if (!handler) {
    throw new Error(`Unexpected script: ${code}`);
  }
  return handler(code);
};

describe("gemini-client", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  describe("parseGeminiStreamGenerateResponse", () => {
    it("uses a later stream body when the first candidate body has empty text", () => {
      const emptyBody = [null, [], null, null, [["rc_123", [""]]]];
      const answerBody = [null, [], null, null, [["rc_123", ["pong"]]]];
      const raw = JSON.stringify([
        [null, null, JSON.stringify(emptyBody)],
        [null, null, JSON.stringify(answerBody)],
      ]);

      expect(geminiClient.parseGeminiStreamGenerateResponse(raw).text).toBe("pong");
    });

    it("extracts text when Gemini shifts the candidate text one slot deeper", () => {
      const body = [null, [], null, null, [[null, [[null, "pong"]]]]];
      const raw = JSON.stringify([[null, null, JSON.stringify(body)]]);

      expect(geminiClient.parseGeminiStreamGenerateResponse(raw).text).toBe("pong");
    });

    it("uses alternate text when the primary slot is only card content", () => {
      const body = [
        null,
        [],
        null,
        null,
        [[null, ["http://googleusercontent.com/card_content/123"], ["pong"]]],
      ];
      const raw = JSON.stringify([[null, null, JSON.stringify(body)]]);

      expect(geminiClient.parseGeminiStreamGenerateResponse(raw).text).toBe("pong");
    });

    it("returns the most complete cumulative body, not an earlier truncated prefix", () => {
      const partialBody = [null, [], null, null, [["rc_1", ["alpha bravo"]]]];
      const fullBody = [null, [], null, null, [["rc_1", ["alpha bravo charlie delta echo"]]]];
      const raw = JSON.stringify([
        [null, null, JSON.stringify(partialBody)],
        [null, null, JSON.stringify(fullBody)],
      ]);

      expect(geminiClient.parseGeminiStreamGenerateResponse(raw).text).toBe(
        "alpha bravo charlie delta echo",
      );
    });

    it("keeps the longest body when a trailing chunk carries shorter text", () => {
      const fullBody = [null, [], null, null, [["rc_1", ["alpha bravo charlie delta echo"]]]];
      const trailingBody = [null, [], null, null, [["rc_1", ["related"]]]];
      const raw = JSON.stringify([
        [null, null, JSON.stringify(fullBody)],
        [null, null, JSON.stringify(trailingBody)],
      ]);

      expect(geminiClient.parseGeminiStreamGenerateResponse(raw).text).toBe(
        "alpha bravo charlie delta echo",
      );
    });

    it("preserves a generated image that arrives in a later equal-text chunk", () => {
      const url = "http://img/gen.png";
      const genImage = [[null, null, null, [null, null, null, url]]];
      const imgCand: any[] = ["rc", ["cat"]];
      imgCand[12] = [];
      imgCand[12][7] = [[genImage]];
      const raw = JSON.stringify([
        [null, null, JSON.stringify([null, [], null, null, [["rc", ["cat"]]]])],
        [null, null, JSON.stringify([null, [], null, null, [imgCand]])],
      ]);

      const result = geminiClient.parseGeminiStreamGenerateResponse(raw);
      expect(result.text).toBe("cat");
      expect(result.images).toEqual([
        { kind: "generated", url, title: "[Generated Image]", alt: "" },
      ]);
    });

    it("returns every generated image from the cumulative final chunk", () => {
      const mk = (url: string) => [[null, null, null, [null, null, null, url]]];
      const cand1: any[] = ["rc", ["pic"]];
      cand1[12] = [];
      cand1[12][7] = [[mk("http://one")]];
      const cand2: any[] = ["rc", ["pic"]];
      cand2[12] = [];
      cand2[12][7] = [[mk("http://one"), mk("http://two")]];
      const raw = JSON.stringify([
        [null, null, JSON.stringify([null, [], null, null, [cand1]])],
        [null, null, JSON.stringify([null, [], null, null, [cand2]])],
      ]);

      const result = geminiClient.parseGeminiStreamGenerateResponse(raw);
      expect(result.images.map((i: { url: string }) => i.url)).toEqual([
        "http://one",
        "http://two",
      ]);
    });

    it("does not let a trailing empty image list erase an earlier image", () => {
      const mk = (url: string) => [[null, null, null, [null, null, null, url]]];
      const cand1: any[] = ["rc", ["pic"]];
      cand1[12] = [];
      cand1[12][7] = [[mk("http://one")]];
      const cand2: any[] = ["rc", ["pic"]];
      cand2[12] = [];
      cand2[12][7] = [[]];
      const raw = JSON.stringify([
        [null, null, JSON.stringify([null, [], null, null, [cand1]])],
        [null, null, JSON.stringify([null, [], null, null, [cand2]])],
      ]);

      const result = geminiClient.parseGeminiStreamGenerateResponse(raw);
      expect(result.images.map((i: { url: string }) => i.url)).toEqual(["http://one"]);
    });

    it("ranks a real answer over an earlier unresolved card-content placeholder", () => {
      const cardOnlyBody = [
        null,
        [],
        null,
        null,
        [[null, ["http://googleusercontent.com/card_content/123"]]],
      ];
      const answerBody = [null, [], null, null, [["rc_1", ["pong"]]]];
      const raw = JSON.stringify([
        [null, null, JSON.stringify(cardOnlyBody)],
        [null, null, JSON.stringify(answerBody)],
      ]);

      expect(geminiClient.parseGeminiStreamGenerateResponse(raw).text).toBe("pong");
    });
  });

  describe("runGeminiWebViaPage", () => {
    it("sends expression-safe page scripts through jsEval", async () => {
      vi.useFakeTimers();
      const seenScripts: string[] = [];

      const run = geminiClient.runGeminiWebViaPage({
        prompt: "quote ' and newline\nsafe",
        model: "gemini-3.1-pro",
        timeoutMs: 10_000,
        createTab: async () => ({ tabId: 123 }),
        closeTab: async () => ({ ok: true }),
        jsEval: async (_tabId: number, code: string) => {
          seenScripts.push(code);
          return routeJsEval(code, {
            type: (c) => {
              expect(c.trim()).toMatch(/^\(\(\) => \{/);
              expect(c).toContain(
                "document.execCommand('insertText', false, \"quote ' and newline\\nsafe\")",
              );
              return asChromeOutput(JSON.stringify({ ok: true, len: 24 }));
            },
            baseline: () => asChromeOutput(JSON.stringify([])),
            send: (c) => {
              expect(c.trim()).toMatch(/^\(\(\) => \{/);
              return asChromeOutput("sent");
            },
            poll: (c) => {
              expect(c.trim()).toMatch(/^\(async \(\) => \{/);
              return asChromeOutput(
                JSON.stringify({ images: [], loading: false, text: "done", turns: 1 }),
              );
            },
          });
        },
      });

      await vi.runAllTimersAsync();
      await expect(run).resolves.toMatchObject({ text: "done" });
      expect(seenScripts.length).toBeGreaterThanOrEqual(4);
    });

    it("detects and extracts large blob-backed generated images without alt or class markers", async () => {
      vi.useFakeTimers();
      const seenScripts: string[] = [];
      const logs: string[] = [];

      const run = geminiClient.runGeminiWebViaPage({
        prompt: "generate a test image",
        model: "gemini-3.1-pro",
        timeoutMs: 10_000,
        log: (msg: string) => logs.push(msg),
        createTab: async () => ({ tabId: 123 }),
        closeTab: async () => ({ ok: true }),
        jsEval: async (_tabId: number, code: string) => {
          seenScripts.push(code);
          return routeJsEval(code, {
            type: () => asChromeOutput(JSON.stringify({ ok: true, len: 21 })),
            baseline: (c) => {
              expect(c).toContain('url.startsWith("blob:")');
              expect(c).toContain('url.includes("gg-dl")');
              expect(c).not.toContain("alt");
              expect(c).not.toContain("className");
              return asChromeOutput(JSON.stringify([]));
            },
            send: () => asChromeOutput("sent"),
            poll: (c) => {
              expect(c).toContain('url.startsWith("blob:")');
              expect(c).toContain("canvas.toDataURL");
              expect(c).not.toContain("alt");
              expect(c).not.toContain("className");
              return asChromeOutput(
                JSON.stringify({
                  images: [
                    {
                      url: "blob:https://gemini.google.com/generated-image",
                      blobIndex: 0,
                      type: "image/png",
                    },
                  ],
                  loading: false,
                  text: "",
                  turns: 1,
                }),
              );
            },
            blob: () =>
              asChromeOutput(
                JSON.stringify({
                  chunk: "ZmFrZS1wbmc=",
                  done: true,
                  type: "image/png",
                  url: "blob:https://gemini.google.com/generated-image",
                }),
              ),
          });
        },
      });

      await vi.runAllTimersAsync();
      const result = await run;

      expect(result.images).toEqual([
        {
          url: "blob:https://gemini.google.com/generated-image",
          b64: "ZmFrZS1wbmc=",
          type: "image/png",
        },
      ]);
      expect(logs).toContain("Found 1 generated image(s)");
      expect(seenScripts.some((script) => script.includes("gg-dl"))).toBe(true);
    });

    it("excludes pre-existing large images before serializing blob candidates", async () => {
      vi.useFakeTimers();
      const baselineKey = "blob:https://gemini.google.com/baseline|1024x1024";

      const run = geminiClient.runGeminiWebViaPage({
        prompt: "generate a new image",
        model: "gemini-3.1-pro",
        timeoutMs: 10_000,
        createTab: async () => ({ tabId: 123 }),
        closeTab: async () => ({ ok: true }),
        jsEval: async (_tabId: number, code: string) =>
          routeJsEval(code, {
            type: () => asChromeOutput(JSON.stringify({ ok: true, len: 20 })),
            baseline: () => asChromeOutput(JSON.stringify([baselineKey])),
            send: () => asChromeOutput("sent"),
            poll: (c) => {
              expect(c).toContain(`const baselineKeys = new Set(["${baselineKey}"])`);
              expect(c).toContain(".filter((img) => !baselineKeys.has(imageKey(img)))");
              expect(c.indexOf("!baselineKeys.has(imageKey(img))")).toBeLessThan(
                c.indexOf("canvas.toDataURL"),
              );
              return asChromeOutput(
                JSON.stringify({
                  images: [],
                  loading: false,
                  text: "No new image was generated.",
                  turns: 1,
                }),
              );
            },
          }),
      });

      await vi.runAllTimersAsync();
      const result = await run;

      expect(result.images).toEqual([]);
      expect(result.text).toBe("No new image was generated.");
    });

    it("keeps existing gg-dl image URL download support", async () => {
      vi.useFakeTimers();
      const fetchUrl = vi.fn(async (url: string) => ({
        b64: url === "https://lh3.googleusercontent.com/gg-dl/generated" ? "Z2ctZGw=" : "",
        type: "image/jpeg",
      }));

      const run = geminiClient.runGeminiWebViaPage({
        prompt: "generate a test image",
        model: "gemini-3.1-pro",
        timeoutMs: 10_000,
        createTab: async () => ({ tabId: 123 }),
        closeTab: async () => ({ ok: true }),
        fetchUrl,
        jsEval: async (_tabId: number, code: string) =>
          routeJsEval(code, {
            type: () => asChromeOutput(JSON.stringify({ ok: true, len: 21 })),
            baseline: () => asChromeOutput(JSON.stringify([])),
            send: () => asChromeOutput("sent"),
            poll: () =>
              asChromeOutput(
                JSON.stringify({
                  images: [{ url: "https://lh3.googleusercontent.com/gg-dl/generated" }],
                  loading: false,
                  text: "",
                  turns: 1,
                }),
              ),
          }),
      });

      await vi.runAllTimersAsync();
      const result = await run;

      expect(fetchUrl).toHaveBeenCalledWith("https://lh3.googleusercontent.com/gg-dl/generated");
      expect(result.images).toEqual([
        {
          url: "https://lh3.googleusercontent.com/gg-dl/generated",
          b64: "Z2ctZGw=",
          type: "image/jpeg",
        },
      ]);
    });
  });
});
