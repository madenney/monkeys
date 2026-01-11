return (() => {
  try {
    const root = window;
    const verbose = !!root.__monkeyMessageVerbose;
    const enableDispatcherScan = !!root.__monkeyDispatcherScanEnabled || verbose;
    if (root.__monkeyMessageWatcher && root.__monkeyMessageWatcher.active) {
      const mode = root.__monkeyMessageWatcher.mode || "unknown";
      const hasObserver = !!root.__monkeyMessageWatcher.observer;
      const reset = mode === "dom" || hasObserver || mode === "waiting-dispatcher" || mode === "hooks";
      if (reset) {
        try {
          if (root.__monkeyMessageWatcher.observer) {
            root.__monkeyMessageWatcher.observer.disconnect();
          }
        } catch (err) {
          // ignore
        }
        if (root.__monkeyMessageWatcher.interval) {
          try {
            clearInterval(root.__monkeyMessageWatcher.interval);
          } catch (err) {
            // ignore
          }
        }
        root.__monkeyMessageWatcher = null;
      } else {
        return {ok: true, status: "already (" + mode + ")"};
      }
    }

  const diag = {
    href: location.href,
    path: location.pathname || "",
    ready: document.readyState,
    title: document.title || ""
  };

  const queue = root.__monkeyMessageQueue = root.__monkeyMessageQueue || [];
  const seen = root.__monkeyMessageSeen = root.__monkeyMessageSeen || new Set();
  const seenNodes = root.__monkeyMessageSeenNodes = root.__monkeyMessageSeenNodes || new WeakSet();
  const pending = root.__monkeyMessagePending = root.__monkeyMessagePending || new WeakSet();
  const attempts = root.__monkeyMessageAttempts = root.__monkeyMessageAttempts || new WeakMap();
  const dispatcherScan = root.__monkeyDispatcherScan = root.__monkeyDispatcherScan || {
    ids: [],
    index: 0,
    source: "",
    total: 0,
    mode: "strict"
  };
  const dispatcherTried = root.__monkeyDispatcherTried = root.__monkeyDispatcherTried || new Set();
  const snapshotLimit = __SNAPSHOT_LIMIT__;

  function pushMessage(payload) {
    queue.push(payload);
    if (queue.length > __MAX_QUEUE_SIZE__) {
      queue.shift();
    }
    try {
      console.log("[monkey-message]", JSON.stringify(payload));
    } catch (err) {
      // ignore console errors
    }
  }

  function emitStatus(message) {
    if (!verbose) return;
    pushMessage({content: String(message), system: true});
  }

  function shouldEmitId(id) {
    if (!id) return true;
    const key = "id:" + id;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }

  function formatAuthorName(author, member) {
    const memberNick = member && typeof member.nick === "string" ? member.nick.trim() : "";
    if (memberNick) return memberNick;
    const globalName = author && typeof author.global_name === "string" ? author.global_name.trim() : "";
    if (globalName) return globalName;
    const username = author && typeof author.username === "string" ? author.username.trim() : "";
    if (!username) return "";
    const discriminator = author && author.discriminator && author.discriminator !== "0"
      ? "#" + author.discriminator
      : "";
    return username + discriminator;
  }

  function getRequire() {
    diag.requireSource = "";
    const chunkKeys = [];
    if (root.webpackChunkdiscord_app) {
      chunkKeys.push("webpackChunkdiscord_app");
    }
    if (root.webpackChunkdiscord_web) {
      chunkKeys.push("webpackChunkdiscord_web");
    }
    diag.chunkKeys = chunkKeys.slice(0);
    if (root.__webpack_require__) {
      diag.requireSource = "__webpack_require__";
      return root.__webpack_require__;
    }
    for (const key of chunkKeys) {
      const chunk = root[key];
      if (!chunk || typeof chunk.push !== "function") continue;
      let req = null;
      const id = Math.random();
      try {
        chunk.push([[id], {}, (r) => {
          req = r;
        }]);
        chunk.pop();
      } catch (err) {
        continue;
      }
      if (req) {
        diag.requireSource = key;
        return req;
      }
    }
    return null;
  }

  diag.scan = "skipped-factories";

  function parseChannelMeta() {
    const parts = String(location.pathname || "").split("/");
    if (parts.length >= 4 && parts[1] === "channels") {
      return {guild_id: parts[2] || "", channel_id: parts[3] || ""};
    }
    return {guild_id: "", channel_id: ""};
  }

  function channelKeyFromMeta(meta) {
    if (!meta) return "";
    if (!meta.guild_id || !meta.channel_id) return "";
    return meta.guild_id + ":" + meta.channel_id;
  }

  let cachedChannelName = "";
  let cachedChannelPath = "";

  function normalizeChannelName(name) {
    if (!name) return "";
    const trimmed = String(name).trim();
    if (!trimmed) return "";
    if (trimmed.startsWith("#")) {
      return trimmed.slice(1).trim();
    }
    return trimmed;
  }

  function extractChannelName(raw) {
    if (!raw) return "";
    let text = String(raw).trim();
    if (!text) return "";
    text = text.replace(/^\(\d+\)\s*/, "");
    if (text.includes("|")) {
      const parts = text.split("|").map((part) => part.trim()).filter(Boolean);
      const hashed = parts.find((part) => part.includes("#"));
      if (hashed) {
        return normalizeChannelName(hashed);
      }
      if (parts.length) {
        text = parts[0];
      }
    }
    if (text.includes("#")) {
      const idx = text.lastIndexOf("#");
      if (idx >= 0) {
        text = text.slice(idx + 1).trim();
      }
    }
    if (text.includes(":")) {
      text = text.split(":").pop().trim();
    }
    if (text.includes("/")) {
      text = text.split("/").pop().trim();
    }
    return normalizeChannelName(text);
  }

  function getChannelName() {
    const path = location.pathname || "";
    if (path === cachedChannelPath && cachedChannelName) {
      return cachedChannelName;
    }

    const selectors = [
      "[data-testid='channel-name']",
      "header h1[title]",
      "header h1",
      "h1[title]",
      "h1"
    ];
    for (const selector of selectors) {
      const el = document.querySelector(selector);
      if (!el) continue;
      const text = el.getAttribute("title") || el.textContent || el.innerText || "";
      const name = extractChannelName(text);
      if (name) {
        cachedChannelName = name;
        cachedChannelPath = path;
        return name;
      }
    }

    const title = document.title || "";
    if (title) {
      const name = extractChannelName(title);
      if (name && name.toLowerCase() !== "discord") {
        cachedChannelName = name;
        cachedChannelPath = path;
        return name;
      }
    }

    cachedChannelPath = path;
    cachedChannelName = "";
    return "";
  }

  function findAuthorId(node) {
    if (!node || !node.querySelector) return "";
    const attrs = ["data-author-id", "data-user-id", "data-userid", "data-uid", "data-author"];
    for (const attr of attrs) {
      const value = node.getAttribute(attr);
      if (isSnowflake(value)) return value;
    }

    const selector = attrs.map((attr) => `[${attr}]`).join(",");
    const el = node.querySelector(selector);
    if (el) {
      for (const attr of attrs) {
        const value = el.getAttribute(attr);
        if (isSnowflake(value)) return value;
      }
    }

    const links = node.querySelectorAll("a[href*='/users/']");
    for (const link of links) {
      const href = link.getAttribute("href") || "";
      const parts = href.split("/").filter(Boolean);
      const candidate = parts[parts.length - 1] || "";
      if (isSnowflake(candidate)) return candidate;
    }

    return "";
  }

  function findLogRoot() {
    return (
      document.querySelector("[data-list-id='chat-messages']") ||
      document.querySelector("[data-list-id^='chat-messages']") ||
      document.querySelector("ol[aria-label*='Messages']") ||
      document.querySelector("div[aria-label*='Messages']") ||
      document.querySelector("[role='log'][aria-label*='Messages']") ||
      document.querySelector("[role='log']")
    );
  }

  function isChatLogRoot(node) {
    if (!node || node.nodeType !== 1) return false;
    const listId = node.getAttribute("data-list-id") || "";
    if (listId.startsWith("chat-messages")) return true;
    const aria = node.getAttribute("aria-label") || "";
    if (aria.includes("Messages")) return true;
    if (node.querySelector && node.querySelector("[id^='message-content-']")) return true;
    if (
      node.querySelector &&
      node.querySelector("[data-list-item-id^='chat-messages__message-container']")
    ) {
      return true;
    }
    return false;
  }

  function getListItemId(node) {
    if (!node || node.nodeType !== 1) return "";
    const direct = node.getAttribute("data-list-item-id") || "";
    if (direct) return direct;
    if (node.closest) {
      const container = node.closest("[data-list-item-id]");
      if (container) {
        return container.getAttribute("data-list-item-id") || "";
      }
    }
    return "";
  }

  function isSnowflake(value) {
    return typeof value === "string" && /^[0-9]{16,20}$/.test(value);
  }

  function extractMessageId(node) {
    if (!node || node.nodeType !== 1) return "";
    const id = node.id || "";
    if (id.indexOf("message-content-") === 0) {
      const candidate = id.replace("message-content-", "");
      if (isSnowflake(candidate)) {
        return candidate;
      }
    }
    const dataId = node.getAttribute("data-message-id") || "";
    if (isSnowflake(dataId)) return dataId;
    const listId = getListItemId(node);
    if (!listId) return "";
    const marker = "message-container-";
    const idx = listId.lastIndexOf(marker);
    if (idx < 0) return "";
    const tail = listId.slice(idx + marker.length);
    if (!tail) return "";
    const parts = tail.split("-");
    const candidate = parts[parts.length - 1] || tail;
    if (isSnowflake(candidate)) {
      return candidate;
    }
    return "";
  }

  function findTimestamp(node) {
    if (!node || node.nodeType !== 1) return "";
    let scope = node;
    if (node.closest) {
      const container = node.closest("[data-list-item-id^='chat-messages__message-container']");
      if (container) {
        scope = container;
      }
    }
    if (!scope.querySelector) return "";
    const timeEl = scope.querySelector("time");
    if (!timeEl) return "";
    return timeEl.getAttribute("datetime") || timeEl.getAttribute("aria-label") || "";
  }

  function collectContentNodes(node) {
    const found = [];
    if (!node || node.nodeType !== 1) return found;

    const pushUnique = (n) => {
      if (!n) return;
      if (found.indexOf(n) === -1) {
        found.push(n);
      }
    };

    if (node.id && node.id.indexOf("message-content-") === 0) {
      pushUnique(node);
    }
    if (!node.querySelectorAll) return found;

    node.querySelectorAll("[id^='message-content-']").forEach((n) => pushUnique(n));
    node.querySelectorAll("[data-list-item-id^='chat-messages__message-container']").forEach((n) => {
      const content = n.querySelector("[id^='message-content-']");
      if (content) {
        pushUnique(content);
        return;
      }
      pushUnique(n);
    });
    return found;
  }

  function collectSnapshotEntries(logRoot) {
    if (!logRoot || !logRoot.querySelectorAll) return [];
    const containers = Array.from(
      logRoot.querySelectorAll("[data-list-item-id^='chat-messages__message-container']")
    );
    if (containers.length) {
      return containers;
    }
    return Array.from(logRoot.querySelectorAll("[id^='message-content-']"));
  }

  function collectDedupeKeys(node) {
    const keys = [];
    const msgId = extractMessageId(node);
    if (msgId) keys.push("id:" + msgId);
    return keys;
  }

  function canonicalizeMessageNode(node) {
    if (!node || node.nodeType !== 1) return null;
    if (node.closest) {
      const container = node.closest("[data-list-item-id^='chat-messages__message-container']");
      if (container) return container;
    }
    return node;
  }

  function handleContentNode(contentNode, meta) {
    const node = canonicalizeMessageNode(contentNode);
    if (!node) return false;
    const textNode = node.querySelector ? node.querySelector("[id^='message-content-']") : null;
    const text = (textNode || node).innerText || (textNode || node).textContent || "";
    const trimmed = text.trim();
    if (!trimmed) return false;

    const keys = collectDedupeKeys(node);
    if (keys.length) {
      for (const key of keys) {
        if (seen.has(key)) {
          return true;
        }
      }
      for (const key of keys) {
        seen.add(key);
      }
    } else if (seenNodes.has(node)) {
      return true;
    }

    const msgId = extractMessageId(node);
    if (!msgId) {
      return false;
    }
    const authorId = findAuthorId(node);
    const channelName = getChannelName();
    seenNodes.add(node);
    pushMessage({
      id: msgId,
      content: trimmed,
      author: "",
      author_id: authorId,
      channel_id: meta.channel_id,
      channel_name: channelName,
      guild_id: meta.guild_id,
      mention_everyone: false,
      mentions: [],
      timestamp: "",
      source: "dom"
    });
    return true;
  }

  function scheduleProcess(contentNode, meta) {
    const node = canonicalizeMessageNode(contentNode);
    if (!node) return;
    if (seenNodes.has(node)) return;
    if (pending.has(node)) return;
    const count = attempts.get(node) || 0;
    if (count >= 3) return;
    pending.add(node);
    setTimeout(() => {
      pending.delete(node);
      if (!node.isConnected) return;
      const processed = handleContentNode(node, meta);
      if (processed) {
        attempts.delete(node);
        return;
      }
      attempts.set(node, count + 1);
      scheduleProcess(node, meta);
    }, 350);
  }

  function snapshotRecent(logRoot, meta) {
    const entries = collectSnapshotEntries(logRoot);
    if (!entries.length) return;
    const start = entries.length > snapshotLimit ? entries.length - snapshotLimit : 0;
    for (let i = start; i < entries.length; i += 1) {
      const entry = entries[i];
      const content = entry.querySelector
        ? entry.querySelector("[id^='message-content-']")
        : null;
      const node = content || entry;
      if (!handleContentNode(node, meta)) {
        scheduleProcess(node, meta);
      }
    }
  }

  function attachDomObserver() {
    if (typeof MutationObserver !== "function") {
      return false;
    }
    let logRoot = findLogRoot();
    if (!isChatLogRoot(logRoot)) {
      return false;
    }

    const observer = new MutationObserver((mutations) => {
      const meta = parseChannelMeta();
      for (const mutation of mutations) {
        for (const node of mutation.addedNodes || []) {
          const contentNodes = collectContentNodes(node);
          for (const contentNode of contentNodes) {
            scheduleProcess(contentNode, meta);
          }
        }
      }
    });

    observer.observe(logRoot, {childList: true, subtree: true});

    const watcher = {
      active: true,
      handler: null,
      mode: "dom",
      observer: observer,
      interval: null,
      logRoot: logRoot,
      channelKey: ""
    };
    root.__monkeyMessageWatcher = watcher;

    let lastSnapshotKey = "";
    let meta = parseChannelMeta();
    let channelKey = channelKeyFromMeta(meta);
    if (channelKey) {
      snapshotRecent(logRoot, meta);
      lastSnapshotKey = channelKey;
      watcher.channelKey = channelKey;
    }

    const interval = setInterval(() => {
      meta = parseChannelMeta();
      channelKey = channelKeyFromMeta(meta);
      const nextRoot = findLogRoot();
      const nextOk = isChatLogRoot(nextRoot);
      const rootChanged = nextOk && nextRoot !== logRoot;
      const rootMissing = !logRoot || !document.contains(logRoot);

      if (nextOk && (rootChanged || rootMissing)) {
        try {
          observer.disconnect();
        } catch (err) {
          // ignore
        }
        logRoot = nextRoot;
        observer.observe(logRoot, {childList: true, subtree: true});
        watcher.logRoot = logRoot;
      }

      if (nextOk && channelKey && channelKey !== lastSnapshotKey) {
        snapshotRecent(logRoot, meta);
        lastSnapshotKey = channelKey;
        watcher.channelKey = channelKey;
      }
    }, 1000);

    watcher.interval = interval;
    return true;
  }

  const handler = (event) => {
    try {
      const msg = event && event.message ? event.message : event;
      if (!msg) return;
      if (!shouldEmitId(msg.id || "")) return;
      const author = msg.author || {};
      const authorTag = formatAuthorName(author, msg.member);
      const payload = {
        id: msg.id || "",
        content: msg.content || "",
        author: authorTag,
        author_id: author.id || "",
        channel_id: msg.channel_id || "",
        guild_id: msg.guild_id || "",
        mention_everyone: !!msg.mention_everyone,
        mentions: Array.isArray(msg.mentions)
          ? msg.mentions.map((m) => m && m.id).filter(Boolean)
          : [],
        timestamp: msg.timestamp || ""
      };
      pushMessage(payload);
    } catch (err) {
      try {
        console.warn("[monkey-message] handler error", err);
      } catch (ignored) {}
    }
  };

  const wsDebugLimit = verbose ? 5 : 0;
  const wsDiag = root.__monkeyWsDiag = root.__monkeyWsDiag || {
    total: 0,
    text: 0,
    arrayBuffer: 0,
    blob: 0,
    view: 0,
    jsonHook: 0,
    jsonParsed: 0,
    jsonErrors: 0,
    nonDispatch: 0,
    msgCreate: 0,
    lastType: "",
    lastPreview: ""
  };

  function noteWs(type, preview) {
    wsDiag.lastType = type || "";
    wsDiag.lastPreview = preview || "";
    if (wsDiag.total % 50 === 0) {
      emitStatus(
        `ws diag total=${wsDiag.total} text=${wsDiag.text} buf=${wsDiag.arrayBuffer} blob=${wsDiag.blob} view=${wsDiag.view} json=${wsDiag.jsonParsed} jsonErr=${wsDiag.jsonErrors} nonDispatch=${wsDiag.nonDispatch} msg=${wsDiag.msgCreate} lastType=${wsDiag.lastType}`
      );
    }
  }

  function emitGatewayMessage(msg, sourceType) {
    if (!msg) return false;
    if (!shouldEmitId(msg.id || "")) return true;
    const meta = parseChannelMeta();
    if (meta.channel_id && msg.channel_id && meta.channel_id !== msg.channel_id) {
      return false;
    }
    const author = msg.author || {};
    const authorName = formatAuthorName(author, msg.member);
    pushMessage({
      id: msg.id || "",
      content: msg.content || "",
      author: authorName,
      author_id: author.id || "",
      channel_id: msg.channel_id || "",
      channel_name: getChannelName(),
      guild_id: msg.guild_id || "",
      mention_everyone: !!msg.mention_everyone,
      mentions: Array.isArray(msg.mentions)
        ? msg.mentions.map((m) => m && m.id).filter(Boolean)
        : [],
      timestamp: msg.timestamp || "",
      source: sourceType || "ws"
    });
    return true;
  }

  function processGatewayPayload(payload, sourceType, preview) {
    if (!payload || typeof payload !== "object") {
      wsDiag.nonDispatch += 1;
      noteWs(sourceType || "dispatch", preview);
      return;
    }
    if (payload.t !== "MESSAGE_CREATE") {
      wsDiag.nonDispatch += 1;
      noteWs(sourceType || "dispatch", preview);
      return;
    }
    wsDiag.msgCreate += 1;
    const msg = payload.d || payload.message || null;
    emitGatewayMessage(msg, sourceType || "ws");
    noteWs(sourceType || "dispatch", preview);
  }

  function toHex(buffer, maxBytes) {
    if (!(buffer instanceof ArrayBuffer)) return "";
    const bytes = new Uint8Array(buffer);
    const limit = Math.min(bytes.length, maxBytes);
    const parts = [];
    for (let i = 0; i < limit; i += 1) {
      parts.push(bytes[i].toString(16).padStart(2, "0"));
    }
    return parts.join("");
  }

  function decodeJson(text) {
    if (!text) return null;
    try {
      return JSON.parse(text);
    } catch (err) {
      return null;
    }
  }

  function inflateWithPako(buffer, mode) {
    if (!root.pako) return null;
    try {
      const bytes = new Uint8Array(buffer);
      if (mode === "deflate-raw") {
        return root.pako.inflateRaw(bytes, {to: "string"});
      }
      return root.pako.inflate(bytes, {to: "string"});
    } catch (err) {
      return null;
    }
  }

  function inflateWithStream(buffer, mode) {
    if (typeof DecompressionStream !== "function") return Promise.resolve(null);
    try {
      const ds = new DecompressionStream(mode);
      const blob = new Blob([buffer]);
      const stream = blob.stream().pipeThrough(ds);
      return new Response(stream).text().catch(() => null);
    } catch (err) {
      return Promise.resolve(null);
    }
  }

  function guessInflateModes(buffer) {
    const bytes = new Uint8Array(buffer);
    if (bytes.length && bytes[0] === 0x78) {
      return ["deflate", "deflate-raw"];
    }
    return ["deflate-raw", "deflate"];
  }

  function attemptInflate(buffer) {
    const modes = guessInflateModes(buffer);
    const first = inflateWithPako(buffer, modes[0]);
    if (first) return Promise.resolve({text: first, mode: modes[0]});
    return inflateWithStream(buffer, modes[0]).then((text) => {
      if (text) return {text, mode: modes[0]};
      const second = inflateWithPako(buffer, modes[1]);
      if (second) return {text: second, mode: modes[1]};
      return inflateWithStream(buffer, modes[1]).then((text2) => {
        if (!text2) return null;
        return {text: text2, mode: modes[1]};
      });
    });
  }

  function handleGatewayMessage(data, sourceType, sizeHint) {
    if (!data) return;
    wsDiag.total += 1;
    let preview = "";
    let hex = "";
    if (data instanceof ArrayBuffer) {
      hex = toHex(data, 16);
    }
    if (typeof data === "string") {
      wsDiag.text += 1;
      preview = data.slice(0, 200);
      const payload = decodeJson(data);
      if (!payload) {
        wsDiag.jsonErrors += 1;
        if (wsDiag.total <= wsDebugLimit) {
          emitStatus(
            `ws debug #${wsDiag.total} type=${sourceType || "text"} size=${sizeHint || data.length} preview=${preview.replace(/\s+/g, " ").slice(0, 120)}`
          );
        }
        noteWs(sourceType || "text", preview);
        return;
      }
      wsDiag.jsonParsed += 1;
      processGatewayPayload(payload, sourceType || "text", preview);
      return;
    } else if (data instanceof ArrayBuffer) {
      wsDiag.arrayBuffer += 1;
      if (wsDiag.total <= wsDebugLimit) {
        emitStatus(
          `ws debug #${wsDiag.total} type=${sourceType || "arrayBuffer"} size=${sizeHint || data.byteLength} hex=${hex}`
        );
      }
      let text = "";
      try {
        text = new TextDecoder("utf-8").decode(data);
      } catch (err) {
        text = "";
      }
      preview = text.slice(0, 200);
      const payload = decodeJson(text);
      if (payload) {
        wsDiag.jsonParsed += 1;
        processGatewayPayload(payload, sourceType || "arrayBuffer", preview);
        return;
      }

      attemptInflate(data).then((result) => {
        if (!result || !result.text) {
          wsDiag.jsonErrors += 1;
          noteWs(sourceType || "arrayBuffer", preview);
          return;
        }
        const inflatedPayload = decodeJson(result.text);
        if (!inflatedPayload) {
          wsDiag.jsonErrors += 1;
          noteWs(sourceType || "arrayBuffer", preview);
          return;
        }
        wsDiag.jsonParsed += 1;
        processGatewayPayload(inflatedPayload, sourceType || "arrayBuffer", result.text.slice(0, 200));
      });
      return;
    }
    if (wsDiag.total <= wsDebugLimit) {
      emitStatus(
        `ws debug #${wsDiag.total} type=${sourceType || typeof data} size=${sizeHint || 0}`
      );
    }
    noteWs(sourceType || typeof data, "");
  }

  function handleWsData(data) {
    if (!data) return;
    if (typeof data === "string" || data instanceof ArrayBuffer) {
      handleGatewayMessage(
        data,
        typeof data === "string" ? "text" : "arrayBuffer",
        typeof data === "string" ? data.length : data.byteLength
      );
      return;
    }
    if (ArrayBuffer.isView && ArrayBuffer.isView(data)) {
      wsDiag.view += 1;
      handleGatewayMessage(data.buffer, "arrayBufferView", data.byteLength);
      return;
    }
    if (data && typeof data.arrayBuffer === "function") {
      const size = typeof data.size === "number" ? data.size : 0;
      data.arrayBuffer().then((buf) => {
        handleGatewayMessage(buf, "blob", size || buf.byteLength);
      }).catch(() => {});
      wsDiag.blob += 1;
      return;
    }
    noteWs(typeof data, "");
  }

  function installJsonParseHook() {
    try {
      if (root.__monkeyJsonParseHook && root.__monkeyJsonParseHook.active) return true;
      const originalParse = JSON.parse;
      JSON.parse = function() {
        const result = originalParse.apply(this, arguments);
        try {
          if (
            result &&
            typeof result === "object" &&
            result.t === "MESSAGE_CREATE" &&
            result.d &&
            typeof result.d === "object"
          ) {
            wsDiag.jsonHook += 1;
            emitGatewayMessage(result.d, "json");
          }
        } catch (err) {
          // ignore hook errors
        }
        return result;
      };
      root.__monkeyJsonParseHook = {active: true, originalParse};
      return true;
    } catch (err) {
      return false;
    }
  }

  function installWebSocketHook() {
    try {
      const wsProto = root.WebSocket && root.WebSocket.prototype;
      if (!wsProto) return false;
      if (root.__monkeyWebSocketHook && root.__monkeyWebSocketHook.active) return true;

      const listenerMap = root.__monkeyWsListenerMap = root.__monkeyWsListenerMap || new WeakMap();
      const socketSet = root.__monkeyWsSockets = root.__monkeyWsSockets || new WeakSet();
      const originalAddEventListener = wsProto.addEventListener;
      const originalRemoveEventListener = wsProto.removeEventListener;
      const originalSend = wsProto.send;
      if (typeof originalAddEventListener !== "function" || typeof originalSend !== "function") {
        return false;
      }

      const internalListener = function(event) {
        try {
          if (event && event.data !== undefined) {
            handleWsData(event.data);
          }
        } catch (err) {
          // ignore hook errors
        }
      };
      internalListener.__monkeyInternal = true;

      const wrapListener = (listener) => {
        if (!listener) return listener;
        if (listener.__monkeyInternal) return listener;
        if (typeof listener === "function") {
          const existing = listenerMap.get(listener);
          if (existing) return existing;
          const wrapped = function(event) {
            try {
              if (event && event.data !== undefined) {
                handleWsData(event.data);
              }
            } catch (err) {
              // ignore hook errors
            }
            return listener.call(this, event);
          };
          listenerMap.set(listener, wrapped);
          return wrapped;
        }
        if (typeof listener.handleEvent === "function") {
          const existing = listenerMap.get(listener);
          if (existing) return existing;
          const wrapped = {
            handleEvent(event) {
              try {
                if (event && event.data !== undefined) {
                  handleWsData(event.data);
                }
              } catch (err) {
                // ignore hook errors
              }
              return listener.handleEvent.call(listener, event);
            }
          };
          listenerMap.set(listener, wrapped);
          return wrapped;
        }
        return listener;
      };

      const registerSocket = (ws) => {
        if (!ws || socketSet.has(ws)) return;
        socketSet.add(ws);
        try {
          originalAddEventListener.call(ws, "message", internalListener);
        } catch (err) {
          // ignore
        }
      };

      wsProto.addEventListener = function(type, listener, options) {
        if (type === "message") {
          return originalAddEventListener.call(this, type, wrapListener(listener), options);
        }
        return originalAddEventListener.call(this, type, listener, options);
      };

      if (typeof originalRemoveEventListener === "function") {
        wsProto.removeEventListener = function(type, listener, options) {
          if (type === "message") {
            const wrapped = listenerMap.get(listener);
            return originalRemoveEventListener.call(this, type, wrapped || listener, options);
          }
          return originalRemoveEventListener.call(this, type, listener, options);
        };
      }

      wsProto.send = function() {
        registerSocket(this);
        return originalSend.apply(this, arguments);
      };

      const onMessageDescriptor = Object.getOwnPropertyDescriptor(wsProto, "onmessage");
      if (onMessageDescriptor && onMessageDescriptor.configurable) {
        Object.defineProperty(wsProto, "onmessage", {
          configurable: true,
          enumerable: onMessageDescriptor.enumerable,
          get() {
            return onMessageDescriptor.get ? onMessageDescriptor.get.call(this) : null;
          },
          set(handler) {
            const wrapped = wrapListener(handler);
            if (onMessageDescriptor.set) {
              return onMessageDescriptor.set.call(this, wrapped);
            }
            return undefined;
          }
        });
      }

      root.__monkeyWebSocketHook = {
        active: true,
        originalAddEventListener,
        originalRemoveEventListener,
        originalSend
      };
      return true;
    } catch (err) {
      return false;
    }
  }

  function factoryLooksLikeDispatcher(factory, mode) {
    if (typeof factory !== "function") return false;
    let src = "";
    try {
      src = Function.prototype.toString.call(factory);
    } catch (err) {
      return false;
    }
    if (!src) return false;
    if (mode === "all") return true;
    if (src.indexOf("dispatcher") >= 0) return true;
    if (src.indexOf("Dispatcher") >= 0) return true;
    if (mode === "strict") {
      if (src.indexOf("dispatch") >= 0 && src.indexOf("subscribe") >= 0) return true;
      if (src.indexOf("dispatch") >= 0 && src.indexOf("register") >= 0) return true;
      if (src.indexOf("dispatch") >= 0 && src.indexOf("waitFor") >= 0) return true;
      return false;
    }
    if (src.indexOf("dispatch") >= 0) return true;
    if (src.indexOf("subscribe") >= 0) return true;
    if (src.indexOf("register") >= 0) return true;
    if (src.indexOf("waitFor") >= 0) return true;
    if (src.indexOf("isDispatching") >= 0) return true;
    if (src.indexOf("Flux") >= 0 || src.indexOf("flux") >= 0) return true;
    return false;
  }

  function locateDispatcher() {
    const info = {
      requireSource: "",
      chunkKeys: [],
      cacheSize: 0,
      candidates: 0,
      dispatch: 0,
      subscribe: 0,
      register: 0,
      factoryTotal: 0,
      factoryCandidates: 0,
      factoryIndex: 0,
      factoryBatch: 0,
      factoryTried: 0,
      factoryErrors: 0,
      accessErrors: 0,
      factoryMode: "",
      scanStage: "",
      error: ""
    };
    const safeGet = (obj, prop) => {
      if (!obj) return undefined;
      try {
        return obj[prop];
      } catch (err) {
        info.accessErrors += 1;
        return undefined;
      }
    };
    const safeHasFunction = (obj, prop) => {
      return typeof safeGet(obj, prop) === "function";
    };
    let req = null;
    try {
      req = getRequire();
    } catch (err) {
      info.error = String(err);
      info.scanStage = "error";
      return {dispatcher: null, info};
    }
    info.requireSource = diag.requireSource || "";
    info.chunkKeys = Array.isArray(diag.chunkKeys) ? diag.chunkKeys : [];
    if (!req) {
      info.scanStage = "no-require";
      return {dispatcher: null, info};
    }
    const cache = req.c || {};
    const modules = Object.values(cache);
    info.cacheSize = modules.length;
    diag.cacheSize = modules.length;
    const candidates = [];
    const consider = (obj) => {
      if (!obj) return;
      const hasDispatch = safeHasFunction(obj, "dispatch");
      const hasRegister = safeHasFunction(obj, "register");
      const hasSubscribe = safeHasFunction(obj, "subscribe");
      const hasWait = safeHasFunction(obj, "wait") || safeHasFunction(obj, "waitFor");
      if (hasDispatch) info.dispatch += 1;
      if (hasRegister) info.register += 1;
      if (hasSubscribe) info.subscribe += 1;
      if (hasDispatch && (hasRegister || hasSubscribe || hasWait)) {
        candidates.push({obj, hasRegister, hasSubscribe, hasWait});
      }
    };

    const scanExports = (exp) => {
      if (!exp) return;
      consider(exp);
      const dispatcher = safeGet(exp, "Dispatcher");
      if (dispatcher) consider(dispatcher);
      const dispatcherLower = safeGet(exp, "dispatcher");
      if (dispatcherLower) consider(dispatcherLower);
      const def = safeGet(exp, "default");
      if (!def) return;
      consider(def);
      const defDispatcher = safeGet(def, "Dispatcher");
      if (defDispatcher) consider(defDispatcher);
      const defDispatcherLower = safeGet(def, "dispatcher");
      if (defDispatcherLower) consider(defDispatcherLower);
    };

    for (const mod of modules) {
      const exports = safeGet(mod, "exports");
      if (!exports) continue;
      scanExports(exports);
    }

    info.candidates = candidates.length;
    info.scanStage = "cache";
    if (candidates.length) {
      const picked = candidates.find((c) => c.hasSubscribe) || candidates.find((c) => c.hasRegister) || candidates[0];
      return {dispatcher: picked ? picked.obj : null, info};
    }

    const factories = req.m || {};
    const factoryIds = Object.keys(factories);
    info.factoryTotal = factoryIds.length;
    diag.factoryCount = factoryIds.length;
    info.scanStage = "factories";

    const modes = ["strict", "loose", "all"];
    const modeIndex = (mode) => modes.indexOf(mode);
    const nextMode = (mode) => {
      const idx = modeIndex(mode);
      if (idx < 0) return "strict";
      return modes[Math.min(idx + 1, modes.length - 1)];
    };
    const resetScan = (mode) => {
      dispatcherScan.ids = [];
      dispatcherScan.index = 0;
      dispatcherScan.mode = mode;
    };
    const buildCandidates = () => {
      dispatcherScan.ids = [];
      if (!factoryIds.length) return;
      if (dispatcherScan.mode === "all") {
        dispatcherScan.ids = factoryIds.slice(0);
        return;
      }
      for (const id of factoryIds) {
        const factory = factories[id];
        if (!factoryLooksLikeDispatcher(factory, dispatcherScan.mode)) continue;
        dispatcherScan.ids.push(id);
      }
    };

    if (!dispatcherScan.mode) {
      dispatcherScan.mode = "strict";
    }

    if (
      dispatcherScan.source !== info.requireSource ||
      dispatcherScan.total !== factoryIds.length
    ) {
      resetScan(dispatcherScan.mode || "strict");
      dispatcherScan.source = info.requireSource || "";
      dispatcherScan.total = factoryIds.length;
      dispatcherTried.clear();
    }

    if (!dispatcherScan.ids.length && factoryIds.length) {
      buildCandidates();
    }

    if (
      (dispatcherScan.index >= dispatcherScan.ids.length || !dispatcherScan.ids.length) &&
      dispatcherScan.mode !== "all"
    ) {
      const upgraded = nextMode(dispatcherScan.mode);
      if (upgraded !== dispatcherScan.mode) {
        resetScan(upgraded);
        buildCandidates();
      }
    }

    info.factoryMode = dispatcherScan.mode;
    info.factoryCandidates = dispatcherScan.ids.length;
    if (!dispatcherScan.ids.length) {
      return {dispatcher: null, info};
    }

    let batchSize = 12;
    if (dispatcherScan.mode === "loose") {
      batchSize = 40;
    } else if (dispatcherScan.mode === "all") {
      batchSize = Math.max(50, Math.ceil(dispatcherScan.ids.length / 20));
    }
    const startIndex = dispatcherScan.index;
    const endIndex = Math.min(startIndex + batchSize, dispatcherScan.ids.length);
    info.factoryBatch = endIndex - startIndex;
    info.factoryIndex = endIndex;

    for (let i = startIndex; i < endIndex; i += 1) {
      const id = dispatcherScan.ids[i];
      if (dispatcherTried.has(id)) continue;
      dispatcherTried.add(id);
      info.factoryTried += 1;
      let exp = null;
      try {
        exp = req(id);
      } catch (err) {
        info.factoryErrors += 1;
        continue;
      }
      scanExports(exp);
      if (candidates.length) break;
    }

    dispatcherScan.index = endIndex;
    info.candidates = candidates.length;
    if (!candidates.length) return {dispatcher: null, info};
    const picked = candidates.find((c) => c.hasSubscribe) || candidates.find((c) => c.hasRegister) || candidates[0];
    return {dispatcher: picked ? picked.obj : null, info};
  }

  function formatDispatcherInfo(info) {
    if (!info) return "";
    if (info.error) {
      return `error=${info.error}`;
    }
    const chunks = info.chunkKeys && info.chunkKeys.length
      ? info.chunkKeys.join(",")
      : "none";
    const source = info.requireSource || "none";
    const factoryTotal = info.factoryTotal || 0;
    const factoryCandidates = info.factoryCandidates || 0;
    const factoryIndex = info.factoryIndex || 0;
    const factoryBatch = info.factoryBatch || 0;
    const factoryTried = info.factoryTried || 0;
    const factoryErrors = info.factoryErrors || 0;
    const accessErrors = info.accessErrors || 0;
    const factoryMode = info.factoryMode || "";
    const stage = info.scanStage ? ` stage=${info.scanStage}` : "";
    const modeLabel = factoryMode ? ` mode=${factoryMode}` : "";
    return `req=${source} chunks=${chunks} cache=${info.cacheSize} cand=${info.candidates} dispatch=${info.dispatch} subscribe=${info.subscribe} register=${info.register} factories=${factoryTotal} factcand=${factoryCandidates} scan=${factoryIndex}/${factoryCandidates} batch=${factoryBatch} tried=${factoryTried} err=${factoryErrors} accessErr=${accessErrors}${modeLabel}${stage}`;
  }

  function attachDispatcher(dispatcher) {
    let attached = false;
    let attachMode = "";
    if (typeof dispatcher.subscribe === "function") {
      dispatcher.subscribe("MESSAGE_CREATE", handler);
      attached = true;
      attachMode = "subscribe";
    } else if (typeof dispatcher.register === "function") {
      dispatcher.register((payload) => {
        if (!payload || payload.type !== "MESSAGE_CREATE") return;
        handler(payload.message || payload);
      });
      attached = true;
      attachMode = "register";
    }
    if (!attached) return false;
    root.__monkeyMessageWatcher = {
      active: true,
      handler: handler,
      mode: attachMode
    };
    emitStatus(`dispatcher attached (${attachMode})`);
    return true;
  }

  function attemptDispatcher() {
    try {
      const result = locateDispatcher();
      if (!result || !result.dispatcher) {
        return {attached: false, info: result ? result.info : null};
      }
      return {attached: attachDispatcher(result.dispatcher), info: result.info};
    } catch (err) {
      return {attached: false, info: {error: String(err)}};
    }
  }

  const wsHooked = installWebSocketHook();
  if (wsHooked) {
    emitStatus("websocket hook installed");
  }
  const jsonHooked = installJsonParseHook();
  if (jsonHooked) {
    emitStatus("json parse hook installed");
  }

  if (!enableDispatcherScan) {
    const domAttached = attachDomObserver();
    return {
      ok: true,
      status: domAttached ? "attached (hooks+dom)" : "attached (hooks)",
      diag
    };
  }

  const initial = attemptDispatcher();
  if (initial.attached) {
    return {ok: true, status: "attached (dispatcher)", diag};
  }

  let checks = 0;
  let maxChecks = 20;
  const maxAllowedChecks = 120;
  const waitInterval = setInterval(() => {
    checks += 1;
    const result = attemptDispatcher();
    const info = formatDispatcherInfo(result.info);
    emitStatus(`dispatcher check ${checks}/${maxChecks} ${info}`.trim());
    if (result.attached) {
      clearInterval(waitInterval);
      return;
    }
    const infoObj = result.info || {};
    const mode = infoObj.factoryMode || "";
    const total = infoObj.factoryCandidates || 0;
    const progress = infoObj.factoryIndex || 0;
    const scanDone = mode === "all" && total > 0 && progress >= total;
    if (scanDone) {
      clearInterval(waitInterval);
      emitStatus("oops we failed");
      attachDomObserver();
      return;
    }
    if (checks >= maxChecks) {
      if (mode === "all" && total > 0 && progress < total && maxChecks < maxAllowedChecks) {
        maxChecks = Math.min(maxAllowedChecks, maxChecks + 20);
        emitStatus(`dispatcher scan extended to ${maxChecks} (mode=all)`);
        return;
      }
      clearInterval(waitInterval);
      emitStatus("oops we failed");
      attachDomObserver();
    }
  }, 1000);

  root.__monkeyMessageWatcher = {
    active: true,
    handler: handler,
    mode: "waiting-dispatcher",
    interval: waitInterval
  };
  return {ok: true, status: "waiting for dispatcher", diag};
  } catch (err) {
    return {
      ok: false,
      error: "inject error: " + String(err),
      diag: {
        href: location.href,
        path: location.pathname || "",
        ready: document.readyState,
        title: document.title || ""
      }
    };
  }
})();
