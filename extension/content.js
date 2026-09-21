// Vriti content script.
//
// Two jobs, both read-only with respect to submission:
//   1. Extract job posting data (JobPosting JSON-LD, falling back to page text).
//   2. Preview-fill ordinary contact fields on an application form.
//
// Hard rule: this script never clicks Submit (or any button that looks like
// it) and never touches a field that matches the sensitive-field blocklist.

const SENSITIVE_FIELD_BLOCKLIST = new RegExp(
  [
    "gender",
    "\\bsex\\b",
    "race",
    "ethnicit", // ethnicity/ethnicities
    "disabilit", // disability/disabilities
    "veteran",
    "\\bssn\\b",
    "social.?security",
    "\\bdob\\b",
    "date.?of.?birth",
    "birth.?date",
    "salary",
    "compensation",
    "desired.?pay",
    "password",
    "credit.?card",
    "passport",
    "visa.?status",
    "citizenship",
    "national.?origin",
    "religio", // religion/religious
    "sexual.?orientation",
    "pregnan",
  ].join("|"),
  "i"
);

function extractJobPostingJsonLd() {
  const scripts = document.querySelectorAll(
    'script[type="application/ld+json"]'
  );
  for (const script of scripts) {
    let parsed;
    try {
      parsed = JSON.parse(script.textContent);
    } catch {
      continue;
    }
    const candidates = Array.isArray(parsed) ? parsed : [parsed];
    for (const candidate of candidates) {
      const graph = candidate["@graph"] ? candidate["@graph"] : [candidate];
      for (const node of graph) {
        if (node && node["@type"] === "JobPosting") {
          const rawType = Array.isArray(node.employmentType)
            ? node.employmentType.join(" ")
            : node.employmentType;
          return {
            title: node.title || null,
            company:
              (node.hiringOrganization && node.hiringOrganization.name) ||
              null,
            location: extractLocation(node.jobLocation),
            description: stripHtml(node.description) || null,
            employment_type_raw: rawType || null,
          };
        }
      }
    }
  }
  return null;
}

function extractLocation(jobLocation) {
  if (!jobLocation) return null;
  const loc = Array.isArray(jobLocation) ? jobLocation[0] : jobLocation;
  const address = loc && loc.address;
  if (!address) return null;
  const parts = [
    address.addressLocality,
    address.addressRegion,
    address.addressCountry,
  ].filter(Boolean);
  return parts.length ? parts.join(", ") : null;
}

function stripHtml(html) {
  if (!html) return null;
  const div = document.createElement("div");
  div.innerHTML = html;
  return div.textContent.trim().slice(0, 5000);
}

function extractFallback() {
  const title =
    document.querySelector("h1")?.textContent?.trim() ||
    document.title ||
    null;
  const description = document.body.innerText.slice(0, 5000);
  return { title, company: null, location: null, description, employment_type_raw: null };
}

function extractJobPosting() {
  const fromJsonLd = extractJobPostingJsonLd();
  if (fromJsonLd && (fromJsonLd.title || fromJsonLd.description)) {
    return fromJsonLd;
  }
  return extractFallback();
}

// --- Prefill preview -------------------------------------------------

// Known field selectors for major ATSs — tried before the generic
// label-guessing heuristics below, since exact selectors are more
// reliable than pattern-matching on labels/placeholders. Same
// "never overwrite / skip sensitive / never submit" rules still apply to
// every field found this way.
const SITE_HINTS = [
  {
    match: /(^|\.)greenhouse\.io$/,
    fields: {
      first_name: ['input[name="job_application[first_name]"]', "#first_name"],
      last_name: ['input[name="job_application[last_name]"]', "#last_name"],
      full_name: ["#name"],
      email: ['input[name="job_application[email]"]', "#email"],
      phone: ['input[name="job_application[phone]"]', "#phone"],
      linkedin_url: ['input[name="job_application[urls][LinkedIn]"]'],
      website_url: ['input[name="job_application[urls][Portfolio]"]'],
      location: [
        'input[name="job_application[location]"]',
        "#candidate-location input",
      ],
    },
  },
  {
    match: /(^|\.)lever\.co$/,
    fields: {
      full_name: ['input[name="name"]'],
      email: ['input[name="email"]'],
      phone: ['input[name="phone"]'],
      linkedin_url: ['input[name="urls[LinkedIn]"]'],
      website_url: ['input[name="urls[Portfolio]"]', 'input[name="urls[GitHub]"]'],
      location: ['input[name="location"]'],
    },
  },
];

function getSiteHints() {
  const host = window.location.hostname;
  const site = SITE_HINTS.find((s) => s.match.test(host));
  return site ? site.fields : null;
}

const FIELD_MATCHERS = [
  { key: "email", pattern: /\bemail\b/i },
  { key: "phone", pattern: /\bphone|\bmobile|\btel\b/i },
  { key: "first_name", pattern: /first.?name|given.?name/i },
  { key: "last_name", pattern: /last.?name|family.?name|surname/i },
  { key: "full_name", pattern: /^\s*name\s*$|full.?name/i },
  { key: "linkedin_url", pattern: /linkedin/i },
  { key: "website_url", pattern: /website|portfolio|personal.?site/i },
  { key: "address", pattern: /address(?!.*(city|state|zip|postal))/i },
  { key: "city", pattern: /\bcity\b/i },
  { key: "state", pattern: /\bstate\b|province/i },
  { key: "postal_code", pattern: /\bzip\b|postal/i },
  { key: "country", pattern: /\bcountry\b/i },
  { key: "location", pattern: /\blocation\b/i },
];

