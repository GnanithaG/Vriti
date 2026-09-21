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
      '<tr><td colspan="6" class="empty">No jobs saved yet. Use the extension to capture one.</td></tr>';
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

    jobsTbody.appendChild(tr);
  }
}

async function loadJobs() {
  const res = await fetch("/api/jobs");
  const jobs = await res.json();
  renderJobs(jobs);
}

loadProfile();
loadJobs();
