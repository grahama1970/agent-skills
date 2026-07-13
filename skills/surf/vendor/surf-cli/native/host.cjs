#!/usr/bin/env node
const net = require("net");
const fs = require("fs");
const path = require("path");
const os = require("os");
const https = require("https");
const { execSync } = require("child_process");
const { GoogleGenerativeAI } = require("@google/generative-ai");
const chatgptClient = require("./chatgpt-client.cjs");
const geminiTabClient = require("./gemini-tab-client.cjs");
const kimiTabClient = require("./kimi-tab-client.cjs");
const geminiClient = require("./gemini-client.cjs");
const perplexityClient = require("./perplexity-client.cjs");
const { mapToolToMessage, mapComputerAction, formatToolContent } = require("./host-helpers.cjs");
const { KeyedRequestQueue } = require("./ai-request-queue.cjs");
const { createBoundedLogger, summarizeExtensionMessage } = require("./host-log.cjs");

const SOCKET_PATH = "/tmp/surf.sock";

// Cross-platform image resize (macOS: sips, Linux: ImageMagick)
function resizeImage(filePath, maxSize) {
  const platform = process.platform;
  
  try {
    if (platform === "darwin") {
      // macOS: use sips
      execSync(`sips --resampleHeightWidthMax ${maxSize} "${filePath}" --out "${filePath}" 2>/dev/null`, { stdio: "pipe" });
      const sizeInfo = execSync(`sips -g pixelWidth -g pixelHeight "${filePath}" 2>/dev/null`, { encoding: "utf8" });
      const width = parseInt(sizeInfo.match(/pixelWidth:\s*(\d+)/)?.[1] || "0", 10);
      const height = parseInt(sizeInfo.match(/pixelHeight:\s*(\d+)/)?.[1] || "0", 10);
      return { success: true, width, height };
    } else {
      // Linux/other: use ImageMagick (try IM6 first, then IM7)
      try {
        execSync(`convert "${filePath}" -resize ${maxSize}x${maxSize}\\> "${filePath}"`, { stdio: "pipe" });
      } catch {
        // IM7 uses 'magick' as main command
        execSync(`magick "${filePath}" -resize ${maxSize}x${maxSize}\\> "${filePath}"`, { stdio: "pipe" });
      }
      // Get dimensions (IM7 may need 'magick identify' instead of just 'identify')
      let sizeInfo;
      try {
        sizeInfo = execSync(`identify -format "%w %h" "${filePath}"`, { encoding: "utf8" });
      } catch {
        sizeInfo = execSync(`magick identify -format "%w %h" "${filePath}"`, { encoding: "utf8" });
      }
      const [width, height] = sizeInfo.trim().split(" ").map(Number);
      return { success: true, width, height };
    }
  } catch (e) {
    return { success: false, error: e.message };
  }
}

const aiRequestQueue = new KeyedRequestQueue(2000);

function queueAiRequest(handler, key = "global") {
  return aiRequestQueue.enqueue(key, handler);
}
const AUTH_FILE = path.join(os.homedir(), ".pi", "agent", "auth.json");

const DEFAULT_RETRY_OPTIONS = {
  maxRetries: 3,
  initialDelayMs: 1000,
  maxDelayMs: 10000,
  backoffFactor: 2,
  retryableStatusCodes: [429, 500, 502, 503, 504]
};

async function withRetry(fn, retryOptions = DEFAULT_RETRY_OPTIONS, retryCount = 0) {
  try {
    return await fn();
  } catch (error) {
    if (retryCount >= retryOptions.maxRetries) {
      throw error;
    }
    
    let isRetryable = false;
    if (error instanceof Error) {
      const statusCodeMatch = error.message.match(/status code (\d+)/i);
      if (statusCodeMatch) {
        const statusCode = parseInt(statusCodeMatch[1], 10);
        isRetryable = retryOptions.retryableStatusCodes.includes(statusCode);
      } else {
        const isNetworkError = error.message.includes('network') || 
                          error.message.includes('timeout') ||
                          error.message.includes('connection');
        const isContentError = error.message.includes('exceeds maximum') ||
                          error.message.includes('too large') ||
                          error.message.includes('token limit');
        isRetryable = isNetworkError && !isContentError;
      }
    }
    
    if (!isRetryable) {
      throw error;
    }
    
    const delay = Math.min(
      retryOptions.initialDelayMs * Math.pow(retryOptions.backoffFactor, retryCount),
      retryOptions.maxDelayMs
    );
    const jitter = 0.8 + Math.random() * 0.4;
    const delayWithJitter = Math.floor(delay * jitter);
    
    await new Promise(resolve => setTimeout(resolve, delayWithJitter));
    return withRetry(fn, retryOptions, retryCount + 1);
  }
}

const AI_PROMPTS = {
  find: (query, pageContext) => `You are analyzing a web page's accessibility tree. Find the element matching the user's description.

Page Context:
${pageContext}

User Query: "${query}"

Respond with ONLY the element ref (e.g., "e5") or "NOT_FOUND" if no match.`,

  summary: (query, pageContext) => `Summarize this web page based on its accessibility tree.

Page Context:
${pageContext}

${query ? `Focus on: ${query}` : ""}

Keep the summary under 300 characters. Focus on the page's purpose and main content.`,

  extract: (query, pageContext) => `Extract structured data from this web page based on the user's request.

Page Context:
${pageContext}

User Request: "${query}"

Respond with valid JSON only.`
};

function detectQueryMode(query) {
  const q = query.toLowerCase();
  if (q.includes("find") || q.includes("where is") || q.includes("locate") || 
      q.includes("click") || q.includes("button") || q.includes("link") ||
      q.includes("input") || q.includes("field")) {
    return "find";
  }
  if (q.includes("summarize") || q.includes("summary") || q.includes("what is this") ||
      q.includes("about") || q.includes("describe") || q.includes("overview")) {
    return "summary";
  }
  if (q.includes("list") || q.includes("extract") || q.includes("all the") ||
      q.includes("get all") || q.includes("show all") || q.includes("json")) {
    return "extract";
  }
  return "summary";
}

let geminiClientCache = null;

function getGeminiClient(apiKey) {
  if (!geminiClientCache || geminiClientCache.apiKey !== apiKey) {
    geminiClientCache = { client: new GeminiClient(apiKey), apiKey };
  }
  return geminiClientCache.client;
}

class GeminiClient {
  constructor(apiKey) {
    this.genAI = new GoogleGenerativeAI(apiKey);
    this.model = this.genAI.getGenerativeModel({ model: "gemini-2.0-flash" });
  }

  async analyze(query, pageContext, options = {}) {
    const mode = options.mode || detectQueryMode(query);
    const promptFn = AI_PROMPTS[mode];
    const prompt = promptFn(query, pageContext);
    
    const result = await withRetry(async () => {
      const response = await this.model.generateContent(prompt);
      return response.response.text();
    });
    
    let content = result.trim();
    
    if (mode === "extract") {
      content = content.replace(/^```(?:json)?\n?|\n?```$/g, '').trim();
    }
    
    return { mode, content };
  }
}



