// Dashboard de CandiTrack: pide los datos a la API (/api/v1/...) y los pinta en la página.
//
// Seguridad: empresas y puestos vienen de correos, así que nunca se insertan como HTML
// (innerHTML), siempre como texto (textContent).

const API = "/api/v1";
const PAGE_SIZE = 25;
const STATUS_LABELS = {
  submitted: "Enviada",
  viewed: "Vista",
  rejected: "Rechazada",
  closed: "Cerrada",
};

const $ = (id) => document.getElementById(id);

// Estado de la tabla: la página actual y un contador para descartar respuestas antiguas.
let offset = 0;
let latestRequest = 0;
let platformLabels = {};

/** GET a la API; lanza un Error con un mensaje legible si la respuesta no es 2xx. */
async function getJSON(path, params = {}) {
  const url = new URL(API + path, window.location.origin);
  for (const [key, value] of Object.entries(params)) {
    if (value === "" || value === null || value === undefined) continue;
    for (const item of [].concat(value)) url.searchParams.append(key, item);
  }
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`La API respondió ${response.status} en ${path}`);
  }
  return response.json();
}

function setText(id, text) {
  $(id).textContent = text;
}

function percent(part, whole) {
  return whole ? `${Math.round((part / whole) * 100)} %` : "–";
}

