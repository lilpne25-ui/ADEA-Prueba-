"use strict";

const el = (id) => document.getElementById(id);
const MAX_FILES = 8;
let queue = [];          // {name, file?, sample?, grupo, cara}
let results = [];
let selected = 0;
let health = null;
let token = "";
const decisions = {};    // decisión humana local (no se persiste)

const esc = (x) => String(x == null ? "" : x).replace(/[&<>"']/g, (s) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[s]));
const escapeHtml = esc;

const STATUS = {
  DETECTADO: ["Detectado", "st-det"], VALIDADO_POR_FORMATO: ["Validado por formato", "st-ok"],
  PENDIENTE_CONFIRMACION: ["Pendiente de confirmación", "st-pend"], NO_DETECTADO: ["No detectado", "st-none"],
  INVALIDO: ["Inválido", "st-bad"],
};
const STATE_LABEL = {listo: "LISTO", revision: "REVISIÓN", descartado: "DESCARTADO", error: "ERROR"};
const PERSIST_LABEL = {
  NO_CONFIGURADO: "NO CONFIGURADO", CONFIGURADO_SIN_PROBAR: "CONFIGURADO (sin probar)",
  CONECTADO_Y_VALIDADO: "CONECTADO Y VALIDADO", FALLO_DE_CONEXION: "FALLO DE CONEXIÓN",
};

const api = async (url, opts = {}) => {
  const headers = {...(opts.headers || {}), ...(token ? {"X-Access-Token": token} : {})};
  const resp = await fetch(url, {...opts, headers});
  if (!resp.ok) {
    let error = {};
    try { error = await resp.json(); } catch { /* sin cuerpo JSON */ }
    throw new Error(error.detail || `HTTP ${resp.status}`);
  }
  return resp.json();
};

function showTab(name) {
  document.querySelectorAll(".tab").forEach((b) => { const on = b.dataset.tab === name; b.classList.toggle("active", on); b.setAttribute("aria-selected", on); });
  document.querySelectorAll(".tab-content").forEach((c) => c.classList.toggle("active", c.id === `tab-${name}`));
  window.scrollTo({top: 0});
}
document.querySelectorAll(".tab").forEach((btn) => btn.addEventListener("click", () => showTab(btn.dataset.tab)));

// ---------- carga ----------
const zone = el("dropzone");
const realUploads = () => !health || health.carga_real_habilitada;
zone.addEventListener("click", () => { if (realUploads()) el("file-input").click(); else loadSampleSet(); });
zone.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); zone.click(); } });
zone.addEventListener("dragover", (e) => { e.preventDefault(); if (realUploads()) zone.classList.add("dragover"); });
zone.addEventListener("dragleave", () => zone.classList.remove("dragover"));
zone.addEventListener("drop", (e) => { e.preventDefault(); zone.classList.remove("dragover"); if (realUploads()) addFiles([...e.dataTransfer.files]); });
el("file-input").addEventListener("change", (e) => { addFiles([...e.target.files]); e.target.value = ""; });
el("camera-input").addEventListener("change", (e) => { addFiles([...e.target.files]); e.target.value = ""; });
el("camera-btn").addEventListener("click", () => {
  if (!realUploads()) { stageMessage("La demo pública no admite fotografías reales; usa la muestra ficticia.", "warn"); return; }
  // getUserMedia solo existe en contextos seguros (localhost o HTTPS). En la LAN por HTTP se usa la cámara nativa.
  if (window.isSecureContext && navigator.mediaDevices && navigator.mediaDevices.getUserMedia) openCamera();
  else el("camera-input").click();
});

// ---------- cámara con encuadre ID-1 y retroalimentación en vivo ----------
let camStream = null;
let camTimer = null;
const ID1_RATIO = 85.6 / 53.98;

function guideRect(video) {
  // Marco centrado con proporción de tarjeta ID-1, 80 % del ancho visible.
  const vw = video.videoWidth, vh = video.videoHeight;
  let w = vw * 0.8, h = w / ID1_RATIO;
  if (h > vh * 0.8) { h = vh * 0.8; w = h * ID1_RATIO; }
  return {x: (vw - w) / 2, y: (vh - h) / 2, w, h};
}

