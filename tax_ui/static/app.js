const pageData = JSON.parse(document.getElementById("page-data").textContent);

const runList = document.getElementById("run-list");
const versionList = document.getElementById("version-list");
const versionCopy = document.getElementById("version-copy");
const refreshVersionsButton = document.getElementById("refresh-versions");
const runForm = document.getElementById("run-form");
const statusCopy = document.getElementById("status-copy");
const selectionMeta = document.getElementById("selection-meta");
const detailActions = document.getElementById("detail-actions");
const summaryCards = document.getElementById("summary-cards");
const artifactLinks = document.getElementById("artifact-links");
const fieldTableBody = document.getElementById("field-table-body");
const validationList = document.getElementById("validation-list");
const reviewList = document.getElementById("review-list");
const validationCount = document.getElementById("validation-count");
const reviewCount = document.getElementById("review-count");
const fieldSearch = document.getElementById("field-search");

let activeRunId = null;
let activeVersionId = null;
let activeVersionDbName = pageData.defaultDbName || "tax_regulation_demo";
let pollTimer = null;
let currentFields = [];

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function statusClass(status) {
  return String(status || "unknown")
    .toLowerCase()
    .replace(/[^a-z0-9_-]/g, "-");
}

function badge(status) {
  const label = escapeHtml(status || "unknown");
  return `<span class="status-badge ${statusClass(status)}">${label}</span>`;
}

function currentFilters() {
  return {
    jurisdiction: runForm.elements.jurisdiction.value.trim() || "HR",
    tax_domain: runForm.elements.tax_domain.value.trim() || "einvoice",
    db_name: runForm.elements.db_name.value.trim() || pageData.defaultDbName || "tax_regulation_demo",
  };
}

function setSelection(record) {
  renderSummary(record);
  renderFields(record.bundle?.fields || []);
  renderList(validationList, record.validation_issues || [], "No validation issues.", validationCount, "issue", "issues");
  renderList(reviewList, record.review_items || [], "No review items.", reviewCount, "item", "items");
}

function renderRuns(runs) {
  if (!runs.length) {
    runList.innerHTML = `<div class="empty-state">No runs yet.</div>`;
    return;
  }

  runList.innerHTML = runs
    .map(
      (run) => `
        <button class="run-item ${run.run_id === activeRunId ? "active" : ""}" data-run-id="${escapeHtml(run.run_id)}">
          <div class="run-title">
            <span>${escapeHtml(run.config.version_label || run.source_name)}</span>
            ${badge(run.status)}
          </div>
          <div class="run-meta">${escapeHtml(run.source_name)}</div>
          <div class="run-meta">${escapeHtml(run.updated_at)}</div>
        </button>
      `,
    )
    .join("");

  runList.querySelectorAll(".run-item").forEach((button) => {
    button.addEventListener("click", () => {
      activeRunId = button.dataset.runId;
      activeVersionId = null;
      fetchRun(activeRunId);
      fetchRuns();
    });
  });
}

function renderVersions(versions, filters) {
  versionCopy.textContent = `${filters.jurisdiction} / ${filters.tax_domain} @ ${filters.db_name}`;

  if (!pageData.hasDbEnv) {
    versionList.innerHTML = `<div class="empty-state">Database env is missing. Set SPRING_DATASOURCE_URL and SPRING_DATASOURCE_USERNAME first.</div>`;
    return;
  }

  if (!versions.length) {
    versionList.innerHTML = `<div class="empty-state">No persisted versions for this jurisdiction and tax domain.</div>`;
    return;
  }

  versionList.innerHTML = versions
    .map(
      (version) => `
        <div class="version-card ${version.document_version_id === activeVersionId ? "active" : ""}">
          <div class="run-title">
            <span>${escapeHtml(version.version_label)}</span>
            ${badge(version.status)}
          </div>
          <div class="run-meta">${escapeHtml(version.original_filename)}</div>
          <div class="run-meta">fields ${escapeHtml(version.field_count)} · review ${escapeHtml(version.review_item_count)}</div>
          <div class="run-meta">${escapeHtml(version.created_at)}</div>
          <div class="version-actions">
            <button class="mini-button open-version" type="button" data-version-id="${escapeHtml(version.document_version_id)}" data-db-name="${escapeHtml(filters.db_name)}">Open</button>
            ${
              version.can_publish
                ? `<button class="mini-button accent publish-version" type="button" data-version-id="${escapeHtml(version.document_version_id)}" data-db-name="${escapeHtml(filters.db_name)}">Publish</button>`
                : ""
            }
          </div>
        </div>
      `,
    )
    .join("");

  versionList.querySelectorAll(".open-version").forEach((button) => {
    button.addEventListener("click", () => {
      activeVersionId = Number(button.dataset.versionId);
      activeVersionDbName = button.dataset.dbName;
      activeRunId = null;
      fetchVersion(activeVersionId, activeVersionDbName);
      fetchVersions();
    });
  });

  versionList.querySelectorAll(".publish-version").forEach((button) => {
    button.addEventListener("click", async () => {
      const versionId = Number(button.dataset.versionId);
      const dbName = button.dataset.dbName;
      await publishVersion(versionId, dbName);
    });
  });
}

