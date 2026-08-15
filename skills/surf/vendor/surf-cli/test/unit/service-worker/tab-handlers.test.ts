import { beforeEach, describe, expect, it, vi } from "vitest";
import { createChromeMock, resetChromeMock } from "../../mocks/chrome";

vi.mock("../../../src/native/port-manager", () => ({
  initNativeMessaging: vi.fn(),
  postToNativeHost: vi.fn(),
}));

async function loadHandleMessage() {
  vi.resetModules();
  (globalThis as any).chrome = createChromeMock();
  const mod = await import("../../../src/service-worker/index");
  return mod.handleMessage;
}

async function loadNativeMessageHandler() {
  vi.resetModules();
  (globalThis as any).chrome = createChromeMock();
  const portManager = await import("../../../src/native/port-manager");
  const initNativeMessaging = vi.mocked(portManager.initNativeMessaging);
  await import("../../../src/service-worker/index");
  const handler = initNativeMessaging.mock.calls.at(-1)?.[0];
  if (!handler) throw new Error("initNativeMessaging handler was not registered");
  return handler;
}

describe("tab handlers", () => {
  beforeEach(() => {
    resetChromeMock();
  });

  it("registers the active tab when tabId is omitted", async () => {
    const handleMessage = await loadHandleMessage();
    const chrome = (globalThis as any).chrome;
    chrome.tabs.query.mockResolvedValue([
      { id: 123, url: "https://example.com/", active: true, windowId: 1 },
    ]);

    const result = await handleMessage({ type: "TABS_REGISTER", name: "work" }, {});

    expect(chrome.tabs.query).toHaveBeenCalledWith({ active: true, lastFocusedWindow: true });
    expect(result).toEqual({ success: true, name: "work", tabId: 123 });
  });

  it.each([
    "chrome://settings/",
    "edge://settings/",
    "brave://settings/",
    "arc://settings/",
    "helium://settings/",
    "chrome-extension://abc/page.html",
    "about:blank",
  ])("rejects registration for restricted URL %s", async (url) => {
    const handleMessage = await loadHandleMessage();
    const chrome = (globalThis as any).chrome;
    chrome.tabs.query.mockResolvedValue([{ id: 999, url, active: true, windowId: 1 }]);

    await expect(handleMessage({ type: "TABS_REGISTER", name: "settings" }, {})).rejects.toThrow(
      /restricted browser or extension page/,
    );
  });

  it("routes selector typing to the selected iframe", async () => {
    const handleMessage = await loadHandleMessage();
    const chrome = (globalThis as any).chrome;
    chrome.webNavigation.getAllFrames.mockResolvedValue([
      { frameId: 0, parentFrameId: -1, url: "https://example.com/" },
      { frameId: 7, parentFrameId: 0, url: "https://example.com/frame" },
    ]);

    await handleMessage({ type: "FRAME_SWITCH", tabId: 123, index: 0 }, {});
    chrome.tabs.sendMessage.mockResolvedValue({ success: true, contentEditable: false });

    const result = await handleMessage(
      {
        type: "SMART_TYPE",
        tabId: 123,
        selector: "#card-number",
        text: "4242",
        clear: true,
        submit: false,
      },
      {},
    );

    expect(chrome.tabs.sendMessage).toHaveBeenLastCalledWith(
      123,
      {
        type: "SMART_TYPE",
        selector: "#card-number",
        text: "4242",
        clear: true,
        submit: false,
      },
      { frameId: 7 },
    );
    expect(result).toEqual({ success: true, contentEditable: false });
  });

  it("moves tabs to the destination window", async () => {
    const handleMessage = await loadHandleMessage();
    const chrome = (globalThis as any).chrome;
    chrome.tabs.move.mockResolvedValue([{ id: 123, windowId: 456, index: 0 }]);

    const result = await handleMessage(
      { type: "TAB_MOVE", tabIds: "123,124", windowId: "456", index: "0" },
      {},
    );

    expect(chrome.tabs.move).toHaveBeenCalledWith([123, 124], { windowId: 456, index: 0 });
    expect(result).toMatchObject({
      success: true,
      moved: [123, 124],
      destinationWindowId: 456,
      index: 0,
    });
  });

  it("closes numeric tab ids parsed from strings", async () => {
    const handleMessage = await loadHandleMessage();
    const chrome = (globalThis as any).chrome;
    chrome.tabs.query.mockResolvedValue([{ id: 123, url: "https://example.com/", windowId: 1 }]);

    const result = await handleMessage({ type: "CLOSE_TAB", tabId: "123" }, {});

    expect(chrome.tabs.remove).toHaveBeenCalledWith([123]);
    expect(result).toEqual({ success: true, tabId: 123, alreadyClosed: false });
  });

  it("treats an already closed tab as successful cleanup", async () => {
    const handleMessage = await loadHandleMessage();
    const chrome = (globalThis as any).chrome;
    chrome.tabs.query.mockResolvedValue([]);

    const result = await handleMessage({ type: "CLOSE_TAB", tabId: "123" }, {});

    expect(chrome.tabs.remove).not.toHaveBeenCalled();
    expect(result).toEqual({ success: true, tabId: 123, alreadyClosed: true });
  });

  it("lets native CLOSE_TAB requests clean up already closed targets", async () => {
    const handleNativeMessage = await loadNativeMessageHandler();
    const chrome = (globalThis as any).chrome;
    chrome.tabs.get.mockRejectedValue(new Error("No tab with id: 123"));
    chrome.tabs.query.mockResolvedValue([]);

    const result = await handleNativeMessage({ type: "CLOSE_TAB", tabId: 123 });

    expect(chrome.tabs.get).not.toHaveBeenCalled();
    expect(chrome.tabs.remove).not.toHaveBeenCalled();
    expect(result).toMatchObject({ success: true, tabId: 123, alreadyClosed: true });
  });
});
