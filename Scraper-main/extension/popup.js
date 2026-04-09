let currentUrl = "";

function addMsg(text, type = "bot") {
  const chat = document.getElementById("scrape-chat");
  const div = document.createElement("div");
  div.className = `msg ${type}`;
  div.textContent = text;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

function setBusy(on) {
  const btn = document.getElementById("run-btn");
  btn.disabled = on;
  btn.textContent = on ? "RUNNING..." : "RUN EXTRACTION";
}

chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
  if (!tabs || !tabs[0]) {
    return;
  }
  currentUrl = tabs[0].url || "";
  document.getElementById("url-bar").textContent = currentUrl || "No active URL";
});

addMsg("Universal mode active. Works on ecommerce, directories, dashboards, articles, and unknown pages.", "bot");

document.getElementById("run-btn").addEventListener("click", () => {
  const query = document.getElementById("query").value.trim();
  const effectiveQuery = query || "";
  const pages = parseInt(document.getElementById("pages").value, 10) || 10;
  const format = document.getElementById("format").value;

  if (!currentUrl || currentUrl.startsWith("chrome://")) {
    addMsg("Open a website tab before running extraction.", "bot");
    return;
  }

  const payload = {
    type: "AGENT",
    url: currentUrl,
    request: effectiveQuery,
    pages,
    format,
    min_price: document.getElementById("min-price").value.trim() || null,
    max_price: document.getElementById("max-price").value.trim() || null,
    brand: document.getElementById("brand").value.trim() || null,
    min_rating: document.getElementById("rating").value.trim() || null,
  };

  if (effectiveQuery) {
    addMsg(`Starting extraction: ${effectiveQuery}`, "user");
  } else {
    addMsg("Starting extraction: auto-detect and scrape all structured records", "user");
  }
  setBusy(true);

  chrome.runtime.sendMessage(payload, (response) => {
    setBusy(false);
    if (chrome.runtime.lastError) {
      addMsg("Native host not connected. Start the Python backend.", "bot");
      return;
    }
    if (!response) {
      addMsg("No response received from backend.", "bot");
      return;
    }
    if (response.error) {
      addMsg(`Error: ${response.error}`, "bot");
      return;
    }
    if (response.summary) {
      addMsg(response.summary, "bot");
      return;
    }
    addMsg("Extraction request completed.", "bot");
  });
});