async function handleApiRequest(msg, sendResponse) {
  const { url, method, headers, body, streamId } = msg;
  
  log(`API_REQUEST: ${method} ${url} streamId=${streamId}`);
  
  try {
    const urlObj = new URL(url);
    const options = {
      hostname: urlObj.hostname,
      port: urlObj.port || 443,
      path: urlObj.pathname + urlObj.search,
      method: method || "POST",
      headers: headers || {},
    };

    const req = https.request(options, (res) => {
      log(`API response status: ${res.statusCode}`);
      
      sendResponse({ 
        type: "API_RESPONSE_START", 
        streamId,
        status: res.statusCode,
        headers: res.headers,
      });

      res.on("data", (chunk) => {
        sendResponse({
          type: "API_RESPONSE_CHUNK",
          streamId,
          chunk: chunk.toString("utf8"),
        });
      });

      res.on("end", () => {
        sendResponse({
          type: "API_RESPONSE_END",
          streamId,
        });
      });

      res.on("error", (err) => {
        log(`API response error: ${err.message}`);
        sendResponse({
          type: "API_RESPONSE_ERROR",
          streamId,
          error: err.message,
        });
      });
    });

    req.on("error", (err) => {
      log(`API request error: ${err.message}`);
      sendResponse({
        type: "API_RESPONSE_ERROR",
        streamId,
        error: err.message,
      });
    });

    if (body) {
      req.write(typeof body === "string" ? body : JSON.stringify(body));
    }
    req.end();
  } catch (err) {
    log(`API_REQUEST error: ${err.message}`);
    sendResponse({
      type: "API_RESPONSE_ERROR",
      streamId,
      error: err.message,
    });
  }
}

const log = createBoundedLogger();

log("Host starting...");

try {
  fs.unlinkSync(SOCKET_PATH);
} catch {}

const pendingRequests = new Map();
const pendingToolRequests = new Map();
const activeStreams = new Map();
let requestCounter = 0;

function sendToolResponse(socket, id, result, error) {
  const response = { type: "tool_response", id };
  
  if (error) {
    response.error = { content: [{ type: "text", text: error }] };
  } else {
    response.result = { content: formatToolContent(result, log) };
  }
  
  try {
    socket.write(JSON.stringify(response) + "\n");
  } catch (e) {
    log(`Error sending tool_response: ${e.message}`);
  }
}

function handleStreamRequest(msg, socket) {
  const { streamType, options, id: originalId } = msg;
  const tabId = msg.tabId;
  const streamId = ++requestCounter;
  
  activeStreams.set(streamId, {
    socket,
    originalId,
    streamType,
  });
  
  writeMessage({
    type: streamType,
    streamId,
    options: options || {},
    tabId,
  });
  
  try {
    socket.write(JSON.stringify({ type: "stream_started", streamId }) + "\n");
  } catch (e) {
    log(`Error sending stream_started: ${e.message}`);
  }
}