function frameQuality(video) {
  // Medidas simples y explicables sobre el área del marco: brillo medio y nitidez (diferencias entre vecinos).
  const r = guideRect(video);
  const c = document.createElement("canvas");
  c.width = 160; c.height = Math.round(160 / ID1_RATIO);
  const ctx = c.getContext("2d", {willReadFrequently: true});
  ctx.drawImage(video, r.x, r.y, r.w, r.h, 0, 0, c.width, c.height);
  const d = ctx.getImageData(0, 0, c.width, c.height).data;
  let sum = 0, edge = 0, n = 0;
  for (let y = 0; y < c.height; y++) for (let x = 0; x < c.width - 1; x++) {
    const i = (y * c.width + x) * 4, g = 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
    const g2 = 0.299 * d[i + 4] + 0.587 * d[i + 5] + 0.114 * d[i + 6];
    sum += g; edge += Math.abs(g - g2); n++;
  }
  return {brillo: sum / n, nitidez: edge / n};
}

async function openCamera() {
  const sheet = el("camera-sheet"), video = el("camera-video");
  try {
    camStream = await navigator.mediaDevices.getUserMedia({video: {facingMode: {ideal: "environment"}, width: {ideal: 1920}, height: {ideal: 1080}}, audio: false});
  } catch (err) {
    stageMessage(`No se pudo abrir la cámara (${err.name}). Se usará el selector de fotos.`, "warn");
    el("camera-input").click();
    return;
  }
  video.srcObject = camStream;
  sheet.showModal();
  camTimer = window.setInterval(() => {
    if (!video.videoWidth) return;
    const q = frameQuality(video), out = el("camera-quality");
    let text = "Encuadre listo para capturar", cls = "ok";
    if (q.brillo < 60) { text = "Poca luz: acércate a una ventana o enciende una lámpara"; cls = "warn"; }
    else if (q.brillo > 225) { text = "Demasiada luz o reflejo: inclina ligeramente la credencial"; cls = "warn"; }
    else if (q.nitidez < 6) { text = "Imagen borrosa: mantén el teléfono quieto y enfoca"; cls = "warn"; }
    out.textContent = text; out.className = `camera-quality ${cls}`;
  }, 400);
}

function closeCamera() {
  window.clearInterval(camTimer); camTimer = null;
  if (camStream) camStream.getTracks().forEach((t) => t.stop());
  camStream = null;
  const sheet = el("camera-sheet");
  if (sheet.open) sheet.close();
}

el("camera-close").addEventListener("click", closeCamera);
el("camera-sheet").addEventListener("cancel", closeCamera);
el("camera-shot").addEventListener("click", () => {
  const video = el("camera-video");
  if (!video.videoWidth) return;
  const r = guideRect(video);
  // Se conserva un margen del 6 % alrededor del marco para que OpenCV pueda detectar los bordes.
  const mx = r.w * 0.06, my = r.h * 0.06;
  const sx = Math.max(0, r.x - mx), sy = Math.max(0, r.y - my);
  const sw = Math.min(video.videoWidth - sx, r.w + 2 * mx), sh = Math.min(video.videoHeight - sy, r.h + 2 * my);
  const c = document.createElement("canvas");
  c.width = Math.round(sw); c.height = Math.round(sh);
  c.getContext("2d").drawImage(video, sx, sy, sw, sh, 0, 0, c.width, c.height);
  c.toBlob((blob) => {
    const file = new File([blob], `captura_${new Date().toISOString().slice(11, 19).replace(/:/g, "")}.jpg`, {type: "image/jpeg"});
    const auto = el("camera-auto").checked;
    closeCamera();
    addFiles([file]);
    if (auto) run();
  }, "image/jpeg", 0.92);
});
el("sample-set").addEventListener("click", loadSampleSet);
el("guide-demo").addEventListener("click", async () => { showTab("lab"); await loadSampleSet(); run(); });
el("run-batch").addEventListener("click", run);