function renderSummary(record) {
  const label =
    record.metadata?.version_label ||
    record.config?.version_label ||
    record.bundle?.document?.version_label ||
    record.source_name ||
    "Unknown";

  statusCopy.textContent = `${label} · ${record.status} · ${record.updated_at}`;

  const metaPills = [
    `<span class="meta-pill">${escapeHtml(record.kind === "version" ? "Persisted version" : "Run result")}</span>`,
    `<span class="meta-pill">${escapeHtml(record.source_name || "")}</span>`,
  ];
  if (record.config?.jurisdiction && record.config?.tax_domain) {
    metaPills.push(`<span class="meta-pill">${escapeHtml(record.config.jurisdiction)} / ${escapeHtml(record.config.tax_domain)}</span>`);
  }
  if (record.config?.db_name) {
    metaPills.push(`<span class="meta-pill">${escapeHtml(record.config.db_name)}</span>`);
  }
  selectionMeta.className = "selection-meta";
  selectionMeta.innerHTML = metaPills.join("");

  if (record.error) {
    summaryCards.innerHTML = `<div class="list-item error-box">${escapeHtml(record.error)}</div>`;
  } else if (record.summary) {
    const summary = record.summary;
    const fieldCount = summary.diff_summary?.candidate_field_count ?? record.bundle?.fields?.length ?? record.metadata?.field_count ?? 0;
    summaryCards.innerHTML = `
      <div class="summary-card"><span>Fields</span><strong>${escapeHtml(fieldCount)}</strong></div>
      <div class="summary-card"><span>Validation</span><strong>${escapeHtml(summary.validation_issue_count ?? 0)}</strong></div>
      <div class="summary-card"><span>Review</span><strong>${escapeHtml(summary.review_item_count ?? 0)}</strong></div>
      <div class="summary-card"><span>LLM</span><strong>${summary.llm?.enabled ? escapeHtml(summary.llm.model || "enabled") : "disabled"}</strong></div>
    `;
  } else {
    summaryCards.innerHTML = `<div class="summary-card"><span>Status</span><strong>${escapeHtml(record.status)}</strong></div>`;
  }

  artifactLinks.innerHTML = Object.entries(record.artifact_urls || {})
    .map(([name, url]) => `<a href="${url}" target="_blank" rel="noreferrer">${escapeHtml(name)}</a>`)
    .join("");

  renderDetailActions(record);
}

function renderDetailActions(record) {
  const actions = [];

  if (record.kind === "version" && record.can_publish) {
    actions.push(
      `<button class="mini-button accent publish-action" type="button" data-version-id="${escapeHtml(record.version_id)}" data-db-name="${escapeHtml(record.config.db_name)}">Publish This Version</button>`,
    );
  }

  const persistedVersionId = record.summary?.database?.document_version_id;
  const persistedDbName = record.summary?.database?.database_name || record.config?.db_name;
  if (record.kind === "run" && persistedVersionId && persistedDbName) {
    actions.push(
      `<button class="mini-button secondary open-version-action" type="button" data-version-id="${escapeHtml(persistedVersionId)}" data-db-name="${escapeHtml(persistedDbName)}">Open Persisted Version</button>`,
    );
    if (record.summary?.database?.document_status !== "published") {
      actions.push(
        `<button class="mini-button accent publish-action" type="button" data-version-id="${escapeHtml(persistedVersionId)}" data-db-name="${escapeHtml(persistedDbName)}">Publish Persisted Version</button>`,
      );
    }
  }

  detailActions.innerHTML = actions.join("");

  detailActions.querySelectorAll(".open-version-action").forEach((button) => {
    button.addEventListener("click", () => {
      activeVersionId = Number(button.dataset.versionId);
      activeVersionDbName = button.dataset.dbName;
      activeRunId = null;
      fetchVersion(activeVersionId, activeVersionDbName);
      fetchVersions();
    });
  });

  detailActions.querySelectorAll(".publish-action").forEach((button) => {
    button.addEventListener("click", async () => {
      const versionId = Number(button.dataset.versionId);
      const dbName = button.dataset.dbName;
      await publishVersion(versionId, dbName);
    });
  });
}

function renderFields(fields) {
  currentFields = fields || [];
  applyFieldFilter();
}