function handleToolRequest(msg, socket) {
  const { method, params } = msg;
  const originalId = msg.id || null;
  
  if (method !== "execute_tool") {
    sendToolResponse(socket, originalId, null, `Unknown method: ${method}`);
    return;
  }
  
  const { tool, args } = params || {};
  const rawTabId = msg.tabId || params?.tabId || args?.tabId;
  const tabId = rawTabId !== undefined ? parseInt(rawTabId, 10) : undefined;
  const rawWindowId = msg.windowId || params?.windowId || args?.windowId;
  const windowId = rawWindowId !== undefined ? parseInt(rawWindowId, 10) : undefined;
  
  // Validate parsed IDs
  if (tabId !== undefined && isNaN(tabId)) {
    sendToolResponse(socket, originalId, null, "tabId must be a number");
    return;
  }
  if (windowId !== undefined && isNaN(windowId)) {
    sendToolResponse(socket, originalId, null, "windowId must be a number");
    return;
  }
  
  if (!tool) {
    sendToolResponse(socket, originalId, null, "No tool specified");
    return;
  }
  
  const extensionMsg = mapToolToMessage(tool, args, tabId);
  if (!extensionMsg) {
    sendToolResponse(socket, originalId, null, `Unknown tool: ${tool}`);
    return;
  }
  
  if (extensionMsg.type === "UNSUPPORTED_ACTION") {
    sendToolResponse(socket, originalId, null, extensionMsg.message);
    return;
  }
  
  if (extensionMsg.type === "LOCAL_WAIT") {
    setTimeout(() => {
      sendToolResponse(socket, originalId, { success: true }, null);
    }, extensionMsg.seconds * 1000);
    return;
  }
  
  if (extensionMsg.type === "BATCH_EXECUTE") {
    executeBatch(extensionMsg.actions, extensionMsg.tabId, socket, originalId);
    return;
  }
  
  if (extensionMsg.type === "AI_ANALYZE") {
    if (!extensionMsg.query || !extensionMsg.query.trim()) {
      sendToolResponse(socket, originalId, null, "Query is required for AI analysis");
      return;
    }
    
    const apiKey = process.env.GOOGLE_API_KEY;
    if (!apiKey) {
      sendToolResponse(socket, originalId, null, "GOOGLE_API_KEY environment variable not set. Export it with: export GOOGLE_API_KEY='your-key'");
      return;
    }
    
    const pageRequestId = ++requestCounter;
    pendingToolRequests.set(pageRequestId, {
      socket: null,
      originalId: null,
      tool: "read_page",
      onComplete: async (pageResult) => {
        if (pageResult.error) {
          sendToolResponse(socket, originalId, null, `Failed to read page: ${pageResult.error}`);
          return;
        }
        
        const pageContent = pageResult.pageContent || "";
        if (!pageContent) {
          sendToolResponse(socket, originalId, null, "No page content available");
          return;
        }
        
        try {
          const gemini = getGeminiClient(apiKey);
          const result = await gemini.analyze(extensionMsg.query, pageContent, { mode: extensionMsg.mode });
          
          if (result.mode === "find") {
            sendToolResponse(socket, originalId, { 
              ref: result.content === "NOT_FOUND" ? null : result.content,
              mode: result.mode,
              aiResult: true
            }, null);
          } else {
            sendToolResponse(socket, originalId, { 
              content: result.content,
              mode: result.mode,
              aiResult: true
            }, null);
          }
        } catch (err) {
          sendToolResponse(socket, originalId, null, `AI analysis failed: ${err.message}`);
        }
      }
    });
    writeMessage({ type: "READ_PAGE", options: { filter: "interactive" }, tabId: extensionMsg.tabId, id: pageRequestId });
    return;
  }
  
  if (extensionMsg.type === "CHATGPT_QUERY") {
    const { query, model, reasoning, withPage, file, timeout, sentinel, stablePolls, keepTab, targetTabId, noActivate } = extensionMsg;

    const chatgptQueueKey = `chatgpt:${targetTabId || extensionMsg.tabId || "auto"}`;
    queueAiRequest(async () => {
      let pageContext = null;
      if (withPage) {
        const pageResult = await new Promise((resolve) => {
          const pageId = ++requestCounter;
          pendingToolRequests.set(pageId, {
            socket: null,
            originalId: null,
            tool: "read_page",
            onComplete: resolve
          });
          writeMessage({ type: "GET_PAGE_TEXT", tabId: extensionMsg.tabId, id: pageId });
        });
        if (pageResult && !pageResult.error) {
          pageContext = {
            url: pageResult.url,
            text: pageResult.text || pageResult.pageContent || ""
          };
        }
      }

      let fullPrompt = query;
      if (pageContext) {
        fullPrompt = `Page: ${pageContext.url}\n\n${pageContext.text}\n\n---\n\n${query}`;
      }

      const result = await chatgptClient.query({
        prompt: fullPrompt,
        model,
        reasoning,
        file,
        timeout,
        sentinel,
        stablePolls,
        keepTab,
        noActivate,
        getCookies: () => new Promise((resolve) => {
          const cookieId = ++requestCounter;
          pendingToolRequests.set(cookieId, {
            socket: null,
            originalId: null,
            tool: "get_cookies",
            onComplete: (r) => resolve(r)
          });
          writeMessage({ type: "GET_CHATGPT_COOKIES", id: cookieId });
        }),
        createTab: () => new Promise((resolve) => {
          if (!keepTab) {
            const tabCreateId = ++requestCounter;
            pendingToolRequests.set(tabCreateId, {
              socket: null,
              originalId: null,
              tool: "create_tab",
              onComplete: (r) => resolve(r)
            });
            writeMessage({ type: "CHATGPT_NEW_TAB", noActivate, id: tabCreateId });
            return;
          }

          const requestedTabId = Number.parseInt(targetTabId || extensionMsg.tabId, 10);
          if (Number.isFinite(requestedTabId) && requestedTabId > 0) {
            if (noActivate) {
              // Skip SWITCH_TAB entirely — CDP attaches to the tab regardless of
              // active state, and SWITCH_TAB foregrounds the tab + window.
              resolve({ tabId: requestedTabId, reused: true, activated: false, tabWasCreated: false });
              return;
            }
            const switchId = ++requestCounter;
            pendingToolRequests.set(switchId, {
              socket: null,
              originalId: null,
              tool: "switch_tab",
              onComplete: (r) => {
                if (r?.error) {
                  const tabCreateId = ++requestCounter;
                  pendingToolRequests.set(tabCreateId, {
                    socket: null,
                    originalId: null,
                    tool: "create_tab",
                    onComplete: (created) => resolve(created)
                  });
                  writeMessage({ type: "CHATGPT_NEW_TAB", noActivate, id: tabCreateId });
                  return;
                }
                resolve({ tabId: requestedTabId, reused: true, activated: true, tabWasCreated: false });
              }
            });
            writeMessage({ type: "SWITCH_TAB", tabId: requestedTabId, id: switchId });
            return;
          }

          const listId = ++requestCounter;
          pendingToolRequests.set(listId, {
            socket: null,
            originalId: null,
            tool: "list_tabs",
            onComplete: (tabsResult) => {
              const tabs = tabsResult?.tabs || [];
              const chatgptTab = tabs
                .filter((tab) => typeof tab.url === "string" && tab.url.startsWith("https://chatgpt.com/"))
                .sort((a, b) => (b.id || 0) - (a.id || 0))[0];

              if (!chatgptTab?.id) {
                const tabCreateId = ++requestCounter;
                pendingToolRequests.set(tabCreateId, {
                  socket: null,
                  originalId: null,
                  tool: "create_tab",
                  onComplete: (r) => resolve(r)
                });
                writeMessage({ type: "CHATGPT_NEW_TAB", noActivate, id: tabCreateId });
                return;
              }

              if (noActivate) {
                resolve({ tabId: chatgptTab.id, reused: true, url: chatgptTab.url, activated: false, tabWasCreated: false });
                return;
              }

              const switchId = ++requestCounter;
              pendingToolRequests.set(switchId, {
                socket: null,
                originalId: null,
                tool: "switch_tab",
                onComplete: () => resolve({ tabId: chatgptTab.id, reused: true, url: chatgptTab.url, activated: true, tabWasCreated: false })
              });
              writeMessage({ type: "SWITCH_TAB", tabId: chatgptTab.id, id: switchId });
            }
          });
          writeMessage({ type: "LIST_TABS", id: listId });
        }),
        closeTab: (tabIdToClose) => new Promise((resolve) => {
          const tabCloseId = ++requestCounter;
          pendingToolRequests.set(tabCloseId, {
            socket: null,
            originalId: null,
            tool: "close_tab",
            onComplete: (r) => resolve(r)
          });
          writeMessage({ type: "CHATGPT_CLOSE_TAB", tabId: tabIdToClose, id: tabCloseId });
        }),
        cdpEvaluate: (tabId, expression) => new Promise((resolve) => {
          const evalId = ++requestCounter;
          pendingToolRequests.set(evalId, {
            socket: null,
            originalId: null,
            tool: "cdp_evaluate",
            onComplete: (r) => resolve(r)
          });
          writeMessage({ type: "CHATGPT_EVALUATE", tabId, expression, id: evalId });
        }),
        cdpCommand: (tabId, method, params) => new Promise((resolve) => {
          const cmdId = ++requestCounter;
          pendingToolRequests.set(cmdId, {
            socket: null,
            originalId: null,
            tool: "cdp_command",
            onComplete: (r) => resolve(r)
          });
          writeMessage({ type: "CHATGPT_CDP_COMMAND", tabId, method, params, id: cmdId });
        }),
        log: (msg) => log(`[chatgpt] ${msg}`)
      });
      
      return result;
    }, chatgptQueueKey).then((result) => {
      sendToolResponse(socket, originalId, {
        response: result.response,
        model: result.model,
        requestedModel: result.requestedModel,
        selectedModel: result.selectedModel,
        modelSelectionStatus: result.modelSelectionStatus,
        modelSelectionError: result.modelSelectionError,
        reasoning: result.reasoning,
        requestedReasoning: result.requestedReasoning,
        selectedReasoning: result.selectedReasoning,
        reasoningSelectionStatus: result.reasoningSelectionStatus,
        reasoningSelectionError: result.reasoningSelectionError,
        tabId: result.tabId,
        controlledTabId: result.controlledTabId,
        conversationUrl: result.conversationUrl,
        messageId: result.messageId,
        responseSource: result.responseSource,
        sentinel: result.sentinel,
        hasSentinel: result.hasSentinel,
        tookMs: result.tookMs,
        activated: result.activated,
        tabWasCreated: result.tabWasCreated,
        noActivate: result.noActivate
      }, null);
    }).catch((err) => {
      sendToolResponse(socket, originalId, null, err.message);
    });
    
    return;
  }

  if (extensionMsg.type === "CHATGPT_EXTRACT") {
    const requestedTabId = Number.parseInt(extensionMsg.targetTabId || extensionMsg.tabId, 10);
    if (!Number.isFinite(requestedTabId) || requestedTabId <= 0) {
      sendToolResponse(socket, originalId, null, "--tab-id required");
      return;
    }

    chatgptClient.extractAssistantResponse({
      tabId: requestedTabId,
      sentinel: extensionMsg.sentinel,
      timeout: extensionMsg.timeout,
      wait: extensionMsg.wait === true,
      stablePolls: extensionMsg.stablePolls,
      noActivate: extensionMsg.noActivate === true,
      cdpEvaluate: (tabId, expression) => new Promise((resolve) => {
        const evalId = ++requestCounter;
        pendingToolRequests.set(evalId, {
          socket: null,
          originalId: null,
          tool: "cdp_evaluate",
          onComplete: (r) => resolve(r)
        });
        writeMessage({ type: "CHATGPT_EVALUATE", tabId, expression, id: evalId });
      }),
    }).then((result) => {
      sendToolResponse(socket, originalId, {
        response: result.response,
        tabId: result.tabId,
        controlledTabId: result.controlledTabId,
        messageId: result.messageId,
        responseSource: result.responseSource,
        sentinel: result.sentinel,
        hasSentinel: result.hasSentinel,
        pageTextContainsSentinel: result.pageTextContainsSentinel,
        stopVisible: result.stopVisible,
        finished: result.finished,
        turnIndex: result.turnIndex,
      }, null);
    }).catch((err) => {
      sendToolResponse(socket, originalId, null, err.message);
    });

    return;
  }
  
  if (extensionMsg.type === "GEMINI_TAB_QUERY") {
    const { query, timeout, sentinel, stablePolls, keepTab, targetTabId, noActivate } = extensionMsg;

    queueAiRequest(async () => {
      const result = await geminiTabClient.query({
        prompt: query,
        timeout,
        sentinel,
        stablePolls,
        keepTab,
        noActivate,
        createTab: () => new Promise((resolve) => {
          const requestedTabId = Number.parseInt(targetTabId || extensionMsg.tabId, 10);
          if (Number.isFinite(requestedTabId) && requestedTabId > 0) {
            if (noActivate) {
              resolve({ tabId: requestedTabId, reused: true, activated: false, tabWasCreated: false });
              return;
            }
            const switchId = ++requestCounter;
            pendingToolRequests.set(switchId, {
              socket: null,
              originalId: null,
              tool: "switch_tab",
              onComplete: (r) => {
                if (r?.error) {
                  resolve({ tabId: requestedTabId, reused: true, activated: false, tabWasCreated: false });
                  return;
                }
                resolve({ tabId: requestedTabId, reused: true, activated: true, tabWasCreated: false });
              }
            });
            writeMessage({ type: "SWITCH_TAB", tabId: requestedTabId, id: switchId });
            return;
          }

          const listId = ++requestCounter;
          pendingToolRequests.set(listId, {
            socket: null,
            originalId: null,
            tool: "list_tabs",
            onComplete: (tabsResult) => {
              const tabs = tabsResult?.tabs || [];
              const geminiTab = tabs
                .filter((tab) => typeof tab.url === "string" && tab.url.includes("gemini.google.com"))
                .sort((a, b) => (b.id || 0) - (a.id || 0))[0];

              if (!geminiTab?.id) {
                resolve(null);
                return;
              }

              if (noActivate) {
                resolve({ tabId: geminiTab.id, reused: true, url: geminiTab.url, activated: false, tabWasCreated: false });
                return;
              }

              const switchId = ++requestCounter;
              pendingToolRequests.set(switchId, {
                socket: null,
                originalId: null,
                tool: "switch_tab",
                onComplete: () => resolve({ tabId: geminiTab.id, reused: true, url: geminiTab.url, activated: true, tabWasCreated: false })
              });
              writeMessage({ type: "SWITCH_TAB", tabId: geminiTab.id, id: switchId });
            }
          });
          writeMessage({ type: "LIST_TABS", id: listId });
        }),
        closeTab: () => Promise.resolve(),
        cdpEvaluate: (tabId, expression) => new Promise((resolve) => {
          const evalId = ++requestCounter;
          pendingToolRequests.set(evalId, {
            socket: null,
            originalId: null,
            tool: "cdp_evaluate",
            onComplete: (r) => resolve(r)
          });
          writeMessage({ type: "CHATGPT_EVALUATE", tabId, expression, id: evalId });
        }),
        cdpCommand: (tabId, method, params) => new Promise((resolve) => {
          const cmdId = ++requestCounter;
          pendingToolRequests.set(cmdId, {
            socket: null,
            originalId: null,
            tool: "cdp_command",
            onComplete: (r) => resolve(r)
          });
          writeMessage({ type: "CHATGPT_CDP_COMMAND", tabId, method, params, id: cmdId });
        }),
        log: (msg) => log(`[gemini_tab] ${msg}`)
      });

      return result;
    }).then((result) => {
      sendToolResponse(socket, originalId, {
        response: result.response,
        model: result.model,
        tabId: result.tabId,
        controlledTabId: result.controlledTabId,
        conversationUrl: result.conversationUrl,
        messageId: result.messageId,
        responseSource: result.responseSource,
        sentinel: result.sentinel,
        hasSentinel: result.hasSentinel,
        tookMs: result.tookMs,
        activated: result.activated,
        tabWasCreated: result.tabWasCreated,
        noActivate: result.noActivate
      }, null);
    }).catch((err) => {
      sendToolResponse(socket, originalId, null, err.message);
    });

    return;
  }


  if (extensionMsg.type === "KIMI_TAB_QUERY") {
    const { query, timeout, sentinel, stablePolls, keepTab, targetTabId, noActivate } = extensionMsg;

    queueAiRequest(async () => {
      const result = await kimiTabClient.query({
        prompt: query,
        timeout,
        sentinel,
        stablePolls,
        keepTab,
        noActivate,
        createTab: () => new Promise((resolve) => {
          const requestedTabId = Number.parseInt(targetTabId || extensionMsg.tabId, 10);
          if (Number.isFinite(requestedTabId) && requestedTabId > 0) {
            if (noActivate) {
              resolve({ tabId: requestedTabId, reused: true, activated: false, tabWasCreated: false });
              return;
            }
            const switchId = ++requestCounter;
            pendingToolRequests.set(switchId, {
              socket: null,
              originalId: null,
              tool: "switch_tab",
              onComplete: (r) => {
                if (r?.error) {
                  resolve({ tabId: requestedTabId, reused: true, activated: false, tabWasCreated: false });
                  return;
                }
                resolve({ tabId: requestedTabId, reused: true, activated: true, tabWasCreated: false });
              }
            });
            writeMessage({ type: "SWITCH_TAB", tabId: requestedTabId, id: switchId });
            return;
          }

          const listId = ++requestCounter;
          pendingToolRequests.set(listId, {
            socket: null,
            originalId: null,
            tool: "list_tabs",
            onComplete: (tabsResult) => {
              const tabs = tabsResult?.tabs || [];
              const kimiTab = tabs
                .filter((tab) => typeof tab.url === "string" && tab.url.includes("kimi.com") && (tab.url.includes("/chat") || tab.url.includes("/agent")))
                .sort((a, b) => (b.id || 0) - (a.id || 0))[0];

              if (!kimiTab?.id) {
                resolve(null);
                return;
              }

              if (noActivate) {
                resolve({ tabId: kimiTab.id, reused: true, url: kimiTab.url, activated: false, tabWasCreated: false });
                return;
              }

              const switchId = ++requestCounter;
              pendingToolRequests.set(switchId, {
                socket: null,
                originalId: null,
                tool: "switch_tab",
                onComplete: () => resolve({ tabId: kimiTab.id, reused: true, url: kimiTab.url, activated: true, tabWasCreated: false })
              });
              writeMessage({ type: "SWITCH_TAB", tabId: kimiTab.id, id: switchId });
            }
          });
          writeMessage({ type: "LIST_TABS", id: listId });
        }),
        closeTab: () => Promise.resolve(),
        cdpEvaluate: (tabId, expression) => new Promise((resolve) => {
          const evalId = ++requestCounter;
          pendingToolRequests.set(evalId, {
            socket: null,
            originalId: null,
            tool: "cdp_evaluate",
            onComplete: (r) => resolve(r)
          });
          writeMessage({ type: "CHATGPT_EVALUATE", tabId, expression, id: evalId });
        }),
        cdpCommand: (tabId, method, params) => new Promise((resolve) => {
          const cmdId = ++requestCounter;
          pendingToolRequests.set(cmdId, {
            socket: null,
            originalId: null,
            tool: "cdp_command",
            onComplete: (r) => resolve(r)
          });
          writeMessage({ type: "CHATGPT_CDP_COMMAND", tabId, method, params, id: cmdId });
        }),
        log: (msg) => log(`[kimi_tab] ${msg}`)
      });

      return result;
    }).then((result) => {
      sendToolResponse(socket, originalId, {
        response: result.response,
        model: result.model,
        tabId: result.tabId,
        controlledTabId: result.controlledTabId,
        conversationUrl: result.conversationUrl,
        messageId: result.messageId,
        responseSource: result.responseSource,
        sentinel: result.sentinel,
        hasSentinel: result.hasSentinel,
        tookMs: result.tookMs,
        activated: result.activated,
        tabWasCreated: result.tabWasCreated,
        noActivate: result.noActivate
      }, null);
    }).catch((err) => {
      sendToolResponse(socket, originalId, null, err.message);
    });

    return;
  }

  if (extensionMsg.type === "PERPLEXITY_QUERY") {
    const { query, mode, model, withPage, timeout, keepTab = true, noActivate = false } = extensionMsg;
    
    queueAiRequest(async () => {
      let pageContext = null;
      if (withPage) {
        const pageResult = await new Promise((resolve) => {
          const pageId = ++requestCounter;
          pendingToolRequests.set(pageId, {
            socket: null,
            originalId: null,
            tool: "read_page",
            onComplete: resolve
          });
          writeMessage({ type: "GET_PAGE_TEXT", tabId: extensionMsg.tabId, id: pageId });
        });
        if (pageResult && !pageResult.error) {
          pageContext = {
            url: pageResult.url,
            text: pageResult.text || pageResult.pageContent || ""
          };
        }
      }
      
      let fullPrompt = query;
      if (pageContext) {
        fullPrompt = `Page: ${pageContext.url}\n\n${pageContext.text}\n\n---\n\n${query}`;
      }
      
      const result = await perplexityClient.query({
        prompt: fullPrompt,
        mode: mode || 'search',
        model,
        timeout: timeout || 120000,
        keepTab: keepTab !== false,
        createTab: () => new Promise((resolve) => {
          const tabCreateId = ++requestCounter;
          pendingToolRequests.set(tabCreateId, {
            socket: null,
            originalId: null,
            tool: "create_tab",
            onComplete: (r) => resolve(r)
          });
          writeMessage({ type: "PERPLEXITY_NEW_TAB", noActivate, id: tabCreateId });
        }),
        closeTab: (tabIdToClose) => new Promise((resolve) => {
          const tabCloseId = ++requestCounter;
          pendingToolRequests.set(tabCloseId, {
            socket: null,
            originalId: null,
            tool: "close_tab",
            onComplete: (r) => resolve(r)
          });
          writeMessage({ type: "PERPLEXITY_CLOSE_TAB", tabId: tabIdToClose, id: tabCloseId });
        }),
        cdpEvaluate: (tabId, expression) => new Promise((resolve) => {
          const evalId = ++requestCounter;
          pendingToolRequests.set(evalId, {
            socket: null,
            originalId: null,
            tool: "cdp_evaluate",
            onComplete: (r) => resolve(r)
          });
          writeMessage({ type: "PERPLEXITY_EVALUATE", tabId, expression, id: evalId });
        }),
        cdpCommand: (tabId, method, params) => new Promise((resolve) => {
          const cmdId = ++requestCounter;
          pendingToolRequests.set(cmdId, {
            socket: null,
            originalId: null,
            tool: "cdp_command",
            onComplete: (r) => resolve(r)
          });
          writeMessage({ type: "PERPLEXITY_CDP_COMMAND", tabId, method, params, id: cmdId });
        }),
        log: (msg) => log(`[perplexity] ${msg}`)
      });
      
      return result;
    }).then((result) => {
      sendToolResponse(socket, originalId, {
        response: result.response,
        sources: result.sources,
        url: result.url,
        mode: result.mode,
        model: result.model,
        tookMs: result.tookMs,
        tabId: result.tabId,
        keepTab: result.keepTab
      }, null);
    }).catch((err) => {
      sendToolResponse(socket, originalId, null, err.message);
    });
    
    return;
  }
  
  if (extensionMsg.type === "GEMINI_QUERY") {
    const { query, model, withPage, file, generateImage, editImage, output, youtube, aspectRatio, timeout } = extensionMsg;
    
    queueAiRequest(async () => {
      // 1. Get page context if requested
      let pageContext = null;
      if (withPage) {
        const pageResult = await new Promise((resolve) => {
          const pageId = ++requestCounter;
          pendingToolRequests.set(pageId, {
            socket: null,
            originalId: null,
            tool: "get_page_text",
            onComplete: resolve
          });
          writeMessage({ type: "GET_PAGE_TEXT", tabId: extensionMsg.tabId, id: pageId });
        });
        if (pageResult && !pageResult.error) {
          pageContext = {
            url: pageResult.url,
            text: pageResult.text || pageResult.pageContent || ""
          };
        }
      }
      
      // 2. Build full prompt
      let fullPrompt = query || "";
      if (pageContext) {
        fullPrompt = `Page: ${pageContext.url}\n\n${pageContext.text}\n\n---\n\n${fullPrompt}`;
      }
      
      // 3. Call Gemini client
      const result = await geminiClient.query({
        prompt: fullPrompt,
        model: model || "gemini-3-pro",
        file,
        generateImage,
        editImage,
        output,
        youtube,
        aspectRatio,
        timeout: timeout || 300000,
        getCookies: () => new Promise((resolve) => {
          const cookieId = ++requestCounter;
          pendingToolRequests.set(cookieId, {
            socket: null,
            originalId: null,
            tool: "get_cookies",
            onComplete: (r) => resolve(r)
          });
          writeMessage({ type: "GET_GOOGLE_COOKIES", id: cookieId });
        }),
        log: (msg) => log(`[gemini] ${msg}`)
      });
      
      return result;
    }).then((result) => {
      const response = { 
        response: result.response, 
        model: result.model, 
        tookMs: result.tookMs 
      };
      if (result.imagePath) {
        response.imagePath = result.imagePath;
      }
      sendToolResponse(socket, originalId, response, null);
    }).catch((err) => {
      sendToolResponse(socket, originalId, null, err.message);
    });
    
    return;
  }
  
  if (extensionMsg.type === "EXECUTE_KEY_REPEAT") {
    const { key, repeat, tabId: tid } = extensionMsg;
    let completed = 0;
    let lastError = null;
    
    const sendNextKey = () => {
      if (completed >= repeat) {
        if (lastError) {
          sendToolResponse(socket, originalId, null, `Key repeat failed: ${lastError}`);
        } else {
          sendToolResponse(socket, originalId, { success: true }, null);
        }
        return;
      }
      const id = ++requestCounter;
      pendingToolRequests.set(id, { 
        socket: null,
        originalId: null,
        tool,
        onComplete: (result) => {
          if (result.error) lastError = result.error;
          completed++;
          setTimeout(sendNextKey, 50);
        }
      });
      writeMessage({ type: "EXECUTE_KEY", key, tabId: tid, id });
    };
    sendNextKey();
    return;
  }
  
  if (extensionMsg.type === "NAMED_TAB_SWITCH" || extensionMsg.type === "NAMED_TAB_CLOSE") {
    const { name, type: opType } = extensionMsg;
    const lookupId = ++requestCounter;
    pendingToolRequests.set(lookupId, {
      socket: null,
      originalId: null,
      tool: "tabs_get_by_name",
      onComplete: (result) => {
        if (result.error || !result.tabId) {
          sendToolResponse(socket, originalId, null, result.error || `No tab found with name "${name}"`);
          return;
        }
        const actionId = ++requestCounter;
        const actionType = opType === "NAMED_TAB_SWITCH" ? "SWITCH_TAB" : "CLOSE_TAB";
        pendingToolRequests.set(actionId, { socket, originalId, tool, tabId: result.tabId });
        writeMessage({ type: actionType, tabId: result.tabId, id: actionId });
      }
    });
    writeMessage({ type: "TABS_GET_BY_NAME", name, id: lookupId });
    return;
  }
  
  const id = ++requestCounter;
  const pendingData = { 
    socket, 
    originalId, 
    tool, 
    savePath: extensionMsg.savePath || args?.savePath,
    autoScreenshot: args?.autoScreenshot,
    fullRes: extensionMsg.fullRes || args?.fullRes,
    maxSize: extensionMsg.maxSize || args?.maxSize,
    tabId: extensionMsg.tabId || tabId
  };
  pendingToolRequests.set(id, pendingData);
  
  // Include windowId for tab resolution scoping
  const finalMsg = { ...extensionMsg, id };
  if (windowId) finalMsg.windowId = windowId;
  writeMessage(finalMsg);
}