function addFiles(files) {
  const ok = files.filter((x) => /^image\/(jpeg|png|webp|bmp|tiff)$/.test(x.type));
  if (ok.length !== files.length) stageMessage("Solo se admiten imágenes PNG, JPG, WEBP, BMP o TIFF.", "warn");
  if (queue.some((x) => x.sample)) queue = [];
  queue.push(...ok.map((file) => ({name: file.name, file, grupo: "", cara: ""})));
  queue = queue.slice(0, MAX_FILES);
  renderQueue();
}

async function loadSampleSet() {
  try {
    const data = await api("/api/samples");
    queue = data.muestras.map((m, i) => ({name: m.archivo, sample: true, data: m.imagen, grupo: i < 2 ? "1" : "", cara: i === 0 ? "front" : i === 1 ? "back" : ""}));
    renderQueue();
    stageMessage("Lote de muestra cargado: frente y reverso ficticios, un contrato con CURP y una foto ruidosa.", "ok");
    setStage("load", "done");
  } catch (err) { stageMessage(`No se pudo cargar la muestra: ${err.message}`, "err"); }
}

function renderQueue() {
  el("queue").innerHTML = queue.map((x, i) => `
    <div class="queue-item">
      <span class="q-name" title="${esc(x.name)}">${esc(x.name)}</span>
      <span class="q-size">${x.sample ? "MUESTRA" : `${(x.file.size / 1024).toFixed(0)} KB`}</span>
      <select class="q-select" data-g="${i}" aria-label="Expediente de ${esc(x.name)}"><option value="">Sin expediente</option>${[1, 2, 3, 4].map((n) => `<option value="${n}" ${x.grupo === String(n) ? "selected" : ""}>Expediente ${n}</option>`).join("")}</select>
      <select class="q-select" data-c="${i}" aria-label="Cara de ${esc(x.name)}"><option value="">Cara: auto</option><option value="front" ${x.cara === "front" ? "selected" : ""}>Frente</option><option value="back" ${x.cara === "back" ? "selected" : ""}>Reverso</option></select>
      <button aria-label="Quitar ${esc(x.name)}" class="q-remove" data-remove="${i}">×</button>
    </div>`).join("");
  el("queue").querySelectorAll("[data-remove]").forEach((b) => b.addEventListener("click", () => { queue.splice(Number(b.dataset.remove), 1); renderQueue(); }));
  el("queue").querySelectorAll("[data-g]").forEach((s) => s.addEventListener("change", () => { queue[Number(s.dataset.g)].grupo = s.value; }));
  el("queue").querySelectorAll("[data-c]").forEach((s) => s.addEventListener("change", () => { queue[Number(s.dataset.c)].cara = s.value; }));
  el("run-batch").disabled = !queue.length;
  if (queue.length) setStage("load", "done");
}

// Compresión en el navegador: reduce el tamaño de carga; no se guarda nada.
async function encodeImage(file) {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, 1600 / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  return canvas.toDataURL("image/jpeg", 0.86);
}

// ---------- estados del proceso ----------
function setStage(stage, state) {
  const li = document.querySelector(`#stages [data-stage="${stage}"]`);
  if (li) li.className = state;
}
function resetStages() { document.querySelectorAll("#stages li").forEach((li) => { li.className = ""; }); }
function stageMessage(text, kind) { const m = el("stage-message"); m.textContent = text; m.className = `stage-message ${kind || ""}`; }

