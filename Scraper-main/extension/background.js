// background.js — routes messages to native Python host

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!["AGENT", "SCRAPE"].includes(msg.type)) {
    return;
  }

  const port = chrome.runtime.connectNative("com.ai_scraper.host");

  const payload = {
    mode: "agent",
    url: msg.url,
    request: msg.request,
    format: msg.format,
    pages: msg.pages || 10,
    min_price: msg.min_price,
    max_price: msg.max_price,
    brand: msg.brand,
    min_rating: msg.min_rating,
  };

  port.postMessage(payload);

  port.onMessage.addListener(response => {
    sendResponse(response);
    port.disconnect();
  });

  port.onDisconnect.addListener(() => {
    if (chrome.runtime.lastError) {
      sendResponse({ error: "Native host not running. Start native_host.py first." });
    }
  });

  return true; // keep async channel open
});