function executeBatch(actions, tabId, socket, originalId) {
  const results = [];
  const DELAY_MS = 100;
  let currentIndex = 0;
  
  function executeNextAction() {
    if (currentIndex >= actions.length) {
      sendToolResponse(socket, originalId, {
        success: true,
        completedActions: actions.length,
        totalActions: actions.length,
        results,
      }, null);
      return;
    }
    
    const action = actions[currentIndex];
    const toolName = mapBatchActionToTool(action);
    const toolArgs = mapBatchActionToArgs(action);
    
    const extensionMsg = mapToolToMessage(toolName, toolArgs, tabId);
    if (!extensionMsg || extensionMsg.type === "UNSUPPORTED_ACTION") {
      results.push({ index: currentIndex, type: action.type, success: false, error: "Unsupported action" });
      sendToolResponse(socket, originalId, {
        success: false,
        completedActions: currentIndex,
        totalActions: actions.length,
        results,
        error: `Action ${currentIndex} failed: Unsupported action type "${action.type}"`,
      }, null);
      return;
    }
    
    if (extensionMsg.type === "LOCAL_WAIT") {
      results.push({ index: currentIndex, type: action.type, success: true });
      currentIndex++;
      setTimeout(executeNextAction, extensionMsg.seconds * 1000);
      return;
    }
    
    const id = ++requestCounter;
    pendingToolRequests.set(id, {
      socket: null,
      originalId: null,
      tool: toolName,
      onComplete: (result) => {
        if (result.error) {
          results.push({ index: currentIndex, type: action.type, success: false, error: result.error });
          sendToolResponse(socket, originalId, {
            success: false,
            completedActions: currentIndex,
            totalActions: actions.length,
            results,
            error: `Action ${currentIndex} failed: ${result.error}`,
          }, null);
          return;
        }
        
        results.push({ index: currentIndex, type: action.type, success: true });
        currentIndex++;
        
        setTimeout(executeNextAction, DELAY_MS);
      }
    });
    
    writeMessage({ ...extensionMsg, id });
  }
  
  executeNextAction();
}