async function run() {
  if (!queue.length) return;
  const button = el("run-batch");
  button.disabled = true;
  button.textContent = "Procesando con Python…";
  resetStages(); setStage("load", "done"); setStage("process", "active");
  el("session-stats").textContent = "PROCESANDO";
  stageMessage("Procesando: localizando tarjeta, comparando preprocesamientos, leyendo con OCR… (puede tardar unos segundos por imagen)", "");
  try {
    const onlySamples = queue.every((x) => x.sample);
    if (!onlySamples && queue.some((x) => x.sample)) throw new Error("Procesa las muestras por separado de tus archivos.");
    const archivos = [];
    for (const x of queue) {
      const entry = {archivo: x.name, grupo: x.grupo || undefined, cara: x.cara || undefined};
      if (!x.sample) entry.imagen = await encodeImage(x.file);
      archivos.push(entry);
    }
    const body = JSON.stringify({archivos, solo_muestra: onlySamples});
    if (new Blob([body]).size > 4_300_000) throw new Error("El lote excede 4.3 MB. Selecciona menos imágenes.");
    const response = await api("/api/process", {method: "POST", headers: {"Content-Type": "application/json"}, body});
    results = response.resultados;
    selected = 0;
    setStage("process", "done"); setStage("result", "done"); setStage("trace", "done");
    el("session-stats").textContent = `${results.length} ARCHIVO(S) · COMPLETADO`;
    stageMessage(`Listo: ${results.length} archivo(s) procesados. Abriendo resultados…`, "ok");
    renderResults();
    showTab("results");
  } catch (err) {
    setStage("process", "error");
    el("session-stats").textContent = "ERROR";
    stageMessage(`No se pudo procesar el lote: ${err.message}`, "err");
  } finally {
    button.disabled = !queue.length;
    button.innerHTML = "Ejecutar procesamiento <span>→</span>";
  }
}

// ---------- resultados ----------
const badge = (state) => `<span class="status-badge ${esc(state)}">${esc(STATE_LABEL[state] || state)}</span>`;
const stBadge = (s) => { const [label, cls] = STATUS[s] || [s, "st-none"]; return `<span class="fstate ${cls}">${esc(label)}</span>`; };

function fieldHtml(title, f) {
  if (!f) return "";
  const empty = f.valor == null || f.valor === "";
  const extra = [];
  if (f.lectura_original) extra.push(`Lectura OCR original: <code>${esc(f.lectura_original)}</code>`);
  if (f.correcciones_ocr && f.correcciones_ocr.length) extra.push(`Corrección OCR: ${esc(f.correcciones_ocr.join("; "))}`);
  (f.alertas || []).forEach((a) => extra.push(`⚠ ${esc(a)}`));
  if (f.evidencia) extra.push(esc(f.evidencia));
  return `<div class="field ${esc((STATUS[f.estado] || [0, "st-none"])[1])}"><small>${esc(title)}</small>${empty ? '<strong class="empty">Sin valor</strong>' : `<strong>${esc(f.valor)}</strong>`}${stBadge(f.estado)}${extra.length ? `<em class="fnote">${extra.join("<br>")}</em>` : ""}</div>`;
}

const GROUPS = [
  ["IDENTIFICACIÓN · ANVERSO", [["curp", "CURP"], ["clave_elector", "Clave de elector"], ["apellido_paterno", "Apellido paterno"], ["apellido_materno", "Apellido materno"], ["nombres", "Nombre(s)"]]],
  ["DOMICILIO", [["calle", "Calle"], ["numero_exterior", "Núm. exterior"], ["numero_interior", "Núm. interior"], ["colonia", "Colonia"], ["codigo_postal", "Código postal"], ["municipio_domicilio", "Alcaldía / municipio"], ["estado_domicilio", "Estado"]]],
  ["DATOS ELECTORALES", [["estado_electoral", "Estado"], ["seccion", "Sección"], ["municipio_electoral", "Municipio"], ["localidad", "Localidad"], ["anio_registro", "Año de registro"], ["emision", "Emisión"], ["vigencia", "Vigencia"]]],
];

function renderResults() {
  el("results-empty").hidden = results.length > 0;
  el("results-view").hidden = results.length === 0;
  const tc = el("tab-count"); tc.hidden = !results.length; tc.textContent = results.length;
  const count = (s) => results.filter((r) => r.estado === s).length;
  el("total-count").textContent = results.length;
  el("ine-count").textContent = results.filter((r) => r.clasificacion === "ine").length;
  el("review-count").textContent = count("revision");
  el("discard-count").textContent = count("descartado");
  el("result-list").innerHTML = results.map((r, i) => `<button class="result-pill ${i === selected ? "active" : ""}" data-result="${i}" role="tab"><span class="name">${esc(r.archivo)}</span>${badge(r.estado)}</button>`).join("");
  el("result-list").querySelectorAll("[data-result]").forEach((b) => b.addEventListener("click", () => { selected = Number(b.dataset.result); renderResults(); }));
  renderDetail(results[selected]);
}

