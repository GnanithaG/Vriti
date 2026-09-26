// Vriti phone app.
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtDate = (iso) => { if (!iso) return ""; const d = new Date(iso.length <= 10 ? iso + "T12:00:00" : iso); return isNaN(d) ? "" : d.toLocaleDateString(undefined, { month: "short", day: "numeric" }); };
const ago = (iso) => { if (!iso) return ""; const m = (Date.now() - new Date(iso)) / 60000; if (isNaN(m)) return ""; if (m < 60) return Math.max(1, Math.round(m)) + "m ago"; if (m < 1440) return Math.round(m / 60) + "h ago"; return Math.round(m / 1440) + "d ago"; };
const todayISO = () => new Date().toISOString().slice(0, 10);
const TRACK = ["Applied", "Interview", "Offer", "Rejected"];
const PF = ["name", "email", "phone", "location", "linkedin", "portfolio", "auth", "sponsor", "salary", "start", "relocate", "workpref", "years", "eeo", "answers"];

const S = { jobs: [], settings: { profile: {}, search: {}, resume: {} }, status: {}, sel: new Set(), sort: "score", openId: null, tf: "All", rtab: "resume", detail: {} };

let tt; function toast(m) { const t = $("#toast"); t.textContent = m; t.hidden = false; clearTimeout(tt); tt = setTimeout(() => (t.hidden = true), 3000); }

async function api(path, opts = {}) {
  const init = { method: opts.method || "GET", headers: {}, credentials: "same-origin" };
  if (opts.body instanceof FormData) init.body = opts.body;
  else if (opts.body !== undefined) { init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(opts.body); }
  const r = await fetch("/api" + path, init);
  if (r.status === 401 && path !== "/login") { showLogin(); throw new Error("Please sign in."); }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || "Something went wrong. Try again.");
  return data;
}

/* ---------- login ---------- */
function showLogin() { $("#app").hidden = true; $("#login").hidden = false; }
$("#loginForm").addEventListener("submit", async (e) => {
  e.preventDefault(); $("#loginErr").hidden = true;
  try { await api("/login", { method: "POST", body: { password: $("#pw").value } }); $("#pw").value = ""; start(); }
  catch (err) { $("#loginErr").textContent = err.message; $("#loginErr").hidden = false; }
});
$("#logout").addEventListener("click", async () => { await api("/logout", { method: "POST" }).catch(() => {}); showLogin(); });

/* ---------- tabs ---------- */
function show(v) {
  $$(".tab").forEach((t) => t.setAttribute("aria-selected", t.dataset.view === v ? "true" : "false"));
  ["inbox", "review", "tracker", "profile"].forEach((x) => ($("#view-" + x).hidden = x !== v));
  history.replaceState(null, "", "#" + v); window.scrollTo({ top: 0 });
}
$$(".tab").forEach((t) => t.addEventListener("click", () => show(t.dataset.view)));

/* ---------- data loading ---------- */
async function refresh() {
  const [jobs, status] = await Promise.all([api("/jobs"), api("/status")]);
  S.jobs = jobs; S.status = status;
  render();
}
let pollTimer;
function schedulePoll() {
  clearTimeout(pollTimer);
  const busy = S.status.searching || S.jobs.some((j) => ["tailoring", "ready", "applying"].includes(j.status));
  pollTimer = setTimeout(async () => { if (document.visibilityState === "visible") await refresh().catch(() => {}); schedulePoll(); }, busy ? 4000 : 30000);
}
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") refresh().catch(() => {}); });

