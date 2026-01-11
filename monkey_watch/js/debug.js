return (() => {
  const root = window;
  const watcher = root.__monkeyMessageWatcher || null;
  const queue = root.__monkeyMessageQueue || [];
  const seen = root.__monkeyMessageSeen || null;
  const logRoot = (
    document.querySelector("[data-list-id='chat-messages']") ||
    document.querySelector("[data-list-id^='chat-messages']") ||
    document.querySelector("ol[aria-label*='Messages']") ||
    document.querySelector("div[aria-label*='Messages']") ||
    document.querySelector("[role='log'][aria-label*='Messages']") ||
    document.querySelector("[role='log']")
  );

  const info = {
    href: location.href,
    path: location.pathname || "",
    ready: document.readyState,
    title: document.title || "",
    watcherActive: !!(watcher && watcher.active),
    watcherMode: watcher && watcher.mode ? watcher.mode : "",
    hasObserver: !!(watcher && watcher.observer),
    hasInterval: !!(watcher && watcher.interval),
    queueLength: Array.isArray(queue) ? queue.length : 0,
    seenSize: seen && typeof seen.size === "number" ? seen.size : 0,
    hasLogRoot: !!logRoot,
    logRootConnected: logRoot ? !!logRoot.isConnected : false
  };

  if (logRoot && logRoot.querySelectorAll) {
    const nodes = logRoot.querySelectorAll(
      "[id^='message-content-'], [data-list-item-id^='chat-messages__message-container']"
    );
    info.logNodeCount = nodes.length;
    const sample = [];
    const max = Math.min(3, nodes.length);
    for (let i = 0; i < max; i += 1) {
      const node = nodes[nodes.length - 1 - i];
      const text = (node.innerText || node.textContent || "").trim();
      if (text) {
        sample.push(text.slice(0, 120));
      }
    }
    if (sample.length) {
      info.sample = sample;
    }
  }

  try {
    if (watcher && watcher.logRoot) {
      info.logRootMatchesWatcher = watcher.logRoot === logRoot;
    }
  } catch (err) {
    // ignore
  }

  return info;
})();