function banner(r) {
  const map = {
    listo: ["ok", "Credencial detectada y validada por formato", "Los identificadores cumplen formato y son consistentes. Esto NO prueba autenticidad; confirma contra el documento."],
    revision: ["warn", "Requiere revisión humana", "Hay evidencia parcial, campos pendientes o inconsistencias. Revisa los avisos marcados."],
    descartado: ["off", "Descartado: no se encontró evidencia de INE/IFE", "No cumple las señales mínimas. Un CURP aislado no basta para aceptar un documento."],
    error: ["err", "No se pudo procesar", r.mensaje || "Archivo inválido."],
  }[r.estado] || ["off", r.estado, ""];
  return `<div class="banner ${map[0]}"><strong>${esc(map[1])}</strong><span>${esc(map[2])}</span></div>`;
}

function renderDetail(r) {
  const box = el("result-detail");
  if (!r) { box.innerHTML = ""; return; }
  if (r.estado === "error") { box.innerHTML = banner(r); return; }
  const t = r.tecnicas || {};
  const strategies = (t.estrategias_comparadas || []).map((s) => `<tr class="${s.estrategia === t.estrategia_elegida ? "chosen" : ""}"><td>${esc(s.estrategia)}</td><td>${esc(s.confianza_media == null ? "—" : s.confianza_media)}</td><td>${esc(s.palabras)}</td><td>${esc(s.puntuacion)}</td><td>${s.estrategia === t.estrategia_elegida ? "elegida" : ""}</td></tr>`).join("");
  const showFields = r.clasificacion !== "no_ine" && r.campos;
  const groups = showFields ? GROUPS.map(([title, items]) => `<div class="field-section-label">${esc(title)}</div><div class="field-grid">${items.map(([k, label]) => fieldHtml(label, r.campos[k])).join("")}</div>`).join("") : "";
  const mrz = r.mrz || {};
  const mrzBlock = (mrz.lineas || []).length ? `<div class="field-section-label">REVERSO · MRZ Y CÓDIGOS</div><pre class="mrz">${esc((mrz.lineas || []).join("\n"))}</pre>
      <div class="evidence">${mrz.lineas_validas ? "Estructura TD1 de 3 líneas reconocida." : `Estructura MRZ no reconocida: ${esc(mrz.motivo || "")}`} ${(mrz.verificadores || []).map((c) => `${esc(c.campo)}: ${c.coincide ? "✓ dígito coincide" : "✗ dígito no coincide"}`).join(" · ")}${mrz.nota ? `<br>⚠ ${esc(mrz.nota)}` : ""}${mrz.correcciones_ocr ? `<br>Correcciones OCR aplicadas: ${esc(mrz.correcciones_ocr.length)} (hipótesis).` : ""}</div>` : "";
  const codes = (r.codigos || []).length ? `<div class="field-grid">${r.codigos.map((c) => `<div class="field"><small>${esc(c.tipo)}</small><strong>${esc(c.valor)}</strong><span class="fstate st-det">Decodificado</span></div>`).join("")}</div>` : "";
  const checks = (r.consistencia || []).map((c) => `<li class="${c.resultado === true ? "c-ok" : c.resultado === false ? "c-bad" : "c-na"}">${c.resultado === true ? "✓" : c.resultado === false ? "✗" : "—"} ${esc(c.prueba)} <small>${esc(c.detalle)}</small></li>`).join("");
  const sig = r.senales || {};
  const p = r.persistencia || {};
  const link = r.vinculacion ? `<div class="evidence">Asociación (${esc(r.vinculacion.origen)}): <b>${esc(r.vinculacion.estado)}</b>. ${esc(r.vinculacion.mensaje)} ${r.reverso ? `Reverso: ${esc(r.reverso.archivo)}.` : ""} ${r.vinculacion.estado === "tentativa" && r.reverso ? '<button class="btn btn-subtle small" id="confirm-link">Confirmar que ambas caras son del mismo documento</button>' : ""}${r.expediente ? `<br>Expediente: <b>${esc(r.expediente.estado)}</b>${r.expediente.faltante && r.expediente.faltante.length ? ` · falta: ${esc(r.expediente.faltante.join(", "))}` : ""}` : ""}</div>` : "";
  const dec = decisions[r.archivo];
  box.innerHTML = `
    ${banner(r)}
    <div class="detail-heading"><div><strong>${esc(r.archivo)}</strong><p>${esc(r.duracion_ms)} ms · clasificación: ${esc(String(r.clasificacion).toUpperCase())} · SHA-256 ${esc((r.sha256 || "").slice(0, 12))}…${r.muestra_ficticia ? " · MUESTRA FICTICIA" : ""}</p></div>${badge(r.estado)}</div>
    <div class="field-section-label">IMAGEN ORIGINAL VS. PROCESADA</div>
    <div class="visual-compare"><figure><img src="${esc(r.preview_original)}" alt="Imagen original"/><figcaption>ORIGINAL</figcaption></figure><figure><img src="${esc(r.preview_limpieza)}" alt="Imagen procesada"/><figcaption>PROCESADA · ${esc(t.estrategia_elegida)}</figcaption></figure></div>
    <div class="evidence">${t.tarjeta_localizada ? "Tarjeta localizada" : "No se localizó la tarjeta"}${t.warp_perspective ? " · perspectiva corregida" : " · sin corrección de perspectiva"} · orientación: ${esc(t.orientacion)}. ${esc((t.notas_localizacion || []).join(" "))}</div>
    <table class="strategies"><thead><tr><th>Estrategia</th><th>Confianza OCR</th><th>Palabras</th><th>Puntuación</th><th></th></tr></thead><tbody>${strategies}</tbody></table>
    <div class="field-section-label">DECISIÓN DE CLASIFICACIÓN</div>
    <div class="evidence"><b>Evidencias:</b> ${esc((r.evidencias || []).join(" · ") || "ninguna")}<br><b>Señales:</b> ${esc(sig.fuertes ?? 0)} fuertes · ${esc(sig.estructurales ?? 0)} estructurales · ${esc(sig.negativas ?? 0)} negativas. <small>${esc(sig.criterio || "")}</small></div>
    ${groups}
    ${mrzBlock}${codes}
    ${checks ? `<div class="field-section-label">VALIDACIÓN CRUZADA</div><ul class="checks">${checks}</ul>` : ""}
    ${link}
    ${(r.alertas || []).length ? `<div class="field-section-label">ALERTAS</div><ul class="alerts">${r.alertas.map((a) => `<li>${esc(a)}</li>`).join("")}</ul>` : ""}
    <div class="field-section-label">TRAZABILIDAD</div>
    <div class="trace"><div><small>ORACLE</small><b>${esc(PERSIST_LABEL[p.oracle] || p.oracle || "—")}</b></div><div><small>SQL SERVER</small><b>${esc(PERSIST_LABEL[p.sqlserver] || p.sqlserver || "—")}</b></div><div><small>ESTADO</small><b>${esc(p.estado || "—")}</b></div></div>
    <div class="evidence">${esc(p.detalle || "")}</div>
    <div class="review-actions"><span>Decisión humana (solo en esta sesión, no se guarda):</span>
      <button class="btn btn-subtle small" data-decide="aceptada">Aceptar tras revisión</button><button class="btn btn-subtle small" data-decide="rechazada">Rechazar</button>${dec ? `<b class="decided">Registrada: ${esc(dec)}</b>` : ""}</div>`;
  box.querySelectorAll("[data-decide]").forEach((b) => b.addEventListener("click", () => { decisions[r.archivo] = b.dataset.decide; renderDetail(r); }));
  const confirm = el("confirm-link");
  if (confirm) confirm.addEventListener("click", () => confirmLink(r));
}