function applyFieldFilter() {
  const query = fieldSearch.value.trim().toLowerCase();
  const visible = currentFields.filter((field) => {
    if (!query) return true;
    const haystack = [
      field.field_code,
      field.field_name,
      field.data_type,
      field.semantic_notes,
      field.sample_value,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return haystack.includes(query);
  });

  if (!visible.length) {
    fieldTableBody.innerHTML = `<tr><td colspan="6" class="empty-cell">No matching fields.</td></tr>`;
    return;
  }

  fieldTableBody.innerHTML = visible
    .map((field) => {
      const min = field.occurrence_min ?? "";
      const max = field.occurrence_max ?? "";
      return `
        <tr>
          <td>${escapeHtml(field.field_code)}</td>
          <td>${escapeHtml(field.field_name || "")}</td>
          <td>${escapeHtml(field.data_type || "")}</td>
          <td>${escapeHtml(`${min}${min !== "" || max !== "" ? ".." : ""}${max}`)}</td>
          <td>${escapeHtml(field.sample_value || "")}</td>
          <td>${escapeHtml(field.semantic_notes || "")}</td>
        </tr>
      `;
    })
    .join("");
}

function renderList(target, items, emptyMessage, countTarget, singular, plural) {
  countTarget.textContent = `${items.length} ${items.length === 1 ? singular : plural}`;
  if (!items.length) {
    target.className = "list-block empty-state";
    target.textContent = emptyMessage;
    return;
  }

  target.className = "list-block";
  target.innerHTML = items
    .map((item) => {
      const title = item.code || item.item_id || item.change?.field_code || "Item";
      const body = item.message || item.change?.explanation || item.severity || "";
      const extra = item.change?.change_type ? `<small>${escapeHtml(item.change.change_type)}</small>` : "";
      return `<div class="list-item"><strong>${escapeHtml(title)}</strong><div>${escapeHtml(body)}</div>${extra}</div>`;
    })
    .join("");
}

async function fetchRuns() {
  const response = await fetch("/api/runs");
  const payload = await response.json();
  renderRuns(payload.runs || []);
}

async function fetchVersions() {
  if (!pageData.hasDbEnv) {
    renderVersions([], currentFilters());
    return;
  }

  const filters = currentFilters();
  const params = new URLSearchParams({
    jurisdiction: filters.jurisdiction,
    tax_domain: filters.tax_domain,
    db_name: filters.db_name,
  });
  const response = await fetch(`/api/document-versions?${params.toString()}`);
  const payload = await response.json();

  if (!response.ok) {
    versionCopy.textContent = payload.detail || "Failed to load versions.";
    versionList.innerHTML = `<div class="empty-state">${escapeHtml(payload.detail || "Failed to load versions.")}</div>`;
    return;
  }

  renderVersions(payload.versions || [], filters);
}

async function fetchRun(runId) {
  const response = await fetch(`/api/runs/${runId}`);
  const run = await response.json();
  setSelection(run);

  if (run.status === "queued" || run.status === "running") {
    clearTimeout(pollTimer);
    pollTimer = setTimeout(() => fetchRun(runId), 2500);
  } else {
    clearTimeout(pollTimer);
    await fetchRuns();
    if (run.summary?.database?.document_version_id) {
      await fetchVersions();
    }
  }
}

async function fetchVersion(versionId, dbName) {
  const params = new URLSearchParams({ db_name: dbName });
  const response = await fetch(`/api/document-versions/${versionId}?${params.toString()}`);
  const payload = await response.json();

  if (!response.ok) {
    statusCopy.textContent = payload.detail || "Failed to load version.";
    return;
  }

  setSelection(payload);
}

async function publishVersion(versionId, dbName) {
  const formData = new FormData();
  formData.set("db_name", dbName);
  formData.set("reviewer", "web-ui");
  formData.set("comment", "Published from browser console.");

  const response = await fetch(`/api/document-versions/${versionId}/publish`, {
    method: "POST",
    body: formData,
  });
  const payload = await response.json();

  if (!response.ok) {
    statusCopy.textContent = payload.detail || "Publish failed.";
    return;
  }

  activeVersionId = versionId;
  activeVersionDbName = dbName;
  setSelection(payload);
  await fetchVersions();
}

async function createRun(event) {
  event.preventDefault();
  const formData = new FormData(runForm);
  const response = await fetch("/api/runs", {
    method: "POST",
    body: formData,
  });

  const payload = await response.json();
  if (!response.ok) {
    statusCopy.textContent = payload.detail || "Run failed to start.";
    return;
  }

  activeRunId = payload.run_id;
  activeVersionId = null;
  statusCopy.textContent = `Run ${payload.run_id} queued...`;
  await fetchRuns();
  await fetchRun(activeRunId);
}

runForm.addEventListener("submit", createRun);
fieldSearch.addEventListener("input", applyFieldFilter);
refreshVersionsButton.addEventListener("click", fetchVersions);
["jurisdiction", "tax_domain", "db_name"].forEach((name) => {
  runForm.elements[name].addEventListener("change", fetchVersions);
});

fetchRuns();
fetchVersions();
