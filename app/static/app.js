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

const EMPLOYMENT_LABELS = {
  full_time: "Full-time",
  part_time: "Part-time",
  contract: "Contract",
  internship: "Internship",
  other: "Other",
};
const CONTRACT_LABELS = { w2: "W2", c2c: "C2C", c2h: "C2H" };

function employmentBadge(job) {
  if (!job.employment_type) return null;
  const badge = document.createElement("span");
  badge.className = `badge badge-${job.employment_type}`;
  let text = EMPLOYMENT_LABELS[job.employment_type] || job.employment_type;
  if (job.contract_type) text += ` · ${CONTRACT_LABELS[job.contract_type] || job.contract_type}`;
  badge.textContent = text;
  return badge;
}

function renderJobs(jobs) {
  if (jobs.length === 0) {
    jobsTbody.innerHTML =
      '<tr><td colspan="10" class="empty">No jobs match.</td></tr>';
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
      await fetch(`/api/applications/${job.id}/stage`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ stage: stageSelect.value }),
      });
      loadStats();
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

    const typeTd = document.createElement("td");
    const badge = employmentBadge(job);
    if (badge) typeTd.appendChild(badge);
    tr.appendChild(typeTd);

    tr.appendChild(stageTd);
    const savedTd = document.createElement("td");
    savedTd.textContent =
      job.stage === "saved"
        ? `Saved ${daysSince(job.created_at)}d ago`
        : `${job.stage} ${daysSince(job.updated_at)}d ago`;
    tr.appendChild(savedTd);
    tr.appendChild(linkTd);

    const fitTd = document.createElement("td");
    const fitBtn = document.createElement("button");
    fitBtn.type = "button";
    fitBtn.className = "row-btn";
    fitBtn.textContent = "Fit";
    fitBtn.addEventListener("click", () => openFitPanel(job));
    fitTd.appendChild(fitBtn);
    tr.appendChild(fitTd);

    const notesTd = document.createElement("td");
    const notesBtn = document.createElement("button");
    notesBtn.type = "button";
    notesBtn.className = "row-btn";
    notesBtn.textContent = job.notes ? "Notes ●" : "Notes";
    notesBtn.addEventListener("click", () => openNotesPanel(job));
    notesTd.appendChild(notesBtn);
    tr.appendChild(notesTd);

    const tailorTd = document.createElement("td");
    const tailorBtn = document.createElement("button");
    tailorBtn.type = "button";
    tailorBtn.className = "row-btn";
    tailorBtn.textContent = "Tailor";
    tailorBtn.addEventListener("click", () => openTailorPanel(job));
    tailorTd.appendChild(tailorBtn);
    tr.appendChild(tailorTd);

    jobsTbody.appendChild(tr);
  }
}

const jobsSearchInput = document.getElementById("jobs-search-input");
const jobsStageFilter = document.getElementById("jobs-stage-filter");
const jobsEmploymentFilter = document.getElementById("jobs-employment-filter");
const jobsContractFilter = document.getElementById("jobs-contract-filter");

let currentJobs = [];

async function loadJobs() {
  const params = new URLSearchParams({
    q: jobsSearchInput.value.trim(),
    stage: jobsStageFilter.value,
    employment_type: jobsEmploymentFilter.value,
    contract_type: jobsContractFilter.value,
  });
  const res = await fetch(`/api/applications?${params}`);
  currentJobs = await res.json();
  renderJobs(currentJobs);
}

