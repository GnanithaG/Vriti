// JobPilot content script.
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
          return {
            title: node.title || null,
            company:
              (node.hiringOrganization && node.hiringOrganization.name) ||
              null,
            location: extractLocation(node.jobLocation),
            description: stripHtml(node.description) || null,
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
  return { title, company: null, location: null, description };
}

function extractJobPosting() {
  const fromJsonLd = extractJobPostingJsonLd();
  if (fromJsonLd && (fromJsonLd.title || fromJsonLd.description)) {
    return fromJsonLd;
  }
  return extractFallback();
}

// --- Prefill preview -------------------------------------------------

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

/**
 * Fills ordinary contact fields from `profile` (as returned by
 * GET /api/prefill). Returns the number of fields filled.
 *
 * Never overwrites a field that already has a value, never touches
 * anything matching SENSITIVE_FIELD_BLOCKLIST, and never interacts with
 * submit/apply buttons.
 */
function prefillPreview(profile) {
  const fields = document.querySelectorAll("input, textarea");
  let filled = 0;

  for (const field of fields) {
    if (!isFillableTextField(field)) continue;
    if (field.value && field.value.trim() !== "") continue; // never overwrite
    if (isSensitiveField(field)) continue; // blocklist wins

    const key = matchProfileKey(field);
    if (!key) continue;
    const value = profile[key];
    if (!value) continue;

    field.value = value;
    field.dispatchEvent(new Event("input", { bubbles: true }));
    field.dispatchEvent(new Event("change", { bubbles: true }));
    highlight(field);
    filled += 1;
  }

  return filled;
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === "JOBPILOT_CAPTURE") {
    sendResponse({ job: extractJobPosting(), url: window.location.href });
    return true;
  }
  if (message.type === "JOBPILOT_PREFILL") {
    const filled = prefillPreview(message.profile || {});
    sendResponse({ filled });
    return true;
  }
  return false;
});
