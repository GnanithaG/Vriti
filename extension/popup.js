const API_BASE = "http://127.0.0.1:8000";

const statusEl = document.getElementById("status");
const captureBtn = document.getElementById("capture-btn");
const prefillBtn = document.getElementById("prefill-btn");

function setStatus(text) {
  statusEl.textContent = text;
}

async function getActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

async function sendToContentScript(tabId, message) {
  return chrome.tabs.sendMessage(tabId, message);
}

captureBtn.addEventListener("click", async () => {
  captureBtn.disabled = true;
  setStatus("Reading page…");
  try {
    const tab = await getActiveTab();
    const { job, url } = await sendToContentScript(tab.id, {
      type: "JOBPILOT_CAPTURE",
    });

    const res = await fetch(`${API_BASE}/api/jobs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, ...job }),
    });

    if (!res.ok) throw new Error(`API returned ${res.status}`);
    const saved = await res.json();
    setStatus(`Saved: ${saved.title || saved.url}`);
  } catch (err) {
    setStatus(`Couldn't save job. Is JobPilot running locally? (${err.message})`);
  } finally {
    captureBtn.disabled = false;
  }
});

prefillBtn.addEventListener("click", async () => {
  prefillBtn.disabled = true;
  setStatus("Loading your profile…");
  try {
    const res = await fetch(`${API_BASE}/api/prefill`);
    if (!res.ok) throw new Error(`API returned ${res.status}`);
    const profile = await res.json();

    const tab = await getActiveTab();
    const { filled } = await sendToContentScript(tab.id, {
      type: "JOBPILOT_PREFILL",
      profile,
    });
    setStatus(
      `Filled ${filled} field(s). Review everything, then press Submit yourself.`
    );
  } catch (err) {
    setStatus(`Couldn't prefill. Is JobPilot running locally? (${err.message})`);
  } finally {
    prefillBtn.disabled = false;
  }
});