let searchDebounceTimer;
jobsSearchInput.addEventListener("input", () => {
  clearTimeout(searchDebounceTimer);
  searchDebounceTimer = setTimeout(loadJobs, 250);
});
jobsStageFilter.addEventListener("change", loadJobs);
jobsEmploymentFilter.addEventListener("change", loadJobs);
jobsContractFilter.addEventListener("change", loadJobs);

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
    loadStats();
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
    loadStats();
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
const tailorResumeSelect = document.getElementById("tailor-resume-select");

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

  for (const select of [fitResumeSelect, tailorResumeSelect]) {
    select.innerHTML = "";
    for (const resume of resumes) {
      const opt = document.createElement("option");
      opt.value = String(resume.id);
      opt.textContent = resume.label;
      select.appendChild(opt);
    }
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
      `/api/applications/${currentFitJobId}/fit?resume_id=${resumeId}`
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

// --- Notes ---------------------------------------------------------------

const notesPanel = document.getElementById("notes-panel");
const notesPanelJobTitle = document.getElementById("notes-panel-job-title");
const notesTextarea = document.getElementById("notes-textarea");
const notesSaveBtn = document.getElementById("notes-save-btn");
const notesStatus = document.getElementById("notes-status");

let currentNotesJobId = null;

function openNotesPanel(job) {
  currentNotesJobId = job.id;
  notesPanelJobTitle.textContent = job.title || job.url;
  notesTextarea.value = job.notes || "";
  notesStatus.textContent = "";
  notesPanel.classList.remove("hidden");
  notesPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

notesSaveBtn.addEventListener("click", async () => {
  if (!currentNotesJobId) return;
  notesStatus.textContent = "Saving…";
  try {
    const res = await fetch(`/api/applications/${currentNotesJobId}/notes`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ notes: notesTextarea.value }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    notesStatus.textContent = "Saved.";
    loadJobs();
  } catch (err) {
    notesStatus.textContent = `Failed: ${err.message}`;
  }
});

// --- Stats -----------------------------------------------------------------

const statsCards = document.getElementById("stats-cards");

async function loadStats() {
  const res = await fetch("/api/stats");
  const stats = await res.json();

  statsCards.innerHTML = "";
  const cards = [
    ["Applications", stats.total_jobs],
    ...STAGES.map((stage) => [stage, stats.counts_by_stage[stage] ?? 0]),
    ["Response rate", `${stats.response_rate}%`],
  ];
  for (const [label, value] of cards) {
    const card = document.createElement("div");
    card.className = "stat-card";
    const valueEl = document.createElement("div");
    valueEl.className = "stat-value";
    valueEl.textContent = value;
    const labelEl = document.createElement("div");
    labelEl.className = "stat-label";
    labelEl.textContent = label;
    card.appendChild(valueEl);
    card.appendChild(labelEl);
    statsCards.appendChild(card);
  }
}

// --- AI-assisted resume tailoring -----------------------------------------

const tailorPanel = document.getElementById("tailor-panel");
const tailorPanelJobTitle = document.getElementById("tailor-panel-job-title");
const tailorGenerateBtn = document.getElementById("tailor-generate-btn");
const tailorStatus = document.getElementById("tailor-status");
const tailorSuggestionsEl = document.getElementById("tailor-suggestions");
const tailorSaveBlock = document.getElementById("tailor-save-block");
const tailorVersionLabel = document.getElementById("tailor-version-label");
const tailorSaveBtn = document.getElementById("tailor-save-btn");
const tailorSaveStatus = document.getElementById("tailor-save-status");

let currentTailorApplicationId = null;
let currentTailorCatalogJobId = null;
let tailorBaseResumeText = "";
let tailorBaseResumeId = null;
let tailorDecisions = []; // [{ original, editedText, accepted }]

function openTailorPanel(job) {
  currentTailorApplicationId = job.id;
  currentTailorCatalogJobId = job.job_id;
  tailorPanelJobTitle.textContent = job.title || job.url;
  tailorStatus.textContent = "";
  tailorSuggestionsEl.innerHTML = "";
  tailorSaveBlock.classList.add("hidden");
  tailorVersionLabel.value = "";
  tailorSaveStatus.textContent = "";
  tailorPanel.classList.remove("hidden");
  tailorPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function renderSuggestionCard(suggestion, index) {
  const card = document.createElement("div");
  card.className = `suggestion-card${suggestion.grounded ? "" : " ungrounded"}`;

  const originalLabel = document.createElement("div");
  originalLabel.className = "suggestion-label";
  originalLabel.textContent = "Original";
  card.appendChild(originalLabel);

  const original = document.createElement("div");
  original.className = "suggestion-original";
  original.textContent = suggestion.original;
  card.appendChild(original);

  const suggestedLabel = document.createElement("div");
  suggestedLabel.className = "suggestion-label";
  suggestedLabel.textContent = "Suggested (editable)";
  card.appendChild(suggestedLabel);

  const textarea = document.createElement("textarea");
  textarea.className = "suggestion-textarea";
  textarea.rows = 3;
  textarea.value = suggestion.suggested;
  textarea.addEventListener("input", () => {
    tailorDecisions[index].editedText = textarea.value;
  });
  card.appendChild(textarea);

  if (suggestion.rationale) {
    const rationale = document.createElement("div");
    rationale.className = "suggestion-rationale";
    rationale.textContent = suggestion.rationale;
    card.appendChild(rationale);
  }

  if (!suggestion.grounded) {
    const warning = document.createElement("div");
    warning.className = "suggestion-warning";
    warning.textContent = `⚠ Not fully grounded in your resume: ${suggestion.ungrounded_note || "review before accepting."}`;
    card.appendChild(warning);
  }

  const acceptRow = document.createElement("label");
  acceptRow.className = "suggestion-accept";
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.addEventListener("change", () => {
    tailorDecisions[index].accepted = checkbox.checked;
  });
  acceptRow.appendChild(checkbox);
  acceptRow.appendChild(document.createTextNode("Use this rewrite"));
  card.appendChild(acceptRow);

  return card;
}

tailorGenerateBtn.addEventListener("click", async () => {
  if (!currentTailorApplicationId) return;
  const resumeId = tailorResumeSelect.value;
  if (!resumeId) {
    tailorStatus.textContent = "Upload a resume first.";
    return;
  }

  tailorStatus.textContent = "Generating suggestions… this calls the Anthropic API.";
  tailorSuggestionsEl.innerHTML = "";
  tailorSaveBlock.classList.add("hidden");

  try {
    const res = await fetch(
      `/api/applications/${currentTailorApplicationId}/tailor?resume_id=${resumeId}`,
      { method: "POST" }
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const result = await res.json();

    tailorBaseResumeText = result.resume_text;
    tailorBaseResumeId = Number(resumeId);
    tailorDecisions = result.suggestions.map((s) => ({
      original: s.original,
      editedText: s.suggested,
      accepted: false,
    }));

    if (result.suggestions.length === 0) {
      tailorStatus.textContent = "No rewrite suggestions — this resume already covers the job well.";
      return;
    }

    tailorStatus.textContent = `${result.suggestions.length} suggestion(s). Review each, then accept the ones to keep.`;
    result.suggestions.forEach((s, i) => {
      tailorSuggestionsEl.appendChild(renderSuggestionCard(s, i));
    });
    tailorSaveBlock.classList.remove("hidden");
  } catch (err) {
    tailorStatus.textContent = `Failed: ${err.message}`;
  }
});

tailorSaveBtn.addEventListener("click", async () => {
  if (!currentTailorCatalogJobId || !tailorBaseResumeId) return;

  let finalText = tailorBaseResumeText;
  for (const decision of tailorDecisions) {
    if (!decision.accepted) continue;
    if (finalText.includes(decision.original)) {
      finalText = finalText.replace(decision.original, decision.editedText);
    }
  }

  tailorSaveStatus.textContent = "Saving…";
  try {
    const res = await fetch(`/api/resumes/${tailorBaseResumeId}/versions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        job_id: currentTailorCatalogJobId,
        final_text: finalText,
        label: tailorVersionLabel.value.trim() || null,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const saved = await res.json();
    tailorSaveStatus.textContent = `Saved as "${saved.label}".`;
    loadResumes();
  } catch (err) {
    tailorSaveStatus.textContent = `Failed: ${err.message}`;
  }
});

// --- Auth gate -------------------------------------------------------------

const userEmailEl = document.getElementById("user-email");
const userAvatarEl = document.getElementById("user-avatar");
const logoutBtn = document.getElementById("logout-btn");

logoutBtn.addEventListener("click", async () => {
  await fetch("/api/auth/logout", { method: "POST" });
  window.location.href = "/login";
});

async function bootstrap() {
  const meRes = await fetch("/api/auth/me");
  if (!meRes.ok) {
    window.location.href = "/login";
    return;
  }
  const me = await meRes.json();
  userEmailEl.textContent = me.email;
  userAvatarEl.textContent = me.email.charAt(0).toUpperCase();

  loadProfile();
  loadStats();
  await Promise.all([loadJobs(), loadResumes()]);

  const tailorApplicationId = new URLSearchParams(window.location.search).get("tailor");
  if (tailorApplicationId) {
    const application = currentJobs.find((j) => j.id === Number(tailorApplicationId));
    if (application) {
      openTailorPanel(application);
    }
  }
}

bootstrap();