async function confirmLink(r) {
  try {
    const slim = results.map((x) => { const c = {...x}; delete c.preview_original; delete c.preview_limpieza; return c; });
    const out = await api("/api/link", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({resultados: slim, confirmar: [r.archivo, r.reverso.archivo]})});
    out.resultados.forEach((upd) => { const i = results.findIndex((x) => x.archivo === upd.archivo); if (i >= 0) results[i] = {...results[i], ...upd, preview_original: results[i].preview_original, preview_limpieza: results[i].preview_limpieza}; });
    renderResults();
  } catch (err) { stageMessage(`No se pudo confirmar la asociación: ${err.message}`, "err"); }
}

// ---------- infraestructura ----------
function infraCard(id, data, label) {
  const card = el(id);
  const ok = data && data.ok === true;
  card.classList.toggle("on", ok);
  card.classList.toggle("off", !ok);
  card.querySelector(".infra-state").textContent = ok ? "Conectado" : (data && data.estado === "NO_CONFIGURADO" ? "No configurado" : "Desconectado");
  const rows = [
    ["Estado de conexión", PERSIST_LABEL[data.estado] || data.estado || "—"],
    ["Última verificación (UTC)", data.verificado_utc || "—"],
  ];
  if (label === "oracle") rows.push(["Expedientes registrados", data.expedientes ?? "—"], ["Último registro", data.ultimo_registro || "—"]);
  else rows.push(["Eventos de auditoría", data.eventos_auditoria ?? "—"], ["Último procesamiento", data.ultimo_procesamiento || "—"],
    ["Eventos por tipo", data.por_tipo ? Object.entries(data.por_tipo).map(([k, v]) => `${k}: ${v}`).join(", ") : "—"]);
  if (data.tipo_error) rows.push(["Tipo de error", data.tipo_error]);
  card.querySelector("dl").innerHTML = rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("");
}

