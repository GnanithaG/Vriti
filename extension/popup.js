const API_BASE = "http://127.0.0.1:8000";

const statusEl = document.getElementById("status");
const captureBtn = document.getElementById("capture-btn");
const prefillBtn = document.getElementById("prefill-btn");
const loggedOutNotice = document.getElementById("logged-out-notice");
const mainActions = document.getElementById("main-actions");

function setStatus(text) {
  statusEl.textContent = text;
}

function apiFetch(path, options = {}) {
  return fetch(`${API_BASE}${path}`, { ...options, credentials: "include" });
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

    const res = await apiFetch("/api/applications", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, ...job }),
    });

    if (res.status === 401) {
      setStatus("Your Vriti session expired. Please log in again.");
      return;
    }
    if (!res.ok) throw new Error(`API returned ${res.status}`);
    const saved = await res.json();
    setStatus(`Saved: ${saved.title || saved.url}`);
  } catch (err) {
    setStatus(`Couldn't save job. Is Vriti running locally? (${err.message})`);
  } finally {
    captureBtn.disabled = false;
  }
});

async function showResumeReminderIfAny() {
  try {
    const tab = await getActiveTab();
    if (!tab?.url) return;

    const applicationsRes = await apiFetch("/api/applications");
    if (!applicationsRes.ok) return;
    const applications = await applicationsRes.json();
    const application = applications.find((a) => a.url === tab.url);
    if (!application) return;

    const resumesRes = await apiFetch("/api/resumes");
    if (!resumesRes.ok) return;
    const resumes = await resumesRes.json();
    const tailored = resumes
      .filter((r) => r.job_id === application.job_id)
      .sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
    if (tailored.length === 0) return;

    const latest = tailored[0];
    document.getElementById("resume-reminder-name").textContent = latest.label;
    document.getElementById(
      "resume-reminder-link"
    ).href = `${API_BASE}/api/resumes/${latest.id}/download`;
    document.getElementById("resume-reminder").classList.add("visible");
  } catch {
    // Best-effort — the rest of the popup still works without this.
  }
}

prefillBtn.addEventListener("click", async () => {
  prefillBtn.disabled = true;
  setStatus("Loading your profile…");
  try {
    const res = await apiFetch("/api/prefill");
    if (res.status === 401) {
      setStatus("Your Vriti session expired. Please log in again.");
      return;
    }
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
    setStatus(`Couldn't prefill. Is Vriti running locally? (${err.message})`);
  } finally {
    prefillBtn.disabled = false;
  }
});

async function init() {
  let loggedIn = false;
  try {
    const res = await apiFetch("/api/auth/me");
    loggedIn = res.ok;
  } catch {
    // Vriti isn't reachable at all — treat like logged out; button
    // clicks will surface the real "is it running locally?" error.
  }

  if (!loggedIn) {
    loggedOutNotice.classList.add("visible");
    mainActions.classList.add("hidden");
    return;
  }

  mainActions.classList.remove("hidden");
  showResumeReminderIfAny();
}

init();
