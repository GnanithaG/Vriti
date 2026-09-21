const userEmailEl = document.getElementById("user-email");
const userAvatarEl = document.getElementById("user-avatar");
const logoutBtn = document.getElementById("logout-btn");

const onboardingSection = document.getElementById("onboarding-section");
const onboardingForm = document.getElementById("onboarding-upload-form");
const onboardingLabelInput = document.getElementById("onboarding-label-input");
const onboardingFileInput = document.getElementById("onboarding-file-input");
const onboardingStatus = document.getElementById("onboarding-status");

const matchesSection = document.getElementById("matches-section");
const resumeSelect = document.getElementById("resume-select");
const uploadAnotherBtn = document.getElementById("upload-another-btn");
const anotherUploadForm = document.getElementById("another-upload-form");
const anotherLabelInput = document.getElementById("another-label-input");
const anotherFileInput = document.getElementById("another-file-input");
const matchesStatus = document.getElementById("matches-status");
const thinCatalogHint = document.getElementById("thin-catalog-hint");
const matchesList = document.getElementById("matches-list");
const careersEmploymentFilter = document.getElementById("careers-employment-filter");
const careersContractFilter = document.getElementById("careers-contract-filter");

logoutBtn.addEventListener("click", async () => {
  await fetch("/api/auth/logout", { method: "POST" });
  window.location.href = "/login";
});

async function uploadResume(label, file) {
  const formData = new FormData();
  formData.append("label", label);
  formData.append("file", file);
  const res = await fetch("/api/resumes", { method: "POST", body: formData });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

onboardingForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  onboardingStatus.textContent = "Uploading…";
  try {
    await uploadResume(onboardingLabelInput.value, onboardingFileInput.files[0]);
    onboardingStatus.textContent = "";
    await loadResumesAndMatches();
  } catch (err) {
    onboardingStatus.textContent = `Failed: ${err.message}`;
  }
});

uploadAnotherBtn.addEventListener("click", () => {
  anotherUploadForm.classList.toggle("hidden");
});

anotherUploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  matchesStatus.textContent = "Uploading…";
  try {
    const resume = await uploadResume(anotherLabelInput.value, anotherFileInput.files[0]);
    anotherUploadForm.reset();
    anotherUploadForm.classList.add("hidden");
    await loadResumesAndMatches(resume.id);
  } catch (err) {
    matchesStatus.textContent = `Failed: ${err.message}`;
  }
});

resumeSelect.addEventListener("change", () => loadMatches(Number(resumeSelect.value)));
careersEmploymentFilter.addEventListener("change", () => loadMatches(Number(resumeSelect.value)));
careersContractFilter.addEventListener("change", () => loadMatches(Number(resumeSelect.value)));

function scoreClass(score) {
  return score >= 70 ? "good" : score >= 40 ? "mid" : "low";
}

const EMPLOYMENT_LABELS = {
  full_time: "Full-time",
  part_time: "Part-time",
  contract: "Contract",
  internship: "Internship",
  other: "Other",
};
const CONTRACT_LABELS = { w2: "W2", c2c: "C2C", c2h: "C2H" };

function employmentBadge(match) {
  if (!match.employment_type) return null;
  const badge = document.createElement("span");
  badge.className = `badge badge-${match.employment_type}`;
  let text = EMPLOYMENT_LABELS[match.employment_type] || match.employment_type;
  if (match.contract_type) text += ` · ${CONTRACT_LABELS[match.contract_type] || match.contract_type}`;
  badge.textContent = text;
  return badge;
}

function renderChips(terms, kind) {
  const wrap = document.createElement("div");
  wrap.className = "term-group";
  for (const term of terms.slice(0, 12)) {
    const chip = document.createElement("span");
    chip.className = `term-chip ${kind}`;
    chip.textContent = term;
    wrap.appendChild(chip);
  }
  return wrap;
}