async function loadInfra() {
  el("infra-refresh").disabled = true;
  try {
    const data = await api("/api/infra");
    infraCard("infra-oracle", data.oracle || {}, "oracle");
    infraCard("infra-sql", data.sqlserver || {}, "sql");
    const o = data.oracle || {}, s = data.sqlserver || {};
    setHealth("health-oracle", PERSIST_LABEL[o.estado] || o.estado || "—", o.ok ? true : o.estado === "NO_CONFIGURADO" ? null : false);
    setHealth("health-sql", PERSIST_LABEL[s.estado] || s.estado || "—", s.ok ? true : s.estado === "NO_CONFIGURADO" ? null : false);
    const errs = [...((data.sqlserver || {}).errores_recientes || []).map((e) => `${e.utc} · auditoría · ${e.tipo} · ${e.codigo} (${e.persistencia})`),
      ...(data.errores_recientes_proceso || []).map((e) => `${e.utc} · ${e.componente} · ${e.codigo}`)];
    el("infra-errors").innerHTML = errs.length ? errs.map((x) => `<li>${esc(x)}</li>`).join("") : '<li class="muted">Sin errores registrados.</li>';
  } catch (err) {
    el("infra-errors").innerHTML = `<li>${esc(`No se pudo consultar: ${err.message}`)}</li>`;
  } finally { el("infra-refresh").disabled = false; }
}
el("infra-refresh").addEventListener("click", loadInfra);
document.querySelector('[data-tab="infra"]').addEventListener("click", loadInfra);

