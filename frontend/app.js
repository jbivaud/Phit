const el = (id) => document.getElementById(id);

const state = {
  runs: [],
  selected: new Set(),
};

function formatDuration(seconds) {
  if (seconds == null) return "--";
  const total = Math.round(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return h > 0
    ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`
    : `${m}:${String(s).padStart(2, "0")}`;
}

async function api(path, options) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.message || `Request failed (${res.status})`);
  return data;
}

async function refreshStatus() {
  const data = await api("/api/status");
  const statusEl = el("connection-status");
  if (data.connected) {
    statusEl.textContent = `Connected as ${data.display_name || "Garmin user"}`;
    statusEl.className = "status connected";
    el("connect-panel").hidden = true;
    el("app").hidden = false;
    await loadRuns();
  } else {
    statusEl.textContent = "Not connected";
    statusEl.className = "status";
    el("connect-panel").hidden = false;
    el("app").hidden = true;
  }
  return data.connected;
}

async function loadRuns() {
  const runs = await api("/api/runs?limit=25");
  state.runs = runs;
  state.selected.clear();
  renderRuns();
}

function renderRuns() {
  const tbody = el("runs-body");
  tbody.innerHTML = "";
  for (const run of state.runs) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><input type="checkbox" data-id="${run.id}" /></td>
      <td>${run.date || "--"}</td>
      <td>${run.name || "--"}</td>
      <td>${run.distance_km != null ? run.distance_km + " km" : "--"}</td>
      <td>${formatDuration(run.duration_s)}</td>
      <td>${run.pace_display}</td>
      <td>${run.avg_hr ?? "--"}</td>
      <td>${run.elevation_gain_m != null ? Math.round(run.elevation_gain_m) + " m" : "--"}</td>
    `;
    tbody.appendChild(tr);
  }
  tbody.querySelectorAll("input[type=checkbox]").forEach((cb) => {
    cb.addEventListener("change", onSelectRun);
  });
}

function onSelectRun(evt) {
  const id = evt.target.dataset.id;
  if (evt.target.checked) {
    if (state.selected.size >= 2) {
      evt.target.checked = false;
      return;
    }
    state.selected.add(id);
  } else {
    state.selected.delete(id);
  }
  el("compare-btn").disabled = state.selected.size !== 2;
}

function deltaClass(metric, delta) {
  if (!delta) return "";
  // For these metrics, a decrease generally means improvement (faster / lower effort).
  const lowerIsBetter = new Set(["duration_s", "pace_min_per_km", "avg_hr", "max_hr"]);
  if (!lowerIsBetter.has(metric)) return "";
  return delta.diff < 0 ? "delta-up" : delta.diff > 0 ? "delta-down" : "";
}

function formatMetric(metric, value) {
  if (value == null) return "--";
  switch (metric) {
    case "duration_s":
      return formatDuration(value);
    case "pace_min_per_km": {
      const m = Math.floor(value);
      const s = Math.round((value - m) * 60);
      return `${m}:${String(s).padStart(2, "0")}/km`;
    }
    case "distance_km":
      return `${value} km`;
    case "elevation_gain_m":
      return `${Math.round(value)} m`;
    default:
      return value;
  }
}

function formatDeltaLabel(metric, delta) {
  if (!delta) return "--";
  const sign = delta.diff > 0 ? "+" : "";
  const value = metric === "duration_s" ? formatDuration(Math.abs(delta.diff)) : Math.abs(delta.diff);
  const pct = delta.pct != null ? ` (${sign}${delta.pct}%)` : "";
  return `${sign}${delta.diff < 0 ? "-" : ""}${value}${pct}`;
}

const METRIC_LABELS = {
  distance_km: "Distance",
  duration_s: "Duration",
  pace_min_per_km: "Pace",
  avg_hr: "Avg HR",
  max_hr: "Max HR",
  avg_cadence: "Avg cadence",
  elevation_gain_m: "Elevation gain",
  calories: "Calories",
};

function renderComparison(data) {
  const { run_a, run_b, deltas } = data;
  const rows = Object.keys(METRIC_LABELS)
    .map((metric) => {
      const cls = deltaClass(metric, deltas[metric]);
      return `
        <div>${METRIC_LABELS[metric]}</div>
        <div>${formatMetric(metric, run_a[metric])}</div>
        <div>${formatMetric(metric, run_b[metric])}</div>
        <div class="${cls}">${formatDeltaLabel(metric, deltas[metric])}</div>
      `;
    })
    .join("");

  el("compare-output").innerHTML = `
    <div class="run-title">${run_a.name || "Run A"} vs ${run_b.name || "Run B"}</div>
    <div class="run-subtitle">${run_a.date || ""} &nbsp;&rarr;&nbsp; ${run_b.date || ""}</div>
    <div class="compare-grid">
      <div class="header">Metric</div>
      <div class="header">${run_a.date || "Run A"}</div>
      <div class="header">${run_b.date || "Run B"}</div>
      <div class="header">Change</div>
      ${rows}
    </div>
  `;
  el("compare-panel").hidden = false;
}

el("connect-form").addEventListener("submit", async (evt) => {
  evt.preventDefault();
  el("connect-error").hidden = true;
  try {
    const result = await api("/api/connect", {
      method: "POST",
      body: JSON.stringify({ email: el("email").value, password: el("password").value }),
    });
    if (result.status === "mfa_required") {
      el("mfa-form").hidden = false;
    } else {
      await refreshStatus();
    }
  } catch (err) {
    el("connect-error").textContent = err.message;
    el("connect-error").hidden = false;
  }
});

el("mfa-form").addEventListener("submit", async (evt) => {
  evt.preventDefault();
  el("connect-error").hidden = true;
  try {
    await api("/api/connect/mfa", {
      method: "POST",
      body: JSON.stringify({ code: el("mfa-code").value }),
    });
    el("mfa-form").hidden = true;
    await refreshStatus();
  } catch (err) {
    el("connect-error").textContent = err.message;
    el("connect-error").hidden = false;
  }
});

el("compare-btn").addEventListener("click", async () => {
  const [a, b] = Array.from(state.selected);
  try {
    const data = await api(`/api/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`);
    renderComparison(data);
  } catch (err) {
    alert(err.message);
  }
});

refreshStatus().then((connected) => {
  if (!connected) {
    // Try auto-connect once using whatever credentials the server has in .env.
    api("/api/connect", { method: "POST", body: JSON.stringify({}) })
      .then((result) => {
        if (result.status === "mfa_required") {
          el("mfa-form").hidden = false;
        }
        return refreshStatus();
      })
      .catch(() => {});
  }
});