function mapBatchActionToTool(action) {
  const map = {
    click: "left_click",
    type: "type",
    key: "key",
    wait: "wait",
    scroll: "scroll",
    screenshot: "screenshot",
    navigate: "navigate",
  };
  return map[action.type] || action.type;
}

function mapBatchActionToArgs(action) {
  switch (action.type) {
    case "click":
      return { ref: action.ref, selector: action.selector, x: action.x, y: action.y };
    case "type":
      return { text: action.text };
    case "key":
      return { key: action.key };
    case "wait":
      return { duration: (action.ms || 1000) / 1000 };
    case "scroll":
      return { scroll_direction: action.direction };
    case "screenshot":
      return { savePath: action.output };
    case "navigate":
      return { url: action.url };
    default:
      return action;
  }
}

function writeMessage(msg) {
  const json = JSON.stringify(msg);
  const len = Buffer.byteLength(json);
  const buf = Buffer.alloc(4 + len);
  buf.writeUInt32LE(len, 0);
  buf.write(json, 4);
  process.stdout.write(buf);
}

let inputBuffer = Buffer.alloc(0);

function processInput() {
  while (inputBuffer.length >= 4) {
    const msgLen = inputBuffer.readUInt32LE(0);
    if (inputBuffer.length < 4 + msgLen) break;
    
    const jsonStr = inputBuffer.slice(4, 4 + msgLen).toString("utf8");
    inputBuffer = inputBuffer.slice(4 + msgLen);
    
    try {
      const msg = JSON.parse(jsonStr);
      log(`Received from extension: ${summarizeExtensionMessage(msg, Buffer.byteLength(jsonStr))}`);
      
      if (msg.type === "GET_AUTH") {
        log("Handling GET_AUTH from extension");
        try {
          if (fs.existsSync(AUTH_FILE)) {
            const authData = JSON.parse(fs.readFileSync(AUTH_FILE, "utf8"));
            writeMessage({ id: msg.id, auth: authData, hint: null });
          } else {
            writeMessage({ 
              id: msg.id, 
              auth: null, 
              hint: "No OAuth credentials found. Run 'pi --login anthropic' in terminal to authenticate with Claude Max."
            });
          }
        } catch (e) {
          log(`Error reading auth file: ${e.message}`);
          writeMessage({ 
            id: msg.id, 
            auth: null, 
            hint: "Failed to read auth credentials. Run 'pi --login anthropic' in terminal to authenticate."
          });
        }
        return;
      }
      
      if (msg.type === "API_REQUEST") {
        handleApiRequest(msg, writeMessage);
        return;
      }
      
      if (msg.type === "STREAM_EVENT") {
        const stream = activeStreams.get(msg.streamId);
        if (stream) {
          try {
            stream.socket.write(JSON.stringify(msg.event) + "\n");
          } catch (e) {
            log(`Error forwarding stream event: ${e.message}`);
            activeStreams.delete(msg.streamId);
            writeMessage({ type: "STREAM_STOP", streamId: msg.streamId });
          }
        }
        return;
      }
      
      if (msg.type === "STREAM_ERROR") {
        const stream = activeStreams.get(msg.streamId);
        if (stream) {
          try {
            stream.socket.write(JSON.stringify({ error: msg.error }) + "\n");
          } catch (e) {}
          activeStreams.delete(msg.streamId);
        }
        return;
      }
      
      
      if (msg.id && pendingToolRequests.has(msg.id)) {
        const pending = pendingToolRequests.get(msg.id);
        pendingToolRequests.delete(msg.id);
        
        if (pending.onComplete) {
          pending.onComplete(msg);
        } else {
          const { socket, originalId, savePath, autoScreenshot, tabId: storedTabId } = pending;
          const tabId = storedTabId || msg._resolvedTabId;
          
          if (savePath && msg.base64) {
            try {
              const dir = path.dirname(savePath);
              if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
              fs.writeFileSync(savePath, Buffer.from(msg.base64, "base64"));
              const origWidth = msg.width || 0;
              const origHeight = msg.height || 0;
              const maxSize = pending.maxSize || 1200;
              const skipResize = pending.fullRes;
              
              let finalDims = origWidth && origHeight ? `${origWidth}x${origHeight}` : "";
              if (!skipResize && (origWidth > maxSize || origHeight > maxSize)) {
                const result = resizeImage(savePath, maxSize);
                if (result.success) {
                  finalDims = `${result.width}x${result.height}, from ${origWidth}x${origHeight}`;
                }
              }
              sendToolResponse(socket, originalId, {
                message: `Saved to ${savePath} (${finalDims})`,
                path: savePath,
                screenshotId: msg.screenshotId,  // Preserve for upload_image workflow
                method: msg.method,
                authoritative: msg.authoritative,
                selector: msg.selector,
                nearest: msg.nearest,
                resolvedTag: msg.resolvedTag,
                resolvedDataQid: msg.resolvedDataQid,
                scrollHeight: msg.scrollHeight,
                clientHeight: msg.clientHeight,
                clientWidth: msg.clientWidth,
                segments: msg.segments,
                offsets: msg.offsets,
                image: origWidth && origHeight ? { width: origWidth, height: origHeight } : undefined,
              }, null);
            } catch (e) {
              sendToolResponse(socket, originalId, null, `Failed to save: ${e.message}`);
            }
          } else if (autoScreenshot && tabId && !msg.error && !msg.base64) {
            
            const screenshotId = ++requestCounter;
            const screenshotPath = `/tmp/pi-auto-${Date.now()}.png`;
            
            const autoFiles = fs.readdirSync("/tmp")
              .filter(f => f.startsWith("pi-auto-") && f.endsWith(".png"))
              .map(f => ({ name: f, time: parseInt(f.match(/pi-auto-(\d+)\.png/)?.[1] || "0", 10) }))
              .sort((a, b) => b.time - a.time);
            if (autoFiles.length >= 10) {
              autoFiles.slice(9).forEach(f => {
                try { fs.unlinkSync(path.join("/tmp", f.name)); } catch (e) {}
              });
            }
            pendingToolRequests.set(screenshotId, {
              socket: null,
              originalId: null,
              tool: "screenshot",
              onComplete: (screenshotMsg) => {
                if (screenshotMsg.base64) {
                  try {
                    fs.writeFileSync(screenshotPath, Buffer.from(screenshotMsg.base64, "base64"));
                    const origW = screenshotMsg.width || 0;
                    const origH = screenshotMsg.height || 0;
                    let finalW = origW, finalH = origH;
                    const maxSize = 1200;
                    if (origW > maxSize || origH > maxSize) {
                      const result = resizeImage(screenshotPath, maxSize);
                      if (result.success) {
                        finalW = result.width;
                        finalH = result.height;
                      }
                    }
                    sendToolResponse(socket, originalId, {
                      ...msg,
                      autoScreenshot: { path: screenshotPath, width: finalW, height: finalH, originalWidth: origW, originalHeight: origH }
                    }, null);
                  } catch (e) {
                    sendToolResponse(socket, originalId, { ...msg, autoScreenshotError: e.message }, null);
                  }
                } else {
                  const errMsg = screenshotMsg.error || "Failed to capture";
                  sendToolResponse(socket, originalId, { ...msg, autoScreenshotError: errMsg }, null);
                }
              }
            });
            setTimeout(() => writeMessage({ type: "EXECUTE_SCREENSHOT", tabId, id: screenshotId }), 500);
            return;
          } else if (msg.results && msg.savePath) {
            try {
              const dir = msg.savePath;
              if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
              
              for (const result of msg.results) {
                if (result.screenshotBase64 && result.hostname) {
                  const ssPath = path.join(dir, `${result.hostname}.png`);
                  fs.writeFileSync(ssPath, Buffer.from(result.screenshotBase64, "base64"));
                  result.screenshot = ssPath;
                  delete result.screenshotBase64;
                  delete result.hostname;
                }
              }
              delete msg.savePath;
              sendToolResponse(socket, originalId, msg, null);
            } catch (e) {
              sendToolResponse(socket, originalId, null, `Failed to save screenshots: ${e.message}`);
            }
          } else {
            const isPureError = msg.error && !msg.success && !msg.base64 && 
                                !msg.pageContent && !msg.tabs && !msg.text &&
                                !msg.output && !msg.messages && !msg.requests;
            
            if (isPureError) {
              sendToolResponse(socket, originalId, null, msg.error);
            } else {
              sendToolResponse(socket, originalId, msg, null);
            }
          }
        }
      } else if (msg.id && pendingRequests.has(msg.id)) {
        const { socket } = pendingRequests.get(msg.id);
        try {
          socket.write(JSON.stringify(msg) + "\n");
        } catch (e) {
          log(`Error writing to CLI socket: ${e.message}`);
        }
        pendingRequests.delete(msg.id);
      }
    } catch (e) {
      log(`Error parsing message: ${e.message}`);
    }
  }
}