function renderMatchCard(match) {
  const card = document.createElement("div");
  card.className = "match-card";

  const header = document.createElement("div");
  header.className = "match-header";

  const titleBlock = document.createElement("div");
  const title = document.createElement("div");
  title.className = "match-title";
  title.textContent = match.title || match.url;
  const meta = document.createElement("div");
  meta.className = "match-meta";
  meta.textContent = [match.company, match.location].filter(Boolean).join(" · ");
  titleBlock.appendChild(title);
  titleBlock.appendChild(meta);
  const badge = employmentBadge(match);
  if (badge) titleBlock.appendChild(badge);
  header.appendChild(titleBlock);

  const score = document.createElement("div");
  score.className = `match-score ${scoreClass(match.score)}`;
  score.textContent = `${match.score}%`;
  header.appendChild(score);

  card.appendChild(header);

  if (match.matched_terms.length > 0) card.appendChild(renderChips(match.matched_terms, "matched"));
  if (match.missing_terms.length > 0) card.appendChild(renderChips(match.missing_terms, "missing"));

  const actions = document.createElement("div");
  actions.className = "match-actions";

  const openLink = document.createElement("a");
  openLink.href = match.url;
  openLink.target = "_blank";
  openLink.rel = "noopener noreferrer";
  openLink.className = "secondary-btn";
  openLink.textContent = "Open posting";
  actions.appendChild(openLink);

  const saveBtn = document.createElement("button");
  saveBtn.type = "button";
  saveBtn.textContent = match.saved ? "Saved ✓" : "Save to pipeline";
  saveBtn.disabled = match.saved;
  saveBtn.addEventListener("click", async () => {
    saveBtn.disabled = true;
    saveBtn.textContent = "Saving…";
    try {
      const application = await saveMatch(match.job_id);
      match.saved = true;
      match.application_id = application.id;
      saveBtn.textContent = "Saved ✓";
    } catch {
      saveBtn.disabled = false;
      saveBtn.textContent = "Save to pipeline";
    }
  });
  actions.appendChild(saveBtn);

  const tailorBtn = document.createElement("button");
  tailorBtn.type = "button";
  tailorBtn.textContent = "Tailor resume for this job";
  tailorBtn.addEventListener("click", async () => {
    tailorBtn.disabled = true;
    try {
      const application = match.saved
        ? { id: match.application_id }
        : await saveMatch(match.job_id);
      window.location.href = `/?tailor=${application.id}`;
    } catch {
      tailorBtn.disabled = false;
    }
  });
  actions.appendChild(tailorBtn);

  card.appendChild(actions);
  return card;
}

async function saveMatch(jobId) {
  const res = await fetch(`/api/careers/matches/${jobId}/save`, { method: "POST" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function loadMatches(resumeId) {
  matchesStatus.textContent = "Matching against your saved jobs…";
  matchesList.innerHTML = "";
  thinCatalogHint.classList.add("hidden");

  try {
    const params = new URLSearchParams({
      resume_id: resumeId,
      employment_type: careersEmploymentFilter.value,
      contract_type: careersContractFilter.value,
    });
    const res = await fetch(`/api/careers/matches?${params}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const result = await res.json();

    if (result.catalog_size === 0) {
      matchesStatus.textContent = "No jobs imported yet.";
      thinCatalogHint.classList.remove("hidden");
      return;
    }

    matchesStatus.textContent = `${result.matches.length} match(es) out of ${result.catalog_size} job(s) in your catalog.`;
    if (result.catalog_size < 3) thinCatalogHint.classList.remove("hidden");

    for (const match of result.matches) {
      matchesList.appendChild(renderMatchCard(match));
    }
  } catch (err) {
    matchesStatus.textContent = `Failed: ${err.message}`;
  }
}

async function loadResumesAndMatches(preferredResumeId) {
  const res = await fetch("/api/resumes");
  const resumes = await res.json();

  if (resumes.length === 0) {
    onboardingSection.classList.remove("hidden");
    matchesSection.classList.add("hidden");
    return;
  }

  onboardingSection.classList.add("hidden");
  matchesSection.classList.remove("hidden");

  resumeSelect.innerHTML = "";
  for (const resume of resumes) {
    const opt = document.createElement("option");
    opt.value = String(resume.id);
    opt.textContent = resume.label;
    resumeSelect.appendChild(opt);
  }

  const selected = preferredResumeId ?? Number(resumeSelect.value);
  resumeSelect.value = String(selected);
  await loadMatches(selected);
}

async function bootstrap() {
  const meRes = await fetch("/api/auth/me");
  if (!meRes.ok) {
    window.location.href = "/login";
    return;
  }
  const me = await meRes.json();
  userEmailEl.textContent = me.email;
  userAvatarEl.textContent = me.email.charAt(0).toUpperCase();

  loadResumesAndMatches();
}

bootstrap();
