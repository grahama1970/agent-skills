/**
 * Gemini Web Client for surf-cli
 * 
 * Cookie-based client for gemini.google.com (no API key required).
 * Adapted from Oracle's gemini-web module.
 */

const https = require("https");
const fs = require("fs");
const path = require("path");

// ============================================================================
// Constants
// ============================================================================

const GEMINI_APP_URL = "https://gemini.google.com/app";
const GEMINI_STREAM_GENERATE_URL = "https://gemini.google.com/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate";
const GEMINI_UPLOAD_URL = "https://content-push.googleapis.com/upload";
const GEMINI_UPLOAD_PUSH_ID = "feeds/mcudyrk2a4khkz";

const USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";

const MODEL_HEADER_NAME = "x-goog-ext-525001261-jspb";
const MODEL_HEADERS = {
  "gemini-3-pro": '[1,null,null,null,"9d8ca3786ebdfbea",null,null,0,[4]]',
  "gemini-2.5-pro": '[1,null,null,null,"4af6c7f5da75d65d",null,null,0,[4]]',
  "gemini-2.5-flash": '[1,null,null,null,"9ec249fc9ad08861",null,null,0,[4]]',
};

const REQUIRED_COOKIES = ["__Secure-1PSID", "__Secure-1PSIDTS"];

const ALL_COOKIE_NAMES = [
  "__Secure-1PSID",
  "__Secure-1PSIDTS", 
  "__Secure-1PSIDCC",
  "__Secure-1PAPISID",
  "NID",
  "AEC",
  "SOCS",
  "__Secure-BUCKET",
  "__Secure-ENID",
  "SID",
  "HSID",
  "SSID",
  "APISID",
  "SAPISID",
  "__Secure-3PSID",
  "__Secure-3PSIDTS",
  "__Secure-3PAPISID",
  "SIDCC",
];

// ============================================================================
// Utility Functions
// ============================================================================

function getNestedValue(value, pathParts, fallback) {
  let current = value;
  for (const part of pathParts) {
    if (current == null) return fallback;
    if (typeof part === "number") {
      if (!Array.isArray(current)) return fallback;
      current = current[part];
    } else {
      if (typeof current !== "object") return fallback;
      current = current[part];
    }
  }
  return current ?? fallback;
}

function buildCookieHeader(cookieMap) {
  return Object.entries(cookieMap)
    .filter(([, value]) => typeof value === "string" && value.length > 0)
    .map(([name, value]) => `${name}=${value}`)
    .join("; ");
}

function buildCookieMap(cookies) {
  const cookieMap = {};
  for (const name of ALL_COOKIE_NAMES) {
    const cookie = cookies.find(c => c.name === name && c.value);
    if (cookie) {
      cookieMap[name] = cookie.value;
    }
  }
  return cookieMap;
}

function hasRequiredCookies(cookieMap) {
  return REQUIRED_COOKIES.every(name => Boolean(cookieMap[name]));
}

function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// ============================================================================
// HTTP Helpers
// ============================================================================

function httpsGet(url, headers, binary = false) {
  return new Promise((resolve, reject) => {
    const urlObj = new URL(url);
    const options = {
      hostname: urlObj.hostname,
      port: 443,
      path: urlObj.pathname + urlObj.search,
      method: "GET",
      headers: {
        "user-agent": USER_AGENT,
        ...headers,
      },
    };

    const req = https.request(options, (res) => {
      const chunks = [];
      res.on("data", chunk => chunks.push(chunk));
      res.on("end", () => {
        const buffer = Buffer.concat(chunks);
        resolve({ 
          status: res.statusCode, 
          headers: res.headers, 
          text: binary ? null : buffer.toString("utf-8"),
          buffer: binary ? buffer : null,
        });
      });
    });

    req.on("error", reject);
    req.end();
  });
}

function httpsPost(url, headers, body) {
  return new Promise((resolve, reject) => {
    const urlObj = new URL(url);
    const options = {
      hostname: urlObj.hostname,
      port: 443,
      path: urlObj.pathname + urlObj.search,
      method: "POST",
      headers: {
        "user-agent": USER_AGENT,
        ...headers,
      },
    };

    const req = https.request(options, (res) => {
      let data = "";
      res.on("data", chunk => data += chunk);
      res.on("end", () => resolve({ status: res.statusCode, headers: res.headers, text: data }));
    });

    req.on("error", reject);
    if (body) req.write(body);
    req.end();
  });
}

async function fetchWithRedirects(url, headers, maxRedirects = 10, binary = false) {
  let current = url;
  for (let i = 0; i <= maxRedirects; i++) {
    const res = await httpsGet(current, headers, binary);
    if (res.status >= 300 && res.status < 400 && res.headers.location) {
      current = new URL(res.headers.location, current).toString();
      continue;
    }
    return res;
  }
  throw new Error(`Too many redirects (>${maxRedirects})`);
}