function formatDate(iso) {
  return new Date(iso).toLocaleDateString("es-ES", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function showError(message) {
  const box = $("error");
  box.textContent = message;
  box.hidden = !message;
}

/** Ejecuta `fn` solo cuando han pasado `ms` sin nuevas llamadas (p. ej. al teclear). */
function debounce(fn, ms) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

// --- Tarjetas de cifras y gráfico (comparten los datos de /stats) ---

async function loadOverview(period) {
  for (const id of ["kpi-sent", "kpi-responded", "kpi-no-response", "kpi-days"]) {
    setText(id, "…");
  }
  const [summary, stats] = await Promise.all([
    getJSON("/summary", { since: period }),
    getJSON("/stats", { since: period }),
  ]);
  renderKpis(summary, stats);
  renderChart(stats);
}

function renderKpis(summary, stats) {
  const total = stats.total;
  setText("kpi-sent", total.sent);
  setText("kpi-sent-note", `${summary.total.alive} siguen vivas`);
  setText("kpi-responded", percent(total.responded, total.sent));
  setText("kpi-no-response", total.no_response);
  setText("kpi-no-response-note", `sin novedades en ${stats.stale_days} días o más`);
  setText(
    "kpi-days",
    total.median_days_to_response === null ? "–" : Math.round(total.median_days_to_response),
  );
}

let chart = null;
let lastStats = null; // para volver a pintar el gráfico si cambia el tema claro/oscuro

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/** Plataformas que no avisan por correo de vistas o rechazos: sus cifras salen bajas. */
function caveat(row) {
  if (!row.notifies_views && !row.notifies_rejections) return "no avisa de vistas ni rechazos";
  if (!row.notifies_views) return "no avisa de vistas";
  if (!row.notifies_rejections) return "no avisa de rechazos";
  return null;
}

function renderChart(stats) {
  lastStats = stats;
  // Texto y cuadrícula del gráfico con los colores del tema actual.
  Chart.defaults.color = cssVar("--muted");
  Chart.defaults.borderColor = cssVar("--border");
  const rows = stats.platforms;
  const labels = rows.map((row) => (caveat(row) ? `${row.label} ⚠` : row.label));
  const series = [
    ["Enviadas", "sent", "--chart-sent"],
    ["Con respuesta", "responded", "--chart-responded"],
    ["Rechazadas", "rejected", "--chart-rejected"],
    ["Sin respuesta", "no_response", "--chart-no-response"],
  ];
  const data = {
    labels,
    datasets: series.map(([label, key, color]) => ({
      label,
      data: rows.map((row) => row[key]),
      backgroundColor: cssVar(color),
      borderRadius: 4,
    })),
  };

  if (chart) {
    chart.data = data; // ya existe: solo cambian los datos (p. ej. al cambiar el periodo)
    chart.update();
  } else {
    chart = new Chart($("platform-chart"), {
      type: "bar",
      data,
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
        plugins: { legend: { position: "bottom" } },
      },
    });
  }

  const notes = rows
    .filter((row) => caveat(row))
    .map((row) => `${row.label} ${caveat(row)}`);
  const note = $("chart-note");
  note.textContent = notes.length
    ? `⚠ ${notes.join("; ")}: sus cifras de respuesta salen más bajas de lo real.`
    : "";
  note.hidden = notes.length === 0;
}

// --- Tabla de candidaturas ---

async function loadPlatforms() {
  const platforms = await getJSON("/platforms");
  const select = $("filter-platform");
  for (const platform of platforms) {
    platformLabels[platform.name] = platform.label;
    select.append(new Option(platform.label, platform.name));
  }
}

function cell(text, className) {
  const td = document.createElement("td");
  td.textContent = text;
  if (className) td.className = className;
  return td;
}

function renderRow(application) {
  const row = document.createElement("tr");
  row.dataset.id = application.id; // para abrir el detalle
  row.tabIndex = 0; // se puede llegar con Tab y abrir con Enter

  const status = document.createElement("td");
  status.append(badge(application.status));

  row.append(
    cell(formatDate(application.updated_at)),
    cell(platformLabels[application.platform] ?? application.platform),
    status,
    cell(application.company),
    cell(application.position ?? "–", "position"),
  );
  return row;
}

async function loadApplications(period) {
  const request = ++latestRequest;
  const wrap = $("table-wrap");
  wrap.setAttribute("aria-busy", "true"); // atenúa la tabla mientras llegan los datos
  try {
    await renderApplications(period, request);
  } finally {
    if (request === latestRequest) wrap.setAttribute("aria-busy", "false");
  }
}

async function renderApplications(period, request) {
  const page = await getJSON("/applications", {
    since: period,
    platform: $("filter-platform").value,
    status: $("filter-status").value,
    company: $("filter-company").value.trim(),
    limit: PAGE_SIZE,
    offset,
  });
  if (request !== latestRequest) return; // llegó tarde: ya se pidió otra página o filtro

  $("applications").replaceChildren(...page.items.map(renderRow));
  $("applications-empty").hidden = page.total > 0;

  const first = page.total ? offset + 1 : 0;
  const last = offset + page.items.length;
  setText("page-info", `${first}–${last} de ${page.total}`);
  $("prev").disabled = offset === 0;
  $("next").disabled = last >= page.total;
}

// --- Detalle de una candidatura ---

function formatDateTime(iso) {
  return new Date(iso).toLocaleString("es-ES", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function badge(status) {
  const span = document.createElement("span");
  span.className = `badge badge-${status}`;
  span.textContent = STATUS_LABELS[status] ?? status;
  return span;
}

function renderEvent(event, applicationPosition) {
  const item = document.createElement("li");
  const when = document.createElement("time");
  when.dateTime = event.date;
  when.textContent = formatDateTime(event.date);
  item.append(when, badge(event.type));
  // Si el correo nombra el puesto de otra forma, se muestra (ayuda a detectar errores).
  if (event.position && event.position !== applicationPosition) {
    const position = document.createElement("div");
    position.className = "event-position";
    position.textContent = `Puesto en este correo: ${event.position}`;
    item.append(position);
  }
  return item;
}

async function openDetail(id) {
  const dialog = $("detail");
  setText("detail-company", "Cargando…");
  setText("detail-position", "");
  $("detail-meta").replaceChildren();
  $("detail-events").replaceChildren();
  if (!dialog.open) dialog.showModal();

  let application;
  try {
    application = await getJSON(`/applications/${encodeURIComponent(id)}`);
  } catch (error) {
    // El aviso de error general queda tapado por la ventana: se muestra dentro de ella.
    setText("detail-company", "No se ha podido cargar la candidatura");
    setText("detail-position", error.message);
    return;
  }
  setText("detail-company", application.company);
  setText("detail-position", application.position ?? "Puesto desconocido");
  const platform = document.createElement("span");
  platform.textContent = platformLabels[application.platform] ?? application.platform;
  $("detail-meta").append(platform, "·", badge(application.status));
  $("detail-events").replaceChildren(
    ...application.events.map((event) => renderEvent(event, application.position)),
  );
}

function rowId(event) {
  return event.target.closest("tr[data-id]")?.dataset.id;
}

// --- Orquestación ---

const period = () => $("period").value;

async function run(task) {
  try {
    showError("");
    await task();
  } catch (error) {
    showError(`No se han podido cargar los datos: ${error.message}`);
  }
}

function refreshTable() {
  return run(() => loadApplications(period()));
}

function applyFilters() {
  offset = 0;
  return refreshTable();
}

function refreshAll() {
  offset = 0;
  return run(() => Promise.all([loadOverview(period()), loadApplications(period())]));
}

$("period").addEventListener("change", refreshAll);
$("filter-platform").addEventListener("change", applyFilters);
$("filter-status").addEventListener("change", applyFilters);
$("filter-company").addEventListener("input", debounce(applyFilters, 300));
$("filters").addEventListener("submit", (event) => event.preventDefault());
// Un solo "escuchador" para toda la tabla (delegación de eventos): sirve aunque las filas
// se vuelvan a pintar al cambiar de página o de filtro.
$("applications").addEventListener("click", (event) => {
  const id = rowId(event);
  if (id) run(() => openDetail(id));
});
$("applications").addEventListener("keydown", (event) => {
  const id = rowId(event);
  if (id && (event.key === "Enter" || event.key === " ")) {
    event.preventDefault();
    run(() => openDetail(id));
  }
});
$("detail-close").addEventListener("click", () => $("detail").close());
// Si el sistema cambia entre claro y oscuro con la página abierta, se repinta el gráfico.
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  if (!lastStats) return;
  chart?.destroy();
  chart = null;
  renderChart(lastStats);
});
$("prev").addEventListener("click", () => {
  offset = Math.max(0, offset - PAGE_SIZE);
  refreshTable();
});
$("next").addEventListener("click", () => {
  offset += PAGE_SIZE;
  refreshTable();
});

run(loadPlatforms).then(refreshAll);
