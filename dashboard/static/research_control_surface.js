(function () {
  const state = {
    results: [],
    sortKey: "sharpe",
    sortDirection: "desc",
  };

  function text(id, value) {
    const node = document.getElementById(id);
    if (node) {
      node.textContent = value == null || value === "" ? "-" : String(value);
    }
  }

  function renderWarning(containerId, messages, kind) {
    const node = document.getElementById(containerId);
    if (!node) {
      return;
    }
    if (!messages || messages.length === 0) {
      node.innerHTML = "";
      return;
    }
    const cssClass = kind === "error" ? "error" : "warning";
    node.innerHTML = `<div class="${cssClass}">${messages.join("<br>")}</div>`;
  }

  function currentItemLabel(item) {
    if (!item) {
      return "-";
    }
    const parts = [item.strategy, item.asset, item.interval].filter(Boolean);
    return parts.length > 0 ? parts.join(" ") : "-";
  }

  async function fetchJson(url, options) {
    const response = await fetch(url, options);
    return response.json();
  }

  async function loadRunStatus() {
    const payload = await fetchJson("/api/research/run-status");
    const stateArtifact = (payload.run_state || {}).artifact || {};
    const progressArtifact = (payload.run_progress || {}).artifact || {};
    const progress = progressArtifact.stage_progress || {};
    const observations = payload.dashboard_observations || {};

    text("run-status", stateArtifact.status || (payload.run_state || {}).artifact_state);
    const authoritativeRunning = stateArtifact.status === "running";
    text("run-stage", authoritativeRunning ? (progressArtifact.current_stage || stateArtifact.stage) : stateArtifact.stage);
    text("run-progress", progress.percent != null ? `${progress.percent}%` : "-");
    text("run-current-item", authoritativeRunning ? currentItemLabel(progressArtifact.current_item) : "-");
    text("run-completed", progress.total != null ? `${progress.completed}/${progress.total}` : "-");
    text("run-elapsed", progressArtifact.elapsed_seconds);
    text("run-eta", progressArtifact.eta_seconds);
    text("run-updated", stateArtifact.updated_at_utc || progressArtifact.updated_at_utc);

    const observationText = [];
    if (observations.pid_live != null) {
      observationText.push(`PID live: ${observations.pid_live}`);
    }
    if (observations.heartbeat_age_seconds != null) {
      observationText.push(`Heartbeat age: ${observations.heartbeat_age_seconds}s`);
    }
    document.getElementById("run-observations").textContent = observationText.join(" | ");
    renderWarning("run-warning", payload.warnings || [], "warning");

    const button = document.getElementById("run-research-button");
    if (button) {
      button.disabled = stateArtifact.status === "running";
    }
  }

  function renderFailureTable(rows) {
    const body = document.getElementById("failure-table-body");
    if (!body) {
      return;
    }
    if (!rows || rows.length === 0) {
      body.innerHTML = '<tr><td colspan="6" class="muted">No diagnostics available.</td></tr>';
      return;
    }
    body.innerHTML = rows.map((row) => `
      <tr>
        <td>${row.asset || "-"}</td>
        <td>${row.interval || "-"}</td>
        <td>${row.status || "-"}</td>
        <td>${row.bar_count ?? "-"}</td>
        <td>${row.fold_count ?? "-"}</td>
        <td>${row.drop_reason || "-"}</td>
      </tr>
    `).join("");
  }

  async function loadFailureDiagnostics() {
    const payload = await fetchJson("/api/research/empty-run-diagnostics");
    const artifact = payload.artifact || {};
    const summary = artifact.summary || {};
    if (payload.artifact_state !== "valid") {
      document.getElementById("failure-summary").textContent = `Diagnostics state: ${payload.artifact_state}`;
      renderWarning("failure-message", payload.artifact_error ? [payload.artifact_error] : [], "error");
      renderFailureTable([]);
      return;
    }

    const selectedAssets = (artifact.selected_assets || []).join(", ");
    const selectedIntervals = (artifact.selected_intervals || []).join(", ");
    document.getElementById("failure-summary").textContent =
      `Stage: ${artifact.failure_stage || "-"} | Assets: ${selectedAssets || "-"} | Intervals: ${selectedIntervals || "-"} | Drop reasons: ${(summary.primary_drop_reasons || []).join(", ") || "-"}`;
    renderWarning("failure-message", artifact.message ? [artifact.message] : [], "warning");
    renderFailureTable(artifact.pairs || []);
  }

  function normalizeValue(value) {
    if (typeof value === "boolean") {
      return value ? 1 : 0;
    }
    if (value == null) {
      return "";
    }
    return value;
  }

  function filteredResults() {
    const search = (document.getElementById("results-search").value || "").toLowerCase();
    const asset = document.getElementById("results-asset-filter").value;
    const interval = document.getElementById("results-interval-filter").value;
    return state.results
      .filter((row) => !asset || row.asset === asset)
      .filter((row) => !interval || row.interval === interval)
      .filter((row) => {
        if (!search) {
          return true;
        }
        return [row.strategy_name, row.asset, row.interval]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(search));
      })
      .sort((a, b) => {
        const left = normalizeValue(a[state.sortKey]);
        const right = normalizeValue(b[state.sortKey]);
        if (left === right) {
          return 0;
        }
        const comparison = left > right ? 1 : -1;
        return state.sortDirection === "asc" ? comparison : -comparison;
      });
  }

  function renderResults() {
    const rows = filteredResults();
    const body = document.getElementById("results-table-body");
    if (!body) {
      return;
    }
    if (rows.length === 0) {
      body.innerHTML = '<tr><td colspan="9" class="muted">No matching research rows.</td></tr>';
      return;
    }
    body.innerHTML = rows.map((row) => `
      <tr>
        <td>${row.strategy_name || "-"}</td>
        <td>${row.asset || "-"}</td>
        <td>${row.interval || "-"}</td>
        <td>${row.sharpe ?? "-"}</td>
        <td>${row.deflated_sharpe ?? "-"}</td>
        <td>${row.max_drawdown ?? "-"}</td>
        <td>${row.totaal_trades ?? "-"}</td>
        <td><span class="pill">${row.goedgekeurd}</span></td>
        <td><span class="pill">${row.success}</span></td>
      </tr>
    `).join("");
  }

  function populateFilterOptions(values, selectId, label) {
    const select = document.getElementById(selectId);
    if (!select) {
      return;
    }
    const current = select.value;
    const options = [`<option value="">All ${label}</option>`]
      .concat(values.map((value) => `<option value="${value}">${value}</option>`));
    select.innerHTML = options.join("");
    select.value = current;
  }

  async function loadResults() {
    const payload = await fetchJson("/api/research/latest");
    const artifact = payload.artifact || {};
    if (payload.artifact_state !== "valid") {
      document.getElementById("results-meta").textContent = `Research artifact state: ${payload.artifact_state}`;
      renderResults();
      return;
    }

    state.results = Array.isArray(artifact.results) ? artifact.results : [];
    const assetValues = [...new Set(state.results.map((row) => row.asset).filter(Boolean))].sort();
    const intervalValues = [...new Set(state.results.map((row) => row.interval).filter(Boolean))].sort();
    populateFilterOptions(assetValues, "results-asset-filter", "assets");
    populateFilterOptions(intervalValues, "results-interval-filter", "intervals");
    document.getElementById("results-meta").textContent =
      `Generated: ${artifact.generated_at_utc || "-"} | Rows: ${artifact.count ?? state.results.length}`;
    renderResults();
  }

  async function triggerRun() {
    const payload = await fetchJson("/api/research/run", { method: "POST" });
    const messages = [];
    if (payload.launch_state) {
      messages.push(`Launch state: ${payload.launch_state}`);
    }
    if (payload.error) {
      messages.push(payload.error);
    }
    if (payload.warnings) {
      messages.push(...payload.warnings);
    }
    renderWarning("run-warning", messages, payload.accepted ? "warning" : "error");
    await loadRunStatus();
  }

  function bindEvents() {
    document.getElementById("run-research-button").addEventListener("click", triggerRun);
    document.getElementById("results-search").addEventListener("input", renderResults);
    document.getElementById("results-asset-filter").addEventListener("change", renderResults);
    document.getElementById("results-interval-filter").addEventListener("change", renderResults);
    document.querySelectorAll("th[data-sort-key]").forEach((node) => {
      node.addEventListener("click", () => {
        const key = node.getAttribute("data-sort-key");
        if (state.sortKey === key) {
          state.sortDirection = state.sortDirection === "asc" ? "desc" : "asc";
        } else {
          state.sortKey = key;
          state.sortDirection = "desc";
        }
        renderResults();
      });
    });
  }

  async function refreshSlowPanels() {
    await Promise.all([loadFailureDiagnostics(), loadResults()]);
  }

  async function init() {
    bindEvents();
    await Promise.all([loadRunStatus(), refreshSlowPanels()]);
    window.setInterval(loadRunStatus, 5000);
    window.setInterval(refreshSlowPanels, 30000);
  }

  init().catch((error) => {
    renderWarning("run-warning", [String(error)], "error");
  });
})();
