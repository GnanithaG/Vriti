const STAGES = ["saved", "applied", "interview", "offer", "rejected"];

const profileForm = document.getElementById("profile-form");
const profileStatus = document.getElementById("profile-status");
const jobsTbody = document.getElementById("jobs-tbody");

async function loadProfile() {
  const res = await fetch("/api/profile");
  const profile = await res.json();
  for (const [key, value] of Object.entries(profile)) {
    const field = profileForm.elements.namedItem(key);
    if (field) field.value = value ?? "";
  }
}

profileForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(profileForm).entries());
  const res = await fetch("/api/profile", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  profileStatus.textContent = res.ok ? "Saved." : "Failed to save.";
  setTimeout(() => (profileStatus.textContent = ""), 2500);
});

function daysSince(dateStr) {
  const then = new Date(dateStr.replace(" ", "T") + "Z");
  const diffMs = Date.now() - then.getTime();
  return Math.max(0, Math.floor(diffMs / (1000 * 60 * 60 * 24)));
}

function renderJobs(jobs) {
  if (jobs.length === 0) {
    jobsTbody.innerHTML =
      '<tr><td colspan="7" class="empty">No jobs saved yet. Use the extension to capture one.</td></tr>';
    return;
  }

  jobsTbody.innerHTML = "";
  for (const job of jobs) {
    const tr = document.createElement("tr");

    const stageSelect = document.createElement("select");
    for (const stage of STAGES) {
      const opt = document.createElement("option");
      opt.value = stage;
      opt.textContent = stage;
      if (stage === job.stage) opt.selected = true;
      stageSelect.appendChild(opt);
    }
    stageSelect.addEventListener("change", async () => {
      await fetch(`/api/jobs/${job.id}/stage`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ stage: stageSelect.value }),
      });
    });

    const stageTd = document.createElement("td");
    stageTd.appendChild(stageSelect);

    const linkTd = document.createElement("td");
    const a = document.createElement("a");
    a.href = job.url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.textContent = "Open";
    linkTd.appendChild(a);

    for (const value of [job.title, job.company, job.location]) {
      const td = document.createElement("td");
      td.textContent = value ?? "";
      tr.appendChild(td);
    }
    tr.appendChild(stageTd);
    const savedTd = document.createElement("td");
    savedTd.textContent = `${daysSince(job.created_at)}d ago`;
    tr.appendChild(savedTd);
    tr.appendChild(linkTd);

    const fitTd = document.createElement("td");
    const fitBtn = document.createElement("button");
    fitBtn.type = "button";
    fitBtn.className = "fit-btn";
    fitBtn.textContent = "Fit";
    fitBtn.addEventListener("click", () => openFitPanel(job));
    fitTd.appendChild(fitBtn);
    tr.appendChild(fitTd);

    jobsTbody.appendChild(tr);
  }
}

async function loadJobs() {
  const res = await fetch("/api/jobs");
  const jobs = await res.json();
  renderJobs(jobs);
}

// --- Import: paste a URL ---------------------------------------------

const urlImportForm = document.getElementById("url-import-form");
const urlImportInput = document.getElementById("url-import-input");
const urlImportStatus = document.getElementById("url-import-status");

urlImportForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  urlImportStatus.textContent = "Fetching…";
  try {
    const res = await fetch("/api/imports/url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: urlImportInput.value }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const job = await res.json();
    urlImportStatus.textContent = `Added: ${job.title || job.url}`;
    urlImportInput.value = "";
    loadJobs();
  } catch (err) {
    urlImportStatus.textContent = `Failed: ${err.message}`;
  }
});

// --- Import: Greenhouse / Lever board search --------------------------

const boardSearchForm = document.getElementById("board-search-form");
const boardTypeSelect = document.getElementById("board-type");
const boardCompanyInput = document.getElementById("board-company");
const boardKeywordInput = document.getElementById("board-keyword");
const boardSearchStatus = document.getElementById("board-search-status");
const boardResults = document.getElementById("board-results");
const boardResultsTbody = document.getElementById("board-results-tbody");
const importSelectedBtn = document.getElementById("import-selected-btn");

let boardCandidates = [];

boardSearchForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  boardSearchStatus.textContent = "Searching…";
  boardResults.classList.add("hidden");

  const params = new URLSearchParams({
    board: boardCompanyInput.value.trim(),
    keyword: boardKeywordInput.value.trim(),
  });

  try {
    const res = await fetch(`/api/imports/${boardTypeSelect.value}?${params}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    boardCandidates = await res.json();
    renderBoardResults(boardCandidates);
    boardSearchStatus.textContent = `${boardCandidates.length} role(s) found.`;
    boardResults.classList.toggle("hidden", boardCandidates.length === 0);
  } catch (err) {
    boardSearchStatus.textContent = `Failed: ${err.message}`;
  }
});

function renderBoardResults(candidates) {
  boardResultsTbody.innerHTML = "";
  candidates.forEach((candidate, index) => {
    const tr = document.createElement("tr");

    const checkboxTd = document.createElement("td");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.dataset.index = String(index);
    checkbox.checked = true;
    checkboxTd.appendChild(checkbox);
    tr.appendChild(checkboxTd);

    const titleTd = document.createElement("td");
    titleTd.textContent = candidate.title ?? "";
    tr.appendChild(titleTd);

    const locationTd = document.createElement("td");
    locationTd.textContent = candidate.location ?? "";
    tr.appendChild(locationTd);

    boardResultsTbody.appendChild(tr);
  });
}

importSelectedBtn.addEventListener("click", async () => {
  const checked = Array.from(
    boardResultsTbody.querySelectorAll('input[type="checkbox"]:checked')
  ).map((cb) => boardCandidates[Number(cb.dataset.index)]);

  if (checked.length === 0) return;

  boardSearchStatus.textContent = "Importing…";
  try {
    const res = await fetch("/api/imports/bulk", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jobs: checked }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const saved = await res.json();
    boardSearchStatus.textContent = `Imported ${saved.length} job(s).`;
    boardResults.classList.add("hidden");
    loadJobs();
  } catch (err) {
    boardSearchStatus.textContent = `Failed: ${err.message}`;
  }
});

// --- Resumes -----------------------------------------------------------

const resumeUploadForm = document.getElementById("resume-upload-form");
const resumeLabelInput = document.getElementById("resume-label-input");
const resumeFileInput = document.getElementById("resume-file-input");
const resumeUploadStatus = document.getElementById("resume-upload-status");
const resumesList = document.getElementById("resumes-list");
const fitResumeSelect = document.getElementById("fit-resume-select");

let resumes = [];

function renderResumes() {
  if (resumes.length === 0) {
    resumesList.innerHTML = '<li class="empty">No resumes uploaded yet.</li>';
  } else {
    resumesList.innerHTML = "";
    for (const resume of resumes) {
      const li = document.createElement("li");
      const label = document.createElement("span");
      label.textContent = resume.label;
      const date = document.createElement("span");
      date.className = "resume-date";
      date.textContent = resume.created_at;
      li.appendChild(label);
      li.appendChild(date);
      resumesList.appendChild(li);
    }
  }

  fitResumeSelect.innerHTML = "";
  for (const resume of resumes) {
    const opt = document.createElement("option");
    opt.value = String(resume.id);
    opt.textContent = resume.label;
    fitResumeSelect.appendChild(opt);
  }
}

async function loadResumes() {
  const res = await fetch("/api/resumes");
  resumes = await res.json();
  renderResumes();
}

resumeUploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = resumeFileInput.files[0];
  if (!file) return;

  resumeUploadStatus.textContent = "Uploading…";
  const formData = new FormData();
  formData.append("label", resumeLabelInput.value);
  formData.append("file", file);

  try {
    const res = await fetch("/api/resumes", { method: "POST", body: formData });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    resumeUploadStatus.textContent = "Uploaded.";
    resumeUploadForm.reset();
    loadResumes();
  } catch (err) {
    resumeUploadStatus.textContent = `Failed: ${err.message}`;
  }
});

// --- Fit analysis --------------------------------------------------------

const fitPanel = document.getElementById("fit-panel");
const fitPanelJobTitle = document.getElementById("fit-panel-job-title");
const fitAnalyzeBtn = document.getElementById("fit-analyze-btn");
const fitResults = document.getElementById("fit-results");

let currentFitJobId = null;

function openFitPanel(job) {
  currentFitJobId = job.id;
  fitPanelJobTitle.textContent = job.title || job.url;
  fitResults.innerHTML = "";
  fitPanel.classList.remove("hidden");
  fitPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function renderTermChips(container, heading, terms, kind) {
  const group = document.createElement("div");
  group.className = "term-group";
  const h4 = document.createElement("h4");
  h4.textContent = `${heading} (${terms.length})`;
  group.appendChild(h4);

  if (terms.length === 0) {
    const none = document.createElement("span");
    none.className = "hint";
    none.textContent = "None.";
    group.appendChild(none);
  } else {
    for (const term of terms) {
      const chip = document.createElement("span");
      chip.className = `term-chip ${kind}`;
      chip.textContent = term;
      group.appendChild(chip);
    }
  }
  container.appendChild(group);
}

fitAnalyzeBtn.addEventListener("click", async () => {
  if (!currentFitJobId) return;
  const resumeId = fitResumeSelect.value;
  if (!resumeId) {
    fitResults.innerHTML = '<p class="hint">Upload a resume first.</p>';
    return;
  }

  fitResults.innerHTML = '<p class="hint">Analyzing…</p>';
  try {
    const res = await fetch(
      `/api/jobs/${currentFitJobId}/fit?resume_id=${resumeId}`
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const result = await res.json();

    fitResults.innerHTML = "";
    const scoreEl = document.createElement("div");
    const scoreClass = result.score >= 70 ? "good" : result.score >= 40 ? "mid" : "low";
    scoreEl.className = `fit-score ${scoreClass}`;
    scoreEl.textContent = `${result.score}% match`;
    fitResults.appendChild(scoreEl);

    renderTermChips(fitResults, "Matched terms", result.matched_terms, "matched");
    renderTermChips(fitResults, "Missing from resume", result.missing_terms, "missing");
  } catch (err) {
    fitResults.innerHTML = `<p class="hint">Failed: ${err.message}</p>`;
  }
});

loadProfile();
loadJobs();
loadResumes();