// ---------- estado del sistema ----------
function setHealth(id, text, ok) { const n = el(id); n.textContent = text; n.className = ok === true ? "on" : ok === false ? "off" : ""; }
async function boot() {
  try {
    health = await api("/api/health");
    el("server-status").textContent = "Motor Python operativo";
    el("mode-badge").textContent = health.modo === "demo" ? "MODO DEMOSTRACIÓN · SIN ESCRITURA" : "MODO CORPORATIVO";
    setHealth("health-api", "Operativo", true);
    setHealth("health-ocr", health.motores.ocr ? `${health.motores.ocr === "tesseract" ? "Tesseract" : "RapidOCR (ONNX)"} · ${health.motores.idioma_ocr}` : "Sin motor OCR: el procesamiento no funcionará", !!health.motores.ocr);
    setHealth("health-cv", health.motores.opencv ? "Disponible" : "No instalado (modo básico)", !!health.motores.opencv);
    setHealth("health-zxing", health.motores.zxing_qr_pdf417 ? "Disponible" : "No instalado", !!health.motores.zxing_qr_pdf417);
    const pe = health.persistencia;
    setHealth("health-oracle", PERSIST_LABEL[pe.oracle] || pe.oracle, pe.oracle === "CONECTADO_Y_VALIDADO" ? true : pe.oracle === "NO_CONFIGURADO" ? null : false);
    setHealth("health-sql", PERSIST_LABEL[pe.sqlserver] || pe.sqlserver, pe.sqlserver === "CONECTADO_Y_VALIDADO" ? true : pe.sqlserver === "NO_CONFIGURADO" ? null : false);
    if (health.modo === "corporate") {
      el("test-db").hidden = false;
      el("test-db").addEventListener("click", testDb);
      // INICIAR_WINDOWS.bat abre la app con #acceso=<token> (el fragmento nunca viaja al servidor).
      const m = window.location.hash.match(/acceso=([\w-]+)/);
      if (m) { try { window.sessionStorage.setItem("adea-token", m[1]); } catch { /* ignorar */ } window.history.replaceState(null, "", window.location.pathname); }
      try { token = window.sessionStorage.getItem("adea-token") || (m ? m[1] : ""); } catch { token = m ? m[1] : ""; }
      if (!token) { token = window.prompt("Token de acceso (está en .env.local como APP_ACCESS_TOKEN; INICIAR_WINDOWS.bat lo pasa solo):") || ""; try { window.sessionStorage.setItem("adea-token", token); } catch { /* ignorar */ } }
      loadInfra();  // verificación real de conexiones al abrir la app
    }
    el("pair-btn").hidden = health.entorno !== "local";
    if (!health.carga_real_habilitada) {
      el("privacy-message").textContent = "Demo pública: solo se aceptan documentos ficticios. Para probar una INE real, ejecuta la aplicación localmente en una red segura.";
      zone.setAttribute("aria-disabled", "true");
      zone.querySelector("h3").textContent = "Protección de datos activada";
      zone.querySelector("p").textContent = "La demo pública no permite subir identificaciones reales.";
      el("upload-label").textContent = "Usar lote ficticio";
      el("camera-btn").disabled = true;
    } else if (health.entorno === "local") {
      el("privacy-message").textContent = "El OCR se ejecuta en tu equipo. En modo demo no se guardan imágenes ni campos. Si usas una INE real, hazlo en una red confiable y cierra el servidor al terminar.";
    }
    if (!health.motores.tesseract) stageMessage("Tesseract no está instalado: el procesamiento no estará disponible hasta instalarlo (ver Guía).", "err");
  } catch {
    el("server-status").textContent = "Motor Python no disponible";
    el("live-dot").classList.add("off");
    setHealth("health-api", "Sin conexión", false);
  }
}
async function testDb() {
  el("db-message").textContent = "Probando conexiones reales…";
  try {
    const out = await api("/api/persistence/test", {method: "POST"});
    setHealth("health-oracle", PERSIST_LABEL[out.oracle.estado] || out.oracle.estado, out.oracle.ok);
    setHealth("health-sql", PERSIST_LABEL[out.sqlserver.estado] || out.sqlserver.estado, out.sqlserver.ok);
    el("db-message").textContent = "Prueba terminada. El estado refleja una conexión real intentada ahora.";
  } catch (err) { el("db-message").textContent = `No se pudo probar: ${err.message}`; }
}
boot();

// ---------- PWA ----------
if ("serviceWorker" in navigator && window.isSecureContext) {
  navigator.serviceWorker.register("/sw.js").catch(() => { /* la app funciona igual sin modo offline */ });
}

// ---------- emparejamiento del celular (solo instalación local) ----------
async function openPairing() {
  try {
    const data = await api("/api/pairing");
    el("pair-qr").src = data.qr || "";
    el("pair-url").textContent = data.url_visible;
    el("pair-note").textContent = data.https
      ? "El celular mostrará un aviso de certificado propio de tu red: acéptalo solo en tu Wi-Fi."
      : (data.aviso || "");
    el("pair-sheet").showModal();
  } catch (err) { stageMessage(`No se pudo generar el emparejamiento: ${err.message}`, "err"); }
}
el("pair-btn").addEventListener("click", openPairing);
el("pair-close").addEventListener("click", () => el("pair-sheet").close());