/* ---------- inbox ---------- */
function scoreRing(score) {
  const s = Math.max(0, Math.min(100, +score || 0));
  const col = s >= 80 ? "var(--good)" : s >= 65 ? "var(--accent)" : "var(--warn)";
  return `<div class="score" style="background:conic-gradient(${col} ${s * 3.6}deg,var(--sunk) 0)"><span>${s || "–"}</span></div>`;
}
function renderInbox() {
  const list = S.jobs.filter((j) => j.status === "new" || j.status === "tailoring");
  list.sort(S.sort === "score" ? (a, b) => (b.fit?.score || 0) - (a.fit?.score || 0) : (a, b) => String(b.foundAt || "").localeCompare(a.foundAt || ""));
  const nNew = list.filter((j) => j.status === "new").length;
  $("#cInbox").textContent = nNew; $("#cInbox").classList.toggle("hot", nNew > 0);
  const box = $("#inboxList");
  box.innerHTML = !list.length
    ? `<div class="empty"><strong>No new jobs right now</strong><span>New matches arrive after each search. Tap Search now to run one.</span></div>`
    : list.map((j) => `
    <div class="job ${S.sel.has(j.id) ? "sel" : ""}" data-id="${esc(j.id)}">
      ${j.status === "tailoring" ? `<span class="spin" style="margin-top:4px" aria-label="Tailoring"></span>` : `<input type="checkbox" aria-label="Select ${esc(j.title)}" ${S.sel.has(j.id) ? "checked" : ""}>`}
      <div>
        <h3>${esc(j.title)}</h3>
        <div class="meta"><strong style="color:var(--ink)">${esc(j.company)}</strong><span>${esc(j.location || "")}${j.remote && !/remote/i.test(j.location || "") ? " · Remote" : ""}</span></div>
        <div class="meta"><span class="src">${esc(j.source || "Web")}</span>${j.jobType ? `<span>${esc(j.jobType)}</span>` : ""}${j.salary ? `<span>${esc(j.salary)}</span>` : ""}<span>${esc(ago(j.postedAt || j.foundAt))}</span>${["greenhouse", "lever", "ashby"].includes(j.ats) ? `<span class="pill good">Auto-apply</span>` : ""}</div>
        ${j.status === "tailoring" ? `<p class="why muted">Tailoring your resume…</p>` : j.fit?.reason ? `<p class="why">${esc(j.fit.reason)}</p>` : ""}
        ${j.error ? `<p class="why" style="color:var(--bad)">${esc(j.error)}</p>` : ""}
      </div>
      ${scoreRing(j.fit?.score)}
      <div class="actions">
        <button class="btn small" data-more>Details</button>
        ${j.url ? `<a class="btn small ghost" href="${esc(j.url)}" target="_blank" rel="noopener">Posting ↗</a>` : ""}
        ${j.status === "new" ? `<button class="btn small ghost" data-skip>Skip</button>` : ""}
      </div>
      <div class="jd" data-jd hidden style="grid-column:1/-1">${esc(j.jd || "No description saved.")}</div>
    </div>`).join("");
  $$(".job", box).forEach((el) => {
    const id = el.dataset.id;
    $("input", el)?.addEventListener("change", (e) => { e.target.checked ? S.sel.add(id) : S.sel.delete(id); el.classList.toggle("sel", e.target.checked); renderSel(); });
    $("[data-more]", el).addEventListener("click", () => { const d = $("[data-jd]", el); d.hidden = !d.hidden; });
    $("[data-skip]", el)?.addEventListener("click", () => skip([id]));
  });
  renderSel();
  const st = S.status.searchState || {};
  $("#lastRun").innerHTML = S.status.searching ? `<span class="spin"></span> Searching now…` : st.lastRunAt ? `Last search ${esc(ago(st.lastRunAt))}: ${st.lastRunFound ?? 0} new.` : "Searches run at 11am, 3pm and 7pm.";
  $("#searchNow").disabled = !!S.status.searching;
  const miss = S.status.missing || [];
  const noResume = (S.settings.resume.text || "").length < 200;
  $("#configNote").hidden = !miss.length && !noResume;
  $("#configNote").textContent = miss.length ? `Server setup incomplete. Add these in your host's environment variables: ${miss.join(", ")}.` : "Add your master resume under Me to start tailoring.";
}
function renderSel() {
  S.sel = new Set([...S.sel].filter((id) => S.jobs.some((j) => j.id === id && j.status === "new")));
  $("#selBar").hidden = !S.sel.size;
  $("#selText").textContent = `${S.sel.size} selected`;
}
$$("#sortSeg button").forEach((b) => b.addEventListener("click", () => { S.sort = b.dataset.s; $$("#sortSeg button").forEach((x) => x.setAttribute("aria-pressed", x === b)); renderInbox(); }));
async function skip(ids) {
  try { await api("/jobs/skip", { method: "POST", body: { ids } }); ids.forEach((i) => S.sel.delete(i)); toast(ids.length > 1 ? `Skipped ${ids.length} jobs` : "Skipped"); await refresh(); } catch (e) { toast(e.message); }
}
$("#skipSel").addEventListener("click", () => skip([...S.sel]));
$("#applySel").addEventListener("click", async () => {
  const ids = [...S.sel];
  try { await api("/jobs/tailor", { method: "POST", body: { ids } }); S.sel.clear(); toast(`Tailoring ${ids.length} job${ids.length > 1 ? "s" : ""}. They'll appear in Review.`); await refresh(); schedulePoll(); }
  catch (e) { toast(e.message); }
});
$("#searchNow").addEventListener("click", async () => {
  try { await api("/search/run", { method: "POST" }); toast("Searching now. New jobs appear here in a minute or two."); await refresh(); schedulePoll(); } catch (e) { toast(e.message); }
});
$("#addJob").addEventListener("click", async () => {
  try { await api("/jobs", { method: "POST", body: { url: $("#addUrl").value.trim(), jd: $("#addJd").value.trim() } }); $("#addUrl").value = ""; $("#addJd").value = ""; toast("Tailoring. It'll appear in Review."); await refresh(); schedulePoll(); }
  catch (e) { toast(e.message); }
});