function fieldLabelText(field) {
  const parts = [
    field.name,
    field.id,
    field.getAttribute("autocomplete"),
    field.getAttribute("aria-label"),
    field.placeholder,
  ];

  if (field.id) {
    const label = document.querySelector(`label[for="${CSS.escape(field.id)}"]`);
    if (label) parts.push(label.textContent);
  }
  const closestLabel = field.closest("label");
  if (closestLabel) parts.push(closestLabel.textContent);

  return parts.filter(Boolean).join(" ");
}

function isSensitiveField(field) {
  return SENSITIVE_FIELD_BLOCKLIST.test(fieldLabelText(field));
}

function isFillableTextField(field) {
  if (field.tagName === "TEXTAREA") return true;
  if (field.tagName !== "INPUT") return false;
  const type = (field.type || "text").toLowerCase();
  return ["text", "email", "tel", "url", "search"].includes(type);
}

function matchProfileKey(field) {
  const label = fieldLabelText(field);
  for (const { key, pattern } of FIELD_MATCHERS) {
    if (pattern.test(label)) return key;
  }
  return null;
}

function highlight(field) {
  field.style.outline = "2px solid #2f6feb";
  field.style.backgroundColor = "#eaf1ff";
}

function tryFillField(field, key, profile, filledFields) {
  if (filledFields.has(field)) return false;
  if (!isFillableTextField(field)) return false;
  if (field.value && field.value.trim() !== "") return false; // never overwrite
  if (isSensitiveField(field)) return false; // blocklist wins

  const value = profile[key];
  if (!value) return false;

  field.value = value;
  field.dispatchEvent(new Event("input", { bubbles: true }));
  field.dispatchEvent(new Event("change", { bubbles: true }));
  highlight(field);
  filledFields.add(field);
  return true;
}

/**
 * Fills ordinary contact fields from `profile` (as returned by
 * GET /api/prefill). Returns the number of fields filled.
 *
 * Never overwrites a field that already has a value, never touches
 * anything matching SENSITIVE_FIELD_BLOCKLIST, and never interacts with
 * submit/apply buttons. Safe to call more than once on the same page
 * (e.g. after a multi-step form reveals new fields) — already-filled
 * fields are simply skipped.
 */
function prefillPreview(profile) {
  const filledFields = new Set();
  let filled = 0;

  const siteFields = getSiteHints();
  if (siteFields) {
    for (const [key, selectors] of Object.entries(siteFields)) {
      for (const selector of selectors) {
        const field = document.querySelector(selector);
        if (field && tryFillField(field, key, profile, filledFields)) {
          filled += 1;
          break; // first matching selector for this key wins
        }
      }
    }
  }

  for (const field of document.querySelectorAll("input, textarea")) {
    if (filledFields.has(field)) continue;
    if (!isFillableTextField(field)) continue;
    if (field.value && field.value.trim() !== "") continue; // never overwrite
    if (isSensitiveField(field)) continue; // blocklist wins

    const key = matchProfileKey(field);
    if (!key) continue;
    if (tryFillField(field, key, profile, filledFields)) {
      filled += 1;
    }
  }

  return filled;
}

// --- Multi-step forms --------------------------------------------------
//
// Some ATS forms (Workday, Greenhouse, Lever) reveal new fields only after
// the person clicks "Next" themselves — we never click it for them. Once a
// prefill has run, watch for newly-added form fields and re-run prefill
// automatically so step 2+ gets the same treatment without the person
// reopening the popup.

let lastPrefillProfile = null;
let multiStepObserver = null;
let rerunTimer = null;

function scheduleRerun() {
  if (!lastPrefillProfile) return;
  clearTimeout(rerunTimer);
  rerunTimer = setTimeout(() => prefillPreview(lastPrefillProfile), 400);
}

function hasFormField(node) {
  if (node.nodeType !== Node.ELEMENT_NODE) return false;
  return node.matches?.("input, textarea") || !!node.querySelector?.("input, textarea");
}

function ensureMultiStepObserver() {
  if (multiStepObserver) return;
  multiStepObserver = new MutationObserver((mutations) => {
    const addedFormField = mutations.some((mutation) =>
      Array.from(mutation.addedNodes).some(hasFormField)
    );
    if (addedFormField) scheduleRerun();
  });
  multiStepObserver.observe(document.body, { childList: true, subtree: true });
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === "JOBPILOT_CAPTURE") {
    sendResponse({ job: extractJobPosting(), url: window.location.href });
    return true;
  }
  if (message.type === "JOBPILOT_PREFILL") {
    lastPrefillProfile = message.profile || {};
    ensureMultiStepObserver();
    const filled = prefillPreview(lastPrefillProfile);
    sendResponse({ filled });
    return true;
  }
  return false;
});
