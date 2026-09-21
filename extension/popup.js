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

async function showResumeReminderIfAny() {
  try {
    const tab = await getActiveTab();
    if (!tab?.url) return;

    const jobsRes = await fetch(`${API_BASE}/api/jobs`);
    if (!jobsRes.ok) return;
    const jobs = await jobsRes.json();
    const job = jobs.find((j) => j.url === tab.url);
    if (!job) return;

    const resumesRes = await fetch(`${API_BASE}/api/resumes`);
    if (!resumesRes.ok) return;
    const resumes = await resumesRes.json();
    const tailored = resumes
      .filter((r) => r.job_id === job.id)
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

showResumeReminderIfAny();