// ============================================================================
// Gemini API Functions
// ============================================================================

async function fetchGeminiAccessToken(cookieMap) {
  const cookieHeader = buildCookieHeader(cookieMap);
  const res = await fetchWithRedirects(GEMINI_APP_URL, { cookie: cookieHeader });
  const html = res.text;

  const tokens = ["SNlM0e", "thykhd"];
  for (const key of tokens) {
    const match = html.match(new RegExp(`"${key}":"(.*?)"`));
    if (match?.[1]) return match[1];
  }
  
  throw new Error("Unable to authenticate with Gemini. Make sure you're signed into gemini.google.com in Chrome.");
}

function trimGeminiJsonEnvelope(text) {
  const start = text.indexOf("[");
  const end = text.lastIndexOf("]");
  if (start === -1 || end === -1 || end <= start) {
    throw new Error("Gemini response did not contain a JSON payload.");
  }
  return text.slice(start, end + 1);
}

function extractErrorCode(responseJson) {
  const code = getNestedValue(responseJson, [0, 5, 2, 0, 1, 0], -1);
  return typeof code === "number" && code >= 0 ? code : undefined;
}

function isModelUnavailable(errorCode) {
  return errorCode === 1052;
}

function extractGgdlUrls(rawText) {
  const matches = rawText.match(/https:\/\/lh3\.googleusercontent\.com\/gg-dl\/[^\s"']+/g) ?? [];
  const seen = new Set();
  const urls = [];
  for (const match of matches) {
    if (seen.has(match)) continue;
    seen.add(match);
    urls.push(match);
  }
  return urls;
}

function ensureFullSizeImageUrl(url) {
  if (url.includes("=s2048")) return url;
  if (url.includes("=s")) return url;
  return `${url}=s2048`;
}

function parseGeminiStreamGenerateResponse(rawText) {
  const responseJson = JSON.parse(trimGeminiJsonEnvelope(rawText));
  const errorCode = extractErrorCode(responseJson);

  const parts = Array.isArray(responseJson) ? responseJson : [];
  let bodyIndex = 0;
  let body = null;
  
  for (let i = 0; i < parts.length; i++) {
    const partBody = getNestedValue(parts[i], [2], null);
    if (!partBody) continue;
    try {
      const parsed = JSON.parse(partBody);
      const candidateList = getNestedValue(parsed, [4], []);
      if (Array.isArray(candidateList) && candidateList.length > 0) {
        bodyIndex = i;
        body = parsed;
        break;
      }
    } catch {
      // ignore
    }
  }

  const candidateList = getNestedValue(body, [4], []);
  const firstCandidate = candidateList[0];
  const textRaw = getNestedValue(firstCandidate, [1, 0], "");
  const cardContent = /^http:\/\/googleusercontent\.com\/card_content\/\d+/.test(textRaw);
  const text = cardContent
    ? (getNestedValue(firstCandidate, [22, 0], null) ?? textRaw)
    : textRaw;
  const thoughts = getNestedValue(firstCandidate, [37, 0, 0], null);
  const metadata = getNestedValue(body, [1], []);

  const images = [];

  // Web images
  const webImages = getNestedValue(firstCandidate, [12, 1], []);
  for (const webImage of webImages) {
    const url = getNestedValue(webImage, [0, 0, 0], null);
    if (!url) continue;
    images.push({
      kind: "web",
      url,
      title: getNestedValue(webImage, [7, 0], undefined),
      alt: getNestedValue(webImage, [0, 4], undefined),
    });
  }

  // Generated images
  const hasGenerated = Boolean(getNestedValue(firstCandidate, [12, 7, 0], null));
  if (hasGenerated) {
    let imgBody = null;
    for (let i = bodyIndex; i < parts.length; i++) {
      const partBody = getNestedValue(parts[i], [2], null);
      if (!partBody) continue;
      try {
        const parsed = JSON.parse(partBody);
        const candidateImages = getNestedValue(parsed, [4, 0, 12, 7, 0], null);
        if (candidateImages != null) {
          imgBody = parsed;
          break;
        }
      } catch {
        // ignore
      }
    }

    const imgCandidate = getNestedValue(imgBody ?? body, [4, 0], null);
    const generated = getNestedValue(imgCandidate, [12, 7, 0], []);
    for (const genImage of generated) {
      const url = getNestedValue(genImage, [0, 3, 3], null);
      if (!url) continue;
      images.push({
        kind: "generated",
        url,
        title: "[Generated Image]",
        alt: "",
      });
    }
  }

  return { metadata, text, thoughts, images, errorCode };
}

// ============================================================================
// File Upload
// ============================================================================

async function uploadGeminiFile(filePath) {
  const absPath = path.resolve(process.cwd(), filePath);
  const data = fs.readFileSync(absPath);
  const fileName = path.basename(absPath);
  
  // Build multipart form data manually
  const boundary = "----FormBoundary" + Math.random().toString(36).slice(2);
  const header = `--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="${fileName}"\r\nContent-Type: application/octet-stream\r\n\r\n`;
  const footer = `\r\n--${boundary}--\r\n`;
  
  const body = Buffer.concat([
    Buffer.from(header, "utf-8"),
    data,
    Buffer.from(footer, "utf-8"),
  ]);

  const res = await httpsPost(GEMINI_UPLOAD_URL, {
    "content-type": `multipart/form-data; boundary=${boundary}`,
    "push-id": GEMINI_UPLOAD_PUSH_ID,
  }, body);

  if (res.status < 200 || res.status >= 300) {
    throw new Error(`File upload failed: ${res.status} (${res.text.slice(0, 200)})`);
  }

  return { id: res.text, name: fileName };
}

// ============================================================================
// Image Download
// ============================================================================

async function downloadGeminiImage(url, cookieMap, outputPath) {
  const cookieHeader = buildCookieHeader(cookieMap);
  const fullUrl = ensureFullSizeImageUrl(url);
  
  // Use binary mode for image download
  const res = await fetchWithRedirects(fullUrl, { cookie: cookieHeader }, 10, true);
  
  if (res.status < 200 || res.status >= 300) {
    throw new Error(`Failed to download image: ${res.status}`);
  }

  const dir = path.dirname(outputPath);
  if (dir && !fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
  
  // Write binary buffer directly
  fs.writeFileSync(outputPath, res.buffer);
}

async function saveFirstGeminiImage(output, cookieMap, outputPath) {
  // Try generated or web images first
  const genOrWeb = output.images.find(img => img.kind === "generated") ?? output.images[0];
  if (genOrWeb?.url) {
    await downloadGeminiImage(genOrWeb.url, cookieMap, outputPath);
    return { saved: true, imageCount: output.images.length };
  }

  // Fall back to gg-dl URLs in raw response
  const ggdl = extractGgdlUrls(output.rawResponseText);
  if (ggdl[0]) {
    await downloadGeminiImage(ggdl[0], cookieMap, outputPath);
    return { saved: true, imageCount: ggdl.length };
  }

  return { saved: false, imageCount: 0 };
}

// ============================================================================
// Core Request Function
// ============================================================================

function buildGeminiFReqPayload(prompt, uploaded, chatMetadata) {
  const promptPayload = uploaded.length > 0
    ? [prompt, 0, null, uploaded.map(file => [[file.id, 1]])]
    : [prompt];

  const innerList = [promptPayload, null, chatMetadata ?? null];
  return JSON.stringify([null, JSON.stringify(innerList)]);
}

async function runGeminiWebOnce(input) {
  const { prompt, files, model, cookieMap, chatMetadata } = input;
  const cookieHeader = buildCookieHeader(cookieMap);
  
  // 1. Get access token
  const at = await fetchGeminiAccessToken(cookieMap);

  // 2. Upload files
  const uploaded = [];
  for (const file of files ?? []) {
    uploaded.push(await uploadGeminiFile(file));
  }

  // 3. Build request
  const fReq = buildGeminiFReqPayload(prompt, uploaded, chatMetadata);
  const params = new URLSearchParams();
  params.set("at", at);
  params.set("f.req", fReq);

  // 4. Send request
  const res = await httpsPost(GEMINI_STREAM_GENERATE_URL, {
    "content-type": "application/x-www-form-urlencoded;charset=utf-8",
    "origin": "https://gemini.google.com",
    "referer": "https://gemini.google.com/",
    "x-same-domain": "1",
    "cookie": cookieHeader,
    [MODEL_HEADER_NAME]: MODEL_HEADERS[model] || MODEL_HEADERS["gemini-3-pro"],
  }, params.toString());

  const rawResponseText = res.text;
  
  if (res.status < 200 || res.status >= 300) {
    return {
      rawResponseText,
      text: "",
      thoughts: null,
      metadata: chatMetadata ?? null,
      images: [],
      errorMessage: `Gemini request failed: ${res.status}`,
    };
  }

  try {
    const parsed = parseGeminiStreamGenerateResponse(rawResponseText);
    return {
      rawResponseText,
      text: parsed.text ?? "",
      thoughts: parsed.thoughts,
      metadata: parsed.metadata,
      images: parsed.images,
      errorCode: parsed.errorCode,
    };
  } catch (error) {
    let responseJson = null;
    try {
      responseJson = JSON.parse(trimGeminiJsonEnvelope(rawResponseText));
    } catch {
      responseJson = null;
    }
    const errorCode = extractErrorCode(responseJson);

    return {
      rawResponseText,
      text: "",
      thoughts: null,
      metadata: chatMetadata ?? null,
      images: [],
      errorCode: typeof errorCode === "number" ? errorCode : undefined,
      errorMessage: error instanceof Error ? error.message : String(error ?? ""),
    };
  }
}

async function runGeminiWebWithFallback(input) {
  const attempt = await runGeminiWebOnce(input);
  
  // Auto-fallback to flash if model unavailable
  if (isModelUnavailable(attempt.errorCode) && input.model !== "gemini-2.5-flash") {
    const fallback = await runGeminiWebOnce({ ...input, model: "gemini-2.5-flash" });
    return { ...fallback, effectiveModel: "gemini-2.5-flash" };
  }
  
  return { ...attempt, effectiveModel: input.model };
}

// ============================================================================
// Main Query Function
// ============================================================================

async function query(options) {
  const {
    prompt,
    model = "gemini-3-pro",
    file,
    generateImage,
    editImage,
    output,
    youtube,
    aspectRatio,
    timeout = 300000,
    getCookies,
    log = () => {},
  } = options;

  const startTime = Date.now();
  log("Starting Gemini query");

  // 1. Get cookies from Chrome
  const cookieResponse = await getCookies();
  const cookies = cookieResponse?.cookies;
  if (!Array.isArray(cookies)) {
    throw new Error("Failed to get cookies from Chrome. Make sure the extension is loaded and Chrome is running.");
  }
  const cookieMap = buildCookieMap(cookies);
  
  if (!hasRequiredCookies(cookieMap)) {
    throw new Error("Gemini login required. Sign into gemini.google.com in Chrome and try again.");
  }
  
  log(`Got ${Object.keys(cookieMap).length} Gemini cookies`);

  // 2. Resolve model
  const resolvedModel = MODEL_HEADERS[model] ? model : "gemini-3-pro";

  // 3. Build prompt
  let fullPrompt = prompt || "";
  if (aspectRatio && (generateImage || editImage)) {
    fullPrompt = `${fullPrompt} (aspect ratio: ${aspectRatio})`;
  }
  if (youtube) {
    fullPrompt = `${fullPrompt}\n\nYouTube video: ${youtube}`;
  }
  if (generateImage && !editImage) {
    fullPrompt = `Generate an image: ${fullPrompt}`;
  }

  // 4. Collect files
  const files = file ? [file] : [];

  // 5. Execute request
  let response;
  let imagePath = null;

  try {
    if (editImage) {
      // Two-turn conversation for image editing
      log("Uploading image for editing...");
      const intro = await runGeminiWebWithFallback({
        prompt: "Here is an image to edit",
        files: [editImage],
        model: resolvedModel,
        cookieMap,
        chatMetadata: null,
      });
      
      log("Sending edit request...");
      const editPrompt = `Use image generation tool to ${fullPrompt}`;
      const out = await runGeminiWebWithFallback({
        prompt: editPrompt,
        files,
        model: resolvedModel,
        cookieMap,
        chatMetadata: intro.metadata,
      });

      response = out;
      
      // Save output image
      const outputPath = output || generateImage || "edited.png";
      const imageSave = await saveFirstGeminiImage(out, cookieMap, outputPath);
      if (!imageSave.saved) {
        throw new Error(`No images generated. Response: ${out.text?.slice(0, 200) || "(empty)"}`);
      }
      imagePath = outputPath;
      
    } else if (generateImage) {
      // Image generation
      log("Generating image...");
      const out = await runGeminiWebWithFallback({
        prompt: fullPrompt,
        files,
        model: resolvedModel,
        cookieMap,
        chatMetadata: null,
      });

      response = out;
      
      // Save output image
      const imageSave = await saveFirstGeminiImage(out, cookieMap, generateImage);
      if (!imageSave.saved) {
        throw new Error(`No images generated. Response: ${out.text?.slice(0, 200) || "(empty)"}`);
      }
      imagePath = generateImage;
      
    } else {
      // Text query
      log("Sending text query...");
      const out = await runGeminiWebWithFallback({
        prompt: fullPrompt,
        files,
        model: resolvedModel,
        cookieMap,
        chatMetadata: null,
      });

      response = out;
    }
  } catch (error) {
    throw new Error(`Gemini request failed: ${error.message}`);
  }

  const tookMs = Date.now() - startTime;
  log(`Completed in ${tookMs}ms`);

  return {
    response: response.text || "",
    model: response.effectiveModel || resolvedModel,
    tookMs,
    imagePath,
    thoughts: response.thoughts,
    imageCount: response.images?.length || 0,
  };
}

// ============================================================================
// Exports
// ============================================================================

module.exports = {
  query,
  hasRequiredCookies,
  buildCookieMap,
  parseGeminiStreamGenerateResponse,
  REQUIRED_COOKIES,
  ALL_COOKIE_NAMES,
  GEMINI_APP_URL,
};