process.stdin.on("readable", () => {
  let chunk;
  while ((chunk = process.stdin.read()) !== null) {
    inputBuffer = Buffer.concat([inputBuffer, chunk]);
    processInput();
  }
});

// Track connected CLI sockets for disconnect notification
const connectedSockets = new Set();

process.stdin.on("end", () => {
  // Extension native port closed (reload, MV3 restart, crash). Exit so Chrome
  // can spawn a fresh host on reconnect. Do not broadcast a fatal
  // extension_disconnected — long chatgpt polls recover via CLI extract fallback.
  log("stdin ended (extension disconnected); shutting down host for reconnect");
  for (const socket of Array.from(connectedSockets)) {
    try {
      socket.end();
    } catch (e) {
      // Socket may already be closed
    }
  }
  try {
    server.close();
  } catch (e) {
    // ignore
  }
  try {
    fs.unlinkSync(SOCKET_PATH);
  } catch (e) {
    // ignore
  }
  process.exit(0);
});

process.stdin.on("error", (err) => {
  log(`stdin error: ${err.message}`);
});

process.stdout.on("error", (err) => {
  log(`stdout error: ${err.message}`);
});

const server = net.createServer((socket) => {
  log("CLI client connected");
  connectedSockets.add(socket);
  socket.on("close", () => connectedSockets.delete(socket));
  
  let dataBuffer = "";

  socket.on("data", (data) => {
    dataBuffer += data.toString();
    const lines = dataBuffer.split("\n");
    dataBuffer = lines.pop() || "";

    for (const line of lines) {
      if (!line.trim()) continue;
      try {
        const msg = JSON.parse(line);
        
        if (msg.type === "GET_AUTH") {
          log("Handling GET_AUTH locally");
          try {
            if (fs.existsSync(AUTH_FILE)) {
              const authData = JSON.parse(fs.readFileSync(AUTH_FILE, "utf8"));
              socket.write(JSON.stringify({ 
                id: msg.id || 0,
                auth: authData,
                hint: null
              }) + "\n");
            } else {
              socket.write(JSON.stringify({ 
                id: msg.id || 0,
                auth: null,
                hint: "No OAuth credentials found. Run 'pi --login anthropic' in terminal to authenticate with Claude Max."
              }) + "\n");
            }
          } catch (e) {
            log(`Error reading auth file: ${e.message}`);
            socket.write(JSON.stringify({ 
              id: msg.id || 0,
              auth: null,
              hint: "Failed to read auth credentials. Run 'pi --login anthropic' in terminal to authenticate."
            }) + "\n");
          }
          continue;
        }
        
        if (msg.type === "tool_request") {
          log("Handling tool_request: " + msg.method + " " + (msg.params?.tool || ""));
          try {
            handleToolRequest(msg, socket);
          } catch (e) {
            socket.write(JSON.stringify({ error: e.message || "Request failed" }) + "\n");
          }
          continue;
        }
        
        if (msg.type === "stream_request") {
          log("Handling stream_request: " + msg.streamType);
          handleStreamRequest(msg, socket);
          continue;
        }
        
        if (msg.type === "stream_stop") {
          log("Handling stream_stop");
          for (const [streamId, stream] of activeStreams.entries()) {
            if (stream.socket === socket) {
              writeMessage({ type: "STREAM_STOP", streamId });
              activeStreams.delete(streamId);
            }
          }
          continue;
        }
        
        const id = ++requestCounter;
        log(`Forwarding to extension: id=${id} type=${msg.type}`);
        pendingRequests.set(id, { socket });
        writeMessage({ ...msg, id });
      } catch (e) {
        log(`Error parsing CLI request: ${e.message}`);
        socket.write(JSON.stringify({ error: "Invalid request" }) + "\n");
      }
    }
  });

  socket.on("error", (err) => {
    log(`CLI socket error: ${err.message}`);
  });
  
  socket.on("close", () => {
    log("CLI client disconnected");
    for (const [id, pending] of pendingRequests.entries()) {
      if (pending.socket === socket) {
        pendingRequests.delete(id);
      }
    }
    for (const [id, pending] of pendingToolRequests.entries()) {
      if (pending.socket === socket && !pending.autoScreenshot) {
        pendingToolRequests.delete(id);
      }
    }
    for (const [streamId, stream] of activeStreams.entries()) {
      if (stream.socket === socket) {
        writeMessage({ type: "STREAM_STOP", streamId });
        activeStreams.delete(streamId);
      }
    }
  });
});

server.listen(SOCKET_PATH, () => {
  log("Socket server listening on " + SOCKET_PATH);
  fs.chmodSync(SOCKET_PATH, 0o600);
  writeMessage({ type: "HOST_READY" });
  log("Sent HOST_READY to extension");
});

server.on("error", (err) => {
  log(`Server error: ${err.message}`);
});

process.on("SIGTERM", () => {
  log("SIGTERM received");
  server.close();
  try { fs.unlinkSync(SOCKET_PATH); } catch {}
  process.exit(0);
});

process.on("SIGINT", () => {
  log("SIGINT received");
  server.close();
  try { fs.unlinkSync(SOCKET_PATH); } catch {}
  process.exit(0);
});

process.on("uncaughtException", (err) => {
  log(`Uncaught exception: ${err.message}\n${err.stack}`);
  process.exit(1);
});

log("Host initialization complete, waiting for connections...");