/* ---------- review ---------- */
function renderReview() {
  const list = S.jobs.filter((j) => j.status === "review").sort((a, b) => String(b.tailoredAt || "").localeCompare(a.tailoredAt || ""));
  const tailoring = S.jobs.filter((j) => j.status === "tailoring").length;
  $("#cReview").textContent = list.length; $("#cReview").classList.toggle("hot", list.length > 0);
  $("#tailoringNote").hidden = !tailoring;
  $("#tailoringNote").innerHTML = `<span class="spin"></span> Tailoring ${tailoring} job${tailoring > 1 ? "s" : ""}…`;
  if (S.openId && !list.some((j) => j.id === S.openId)) S.openId = null;
  if (!S.openId && list.length) S.openId = list[0].id;
  const box = $("#reviewList");
  if (!list.length) { box.innerHTML = tailoring ? "" : `<div class="empty"><strong>Nothing to review</strong><span>Select jobs in your inbox and tap Tailor &amp; review.</span></div>`; $("#reviewDetail").innerHTML = ""; return; }
  box.innerHTML = list.length > 1 ? `<div class="seg">${list.map((j) => `<button type="button" data-open="${esc(j.id)}" aria-pressed="${j.id === S.openId}">${esc(j.company || j.title)}</button>`).join("")}</div>` : "";
  $$("[data-open]", box).forEach((b) => b.addEventListener("click", () => { S.openId = b.dataset.open; S.rtab = "resume"; renderReview(); }));
  const editing = document.activeElement?.closest?.("#rBody");
  if (!editing) renderDetail(list.find((j) => j.id === S.openId));
}
function renderDetail(job) {
  const d = $("#reviewDetail"); if (!job) { d.innerHTML = ""; return; }
  const r = job.result || {}, fit = r.fit || {};
  const lc = /strong/i.test(fit.level) ? "good" : /moderate/i.test(fit.level) ? "warn" : "bad";
  const asks = (r.answers || []).filter((a) => /^ASK ME/i.test(a.answer || "")).length;
  const auto = ["greenhouse", "lever", "ashby"].includes(job.ats);
  const ats = r.ats || {};
  d.innerHTML = `<div style="display:flex;flex-direction:column;gap:16px">
    <div class="block">
      <div class="row between" style="align-items:flex-start">
        <div><span class="label">${esc(job.source || "")}</span><h2>${esc(job.title)}</h2><p class="muted">${esc(job.company)}${job.location ? " · " + esc(job.location) : ""}</p></div>
        ${scoreRing(fit.score ?? job.fit?.score)}
      </div>
      <p><span class="pill ${lc}">${esc(fit.level || "Fit")}</span> ${esc(fit.reason || "")}</p>
      ${ats.score != null ? `<div class="row"><span class="pill ${ats.score >= 90 ? "good" : ats.score >= 75 ? "accent" : "warn"}">ATS keyword match ${esc(ats.score)}%</span></div>` : ""}
      ${(ats.missing || []).filter(Boolean).length ? `<div class="notice"><strong class="small">Missing from your resume.</strong> <span class="small">Tap any you really have, then Redo tailoring.</span><div class="chips" style="margin-top:8px">${ats.missing.filter(Boolean).map((m) => `<button type="button" class="btn small" data-have="${esc(m)}">+ ${esc(m)}</button>`).join("")}</div></div>` : ""}
      ${(r.keywords || []).length ? `<div class="chips">${r.keywords.map((k) => `<span class="chip ${k.found ? "hit" : "miss"}">${k.found ? "✓ " : ""}${esc(k.term)}</span>`).join("")}</div>` : ""}
      <div class="grid2">
        <div><span class="label">Leads with</span><ul class="plain">${(fit.strengths || []).map((s) => `<li>${esc(s)}</li>`).join("")}</ul></div>
        <div><span class="label">Gaps</span><ul class="plain">${(fit.gaps || []).map((s) => `<li>${esc(s)}</li>`).join("") || "<li class='muted'>None found</li>"}</ul></div>
      </div>
    </div>
    <div class="block">
      <div class="seg" id="rSeg">
        <button type="button" data-t="resume">Resume</button>
        <button type="button" data-t="answers">Answers${asks ? ` (${asks} to fill)` : ""}</button>
        ${r.coverLetter ? `<button type="button" data-t="letter">Cover letter</button>` : ""}
        <button type="button" data-t="changes">Changes</button>
      </div>
      <div id="rBody"></div>
    </div>
    <div class="block">
      <h3>Ready to apply?</h3>
      <p class="muted small">${auto
        ? (S.status.applySubmit ? "Approving fills in and submits this application on the server with this resume and these answers. If anything unexpected comes up, it stops and asks you." : "Approving fills in the form on the server but doesn't submit it yet (test mode is on). You'll see a screenshot in the Tracker.")
        : "This site needs your own sign-in, so approving moves it to your Tracker with the resume and answers ready to copy."}</p>
      <div class="notice warn" id="askWarn" ${asks ? "" : "hidden"}>Fill in the answers marked “ASK ME” first.</div>
      <button class="btn good big" id="approve">${auto && S.status.applySubmit ? "Approve &amp; submit" : "Approve"}</button>
      <div class="row">
        <a class="btn small ghost" href="${esc(job.applyUrl || job.url || "#")}" target="_blank" rel="noopener">Open application ↗</a>
        <button class="btn small ghost" id="retailor">Redo tailoring</button>
        <button class="btn small ghost danger" id="rSkip">Skip this job</button>
      </div>
    </div></div>`;
  $$("#rSeg button").forEach((b) => b.addEventListener("click", () => { S.rtab = b.dataset.t; renderRBody(job); }));
  if (S.rtab === "letter" && !r.coverLetter) S.rtab = "resume";
  renderRBody(job);
  $("#approve").addEventListener("click", () => approve(job));
  $("#retailor").addEventListener("click", async () => { try { await api("/jobs/tailor", { method: "POST", body: { ids: [job.id] } }); toast("Tailoring again…"); await refresh(); schedulePoll(); } catch (e) { toast(e.message); } });
  $("#rSkip").addEventListener("click", () => skip([job.id]));
  $$("[data-have]", d).forEach((b) => b.addEventListener("click", async () => {
    const p = S.settings.profile; const confirmed = [...new Set([...(p.confirmed || []), b.dataset.have])];
    try { S.settings.profile = await api("/settings/profile", { method: "PUT", body: { confirmed } }); b.disabled = true; b.textContent = "✓ " + b.dataset.have; toast("Added. Tap Redo tailoring when you're done."); } catch (e) { toast(e.message); }
  }));
}
function resumeHTML(R) {
  const sec = (t, inner) => (inner ? `<div class="rs">${esc(t)}</div>${inner}` : "");
  return `<div class="paper"><div class="rn">${esc(R.name || S.settings.profile.name || "")}</div>${R.headline ? `<div class="rh">${esc(R.headline)}</div>` : ""}
    <div class="rc">${(R.contact || []).filter(Boolean).map(esc).join("  ·  ")}</div>
    ${sec("Summary", R.summary ? `<p>${esc(R.summary)}</p>` : "")}
    ${sec("Skills", (R.skills || []).map((g) => `<div><strong>${esc(g.group)}:</strong> ${esc((g.items || []).join(", "))}</div>`).join(""))}
    ${sec("Experience", (R.experience || []).map((j) => `<div class="pj"><div class="jt"><span>${esc(j.title)} · ${esc(j.company)}${j.location ? ", " + esc(j.location) : ""}</span><span class="jdt">${esc(j.dates)}</span></div><ul>${(j.bullets || []).map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>`).join(""))}
    ${sec("Education", (R.education || []).map((e) => `<div class="pj"><div class="jt"><span>${esc(e.degree)} · ${esc(e.school)}</span><span class="jdt">${esc(e.dates)}</span></div>${e.details ? `<div>${esc(e.details)}</div>` : ""}</div>`).join(""))}
    ${(R.extra || []).map((x) => sec(x.heading, `<ul>${(x.items || []).map((i) => `<li>${esc(i)}</li>`).join("")}</ul>`)).join("")}</div>`;
}
function renderRBody(job) {
  const r = job.result || {}, b = $("#rBody");
  $$("#rSeg button").forEach((x) => x.setAttribute("aria-pressed", x.dataset.t === S.rtab));
  if (S.rtab === "resume") {
    b.innerHTML = `<div class="row"><a class="btn small" href="/api/jobs/${encodeURIComponent(job.id)}/resume.docx">Download Word</a></div><div class="paper-wrap">${resumeHTML(r.resume || {})}</div>`;
  } else if (S.rtab === "answers") {
    const ans = r.answers || [];
    b.innerHTML = `<p class="muted small">Edit anything. These exact answers are used on the form.</p>` + ans.map((a, i) => `
      <div class="qa ${/^ASK ME/i.test(a.answer || "") ? "ask" : ""}"><label class="q" for="ans-${i}">${esc(a.question)}</label><textarea id="ans-${i}" data-i="${i}">${esc(a.answer)}</textarea></div>`).join("") +
      `<button class="btn primary small" id="saveAns">Save answers</button>`;
    $("#saveAns").addEventListener("click", async () => { try { await api(`/jobs/${encodeURIComponent(job.id)}`, { method: "PATCH", body: { answers: readAnswers(job) } }); toast("Answers saved"); await refresh(); } catch (e) { toast(e.message); } });
  } else if (S.rtab === "letter") {
    b.innerHTML = `<div class="row"><a class="btn small" href="/api/jobs/${encodeURIComponent(job.id)}/cover.docx">Download Word</a></div><textarea id="letterBox" class="tall">${esc(r.coverLetter)}</textarea><button class="btn primary small" id="saveLetter">Save cover letter</button>`;
    $("#saveLetter").addEventListener("click", async () => { try { await api(`/jobs/${encodeURIComponent(job.id)}`, { method: "PATCH", body: { coverLetter: $("#letterBox").value.trim() } }); toast("Cover letter saved"); await refresh(); } catch (e) { toast(e.message); } });
  } else {
    b.innerHTML = `<ul class="plain">${(r.changes || []).map((c) => `<li>${esc(c)}</li>`).join("") || "<li class='muted'>No notes</li>"}</ul>`;
  }
}
function readAnswers(job) {
  const boxes = $$("#rBody [data-i]");
  return (job.result?.answers || []).map((a, i) => ({ question: a.question, answer: (boxes[i]?.value ?? a.answer).trim() }));
}
async function approve(job) {
  const body = {};
  if ($$("#rBody [data-i]").length) body.answers = readAnswers(job);
  if ($("#letterBox")) body.coverLetter = $("#letterBox").value.trim();
  const answers = body.answers || job.result?.answers || [];
  if (answers.some((a) => /^ASK ME/i.test(a.answer || ""))) { S.rtab = "answers"; renderRBody(job); $("#askWarn").hidden = false; toast("Fill in the ASK ME answers first"); return; }
  try {
    const r = await api(`/jobs/${encodeURIComponent(job.id)}/approve`, { method: "POST", body });
    const auto = ["greenhouse", "lever", "ashby"].includes(r.ats);
    toast(auto ? (r.willSubmit ? "Approved. Submitting now." : "Approved. Filling the form (test mode).") : "Approved. It's in your Tracker, ready for you to submit.");
    await refresh(); schedulePoll();
  } catch (e) { toast(e.message); }
}

/* ---------- tracker ---------- */
function renderTracker() {
  const inflight = S.jobs.filter((j) => ["ready", "applying", "needs_you"].includes(j.status));
  const done = S.jobs.filter((j) => j.status === "submitted" || j.status === "closed");
  const all = [...inflight, ...done];
  const needs = S.jobs.filter((j) => j.status === "needs_you").length;
  $("#cTracker").textContent = all.length; $("#cTracker").classList.toggle("hot", needs > 0);
  const cnt = (s) => done.filter((j) => j.status === "submitted" && (j.trackerStatus || "Applied") === s).length;
  $("#stats").innerHTML = [["Applied", TRACK.reduce((n, s) => n + cnt(s), 0)], ["Interviews", cnt("Interview")], ["Offers", cnt("Offer")], ["Needs you", needs]]
    .map(([k, v]) => `<div class="stat"><b class="mono">${v}</b><span>${k}</span></div>`).join("");
  const F = ["All", "Needs you", "Submitting", ...TRACK];
  $("#trackSeg").innerHTML = F.map((f) => `<button type="button" data-f="${f}" aria-pressed="${S.tf === f}">${f}</button>`).join("");
  $$("#trackSeg button").forEach((b) => b.addEventListener("click", () => { S.tf = b.dataset.f; renderTracker(); }));
  const match = (j) => S.tf === "All" || (S.tf === "Needs you" && j.status === "needs_you") || (S.tf === "Submitting" && ["ready", "applying"].includes(j.status)) || (j.status === "submitted" && (j.trackerStatus || "Applied") === S.tf);
  const list = all.filter(match).sort((a, b) => String(b.appliedAt || b.approvedAt || "").localeCompare(a.appliedAt || a.approvedAt || ""));
  const box = $("#trackList");
  if (!list.length) { box.innerHTML = `<div class="empty">${all.length ? "Nothing here." : "Applications you approve show up here with their status and follow-up dates."}</div>`; return; }
  const today = todayISO();
  box.innerHTML = list.map((j) => {
    let pill;
    if (j.status === "ready") pill = `<span class="pill accent">Queued</span>`;
    else if (j.status === "applying") pill = `<span class="pill accent"><span class="spin"></span> Submitting</span>`;
    else if (j.status === "needs_you") pill = `<span class="pill warn">Needs you</span>`;
    else if (j.status === "closed") pill = `<span class="pill">Closed</span>`;
    else { const t = j.trackerStatus || "Applied"; pill = `<span class="pill ${t === "Offer" || t === "Interview" ? "good" : t === "Rejected" ? "bad" : ""}">${esc(t)}</span>`; }
    const due = j.status === "submitted" && (j.trackerStatus || "Applied") === "Applied" && j.followUp && j.followUp <= today;
    return `<div class="block" data-id="${esc(j.id)}" style="gap:8px">
      <div class="row between" style="align-items:flex-start"><div><h3>${esc(j.title)}</h3><div class="muted small">${esc(j.company)}${j.location ? " · " + esc(j.location) : ""}</div></div>${pill}</div>
      <div class="row small muted">${j.appliedAt ? `<span class="mono">Applied ${fmtDate(j.appliedAt)}</span>` : ""}${j.followUp && j.status === "submitted" ? `<span class="pill ${due ? "warn" : ""}">${due ? "Follow up now" : "Follow up " + fmtDate(j.followUp)}</span>` : ""}<span class="src">${esc(j.source || "")}</span></div>
      ${j.note ? `<div class="notice ${j.status === "needs_you" ? "warn" : ""}">${esc(j.note)}</div>` : ""}
      ${j.hasShot ? `<details data-shot><summary class="small">Screenshot of the form</summary><img class="shot" alt="Screenshot of the application form" loading="lazy"></details>` : ""}
      <div class="row">
        ${j.status === "submitted" ? `<select aria-label="Status" data-ts style="width:auto;padding:5px 8px;font-size:13px">${TRACK.map((s) => `<option ${s === (j.trackerStatus || "Applied") ? "selected" : ""}>${s}</option>`).join("")}</select>` : ""}
        ${j.status === "needs_you" ? `<a class="btn small primary" href="${esc(j.applyUrl || j.url || "#")}" target="_blank" rel="noopener">Open application ↗</a><button class="btn small" data-mine>I submitted it</button>${["greenhouse", "lever", "ashby"].includes(j.ats) ? `<button class="btn small ghost" data-retry>Try again</button>` : ""}` : `<a class="btn small ghost" href="${esc(j.applyUrl || j.url || "#")}" target="_blank" rel="noopener">Job ↗</a>`}
        ${j.result ? `<a class="btn small ghost" href="/api/jobs/${encodeURIComponent(j.id)}/resume.docx">Resume</a>` : ""}
      </div></div>`;
  }).join("");
  $$("[data-id]", box).forEach((el) => {
    const id = el.dataset.id;
    $("[data-ts]", el)?.addEventListener("change", (e) => api(`/jobs/${encodeURIComponent(id)}`, { method: "PATCH", body: { trackerStatus: e.target.value } }).then(() => { toast("Moved to " + e.target.value); refresh(); }).catch((x) => toast(x.message)));
    $("[data-retry]", el)?.addEventListener("click", () => api(`/jobs/${encodeURIComponent(id)}/retry`, { method: "POST" }).then(() => { toast("Trying again"); refresh(); schedulePoll(); }).catch((x) => toast(x.message)));
    $("[data-mine]", el)?.addEventListener("click", () => api(`/jobs/${encodeURIComponent(id)}`, { method: "PATCH", body: { markSubmitted: true } }).then(() => { toast("Added to tracker"); refresh(); }).catch((x) => toast(x.message)));
    $("[data-shot]", el)?.addEventListener("toggle", async (e) => { const img = $("img", e.target); if (e.target.open && !img.src) { const j = await api(`/jobs/${encodeURIComponent(id)}`); img.src = j.shot || ""; } });
  });
}

/* ---------- settings ---------- */
function fillForms() {
  const { profile, search, resume } = S.settings;
  PF.forEach((f) => { const el = $("#p_" + f); if (el !== document.activeElement) el.value = profile[f] || ""; });
  $("#s_titles").value = (search.titles || []).join(", ");
  $("#s_level").value = search.level || "Mid-Senior";
  $("#s_sponsor").value = search.sponsorship || "needs";
  $$("#s_types input").forEach((i) => (i.checked = (search.jobTypes || ["Full-time"]).includes(i.value)));
  $("#s_excludes").value = search.excludes || "";
  $("#s_hours").value = search.postedWithinHours || 24;
  $("#s_max").value = search.maxPerRun || 20;
  $("#resumeText").value = resume.text || "";
  $("#resumeMeta").textContent = resume.updatedAt ? `Saved ${fmtDate(resume.updatedAt)}${resume.fileName ? " · " + resume.fileName : ""}` : "";
}
function renderAuto() {
  const st = S.status, ss = st.searchState || {};
  const src = [st.sources?.jsearch && "JSearch (LinkedIn, Indeed, ZipRecruiter, Glassdoor)", st.sources?.adzuna && "Adzuna"].filter(Boolean).join(" and ");
  $("#autoSearch").textContent = (src ? `Searching ${src}. ` : "No job API keys set yet. ") + (ss.lastRunAt ? `Last run ${ago(ss.lastRunAt)}: ${ss.lastRunFound ?? 0} new. ${ss.lastRunNote || ""}` : "");
  $("#applyMode").textContent = st.applySubmit ? "Submits after you approve" : "Test mode: fills forms, doesn't submit";
  $("#pushState").textContent = !st.push ? "Notifications aren't set up on the server yet." : notifPerm() === "granted" ? "Notifications are on for this device." : "";
  $("#enablePush").hidden = !st.push || notifPerm() === "granted";
}
$("#saveProfile").addEventListener("click", async () => {
  const body = {}; PF.forEach((f) => (body[f] = $("#p_" + f).value.trim()));
  try { S.settings.profile = await api("/settings/profile", { method: "PUT", body }); toast("Details saved"); } catch (e) { toast(e.message); }
});
$("#saveSearch").addEventListener("click", async () => {
  const body = { titles: $("#s_titles").value.split(",").map((x) => x.trim()).filter(Boolean), level: $("#s_level").value, sponsorship: $("#s_sponsor").value,
    jobTypes: $$("#s_types input:checked").map((i) => i.value), excludes: $("#s_excludes").value.trim(), postedWithinHours: +$("#s_hours").value || 24, maxPerRun: +$("#s_max").value || 20 };
  if (!body.titles.length) return toast("Add at least one job title");
  try { S.settings.search = await api("/settings/search", { method: "PUT", body }); toast("Search saved"); } catch (e) { toast(e.message); }
});
$("#saveResume").addEventListener("click", async () => {
  const text = $("#resumeText").value.trim(); if (text.length < 200) return toast("Paste your full resume");
  try { S.settings.resume = await api("/settings/resume", { method: "PUT", body: { text } }); fillForms(); toast("Resume saved"); } catch (e) { toast(e.message); }
});
$("#resumeFile").addEventListener("change", async (e) => {
  const f = e.target.files[0]; if (!f) return; toast("Reading " + f.name + "…");
  const fd = new FormData(); fd.append("file", f);
  try { S.settings.resume = await api("/resume/upload", { method: "POST", body: fd }); fillForms(); toast("Resume saved"); } catch (err) { toast(err.message); }
  e.target.value = "";
});

/* ---------- notifications ---------- */
function notifPerm() { return typeof Notification === "undefined" ? "unsupported" : Notification.permission; }
function b64ToUint8(b64) { const p = "=".repeat((4 - (b64.length % 4)) % 4); const s = atob((b64 + p).replace(/-/g, "+").replace(/_/g, "/")); return Uint8Array.from([...s].map((c) => c.charCodeAt(0))); }
$("#enablePush").addEventListener("click", async () => {
  try {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) return toast("This browser can't show notifications. On iPhone, add Vriti to your Home Screen first.");
    const perm = await Notification.requestPermission();
    if (perm !== "granted") return toast("Notifications weren't allowed.");
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToUint8(S.status.vapidPublic) });
    await api("/push/subscribe", { method: "POST", body: sub.toJSON() });
    toast("Notifications are on"); renderAuto();
  } catch (e) { toast("Couldn't turn on notifications: " + e.message); }
});

/* ---------- boot ---------- */
function render() { renderInbox(); renderReview(); renderTracker(); renderAuto(); }
async function start() {
  try {
    const [settings] = await Promise.all([api("/settings")]);
    S.settings = settings;
    $("#login").hidden = true; $("#app").hidden = false;
    fillForms(); await refresh(); schedulePoll();
    const tab = location.hash.slice(1); if (["inbox", "review", "tracker", "profile"].includes(tab)) show(tab);
  } catch { /* showLogin already handled */ }
}
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
start();
