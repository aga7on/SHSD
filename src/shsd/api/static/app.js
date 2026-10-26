"use strict";

const API = "/v1/streams";
const WINDOW_LIMIT_MS = 600_000;
const state = {
  streams: [],
  stream: null,
  events: new Map(),
  speechSegments: new Map(),
  captions: [],
  watermarks: null,
  selectedEvent: null,
  selectedLevel: "L2",
  lastSequence: 0,
  socket: null,
  reconnectDelay: 750,
  reconnectTimer: null,
  pollTimer: null,
  showE: false,
  showD: false,
  hasSnapshot: false,
};

const $ = (selector) => document.querySelector(selector);
const dom = {
  connection: $("#connection-label"),
  createForm: $("#create-form"),
  createFeedback: $("#create-feedback"),
  source: $("#source-path"),
  streamList: $("#stream-list"),
  sourceName: $("#active-source"),
  streamStatus: $("#stream-status"),
  statusDot: $("#status-dot"),
  epoch: $("#epoch-label"),
  chart: $("#timeline-chart"),
  chartEmpty: $("#timeline-empty"),
  axis: $("#axis-ticks"),
  rows: $("#track-rows"),
  cursorLayer: $("#cursor-layer"),
  rangeLabel: $("#time-window-label"),
  detailPlaceholder: $("#event-placeholder"),
  details: $("#event-details"),
  revisionBadge: $("#detail-revision-badge"),
  refineForm: $("#refine-form"),
  refineFeedback: $("#refine-feedback"),
  refineSubmit: $("#refine-submit"),
  refineStart: $("#refine-start"),
  refineEnd: $("#refine-end"),
  refineLevel: $("#refine-level"),
  live: $("#live-announcement"),
};

function node(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined && text !== null) el.textContent = String(text);
  return el;
}

function setFeedback(element, message, tone = "") {
  element.textContent = message;
  if (tone) element.dataset.tone = tone;
  else delete element.dataset.tone;
}

function announce(message) {
  dom.live.textContent = "";
  window.setTimeout(() => { dom.live.textContent = message; }, 20);
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const raw = await response.text();
  let data = {};
  if (raw) {
    try { data = JSON.parse(raw); }
    catch { data = { detail: raw }; }
  }
  if (!response.ok) {
    const detail = data.detail || data.message || response.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

function streamLabel(status) {
  return ({ queued: "В очереди", running: "Обрабатывается", completed: "Готово", failed: "Ошибка" })[status] || status || "Неизвестно";
}

function statusTone(status) {
  return status === "running" ? "running" : status === "queued" ? "queued" : status === "failed" ? "failed" : "";
}

function humanTime(ms, compact = false) {
  const safe = Math.max(0, Math.floor(Number(ms) || 0));
  const hours = Math.floor(safe / 3_600_000);
  const minutes = Math.floor((safe % 3_600_000) / 60_000);
  const seconds = Math.floor((safe % 60_000) / 1_000);
  const tenths = Math.floor((safe % 1_000) / 100);
  if (hours > 0) return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  if (compact && safe >= 60_000) return `${minutes}:${String(seconds).padStart(2, "0")}`;
  return `${minutes}:${String(seconds).padStart(2, "0")}.${tenths}`;
}

function relativePath(value) {
  if (!value) return "Локальный файл";
  const pieces = String(value).split(/[\\/]/).filter(Boolean);
  return pieces.at(-1) || value;
}

function selectedHorizon() {
  const duration = Number(state.stream?.source_duration_ms || 0);
  const cursor = Number(selectedWatermarks().C || 0);
  return state.stream?.status === "completed" ? (duration || cursor) : cursor;
}

function selectedWatermarks() {
  const record = state.watermarks || {};
  return record.watermarks && typeof record.watermarks === "object" ? record.watermarks : record;
}

function percentAt(ms, rangeStart, rangeEnd) {
  const span = Math.max(1, rangeEnd - rangeStart);
  return Math.max(0, Math.min(100, ((ms - rangeStart) / span) * 100));
}

function setMetric(name, ms, horizon) {
  const number = Number(ms || 0);
  const label = $(`#metric-${name}`);
  const bar = $(`#metric-bar-${name}`);
  const progress = bar.parentElement;
  label.textContent = state.stream ? humanTime(number) : "-";
  const value = horizon > 0 ? Math.max(0, Math.min(100, (number / horizon) * 100)) : 0;
  bar.style.width = `${value}%`;
  progress.setAttribute("aria-valuenow", value.toFixed(0));
  progress.setAttribute("aria-valuetext", `${humanTime(number)} из ${humanTime(horizon)}`);
}

function renderMetrics() {
  const watermarks = selectedWatermarks();
  const horizon = selectedHorizon();
  const draft = Number(watermarks.D?.[state.selectedLevel] || 0);
  const read = Number(watermarks.R?.[state.selectedLevel] || 0);
  const captured = Number(watermarks.C || 0);
  const embedded = Number(watermarks.E || 0);
  setMetric("c", captured, Math.max(horizon, 1));
  setMetric("e", embedded, Math.max(horizon, 1));
  setMetric("d", draft, Math.max(horizon, 1));
  setMetric("r", read, Math.max(horizon, 1));
  $("#metric-level-d").textContent = state.selectedLevel;
  $("#metric-level-r").textContent = state.selectedLevel;
  const lag = Math.max(0, horizon - read);
  $("#backlog-value").textContent = state.stream ? humanTime(lag) : "-";
  $("#backlog-note").textContent = state.stream
    ? `C продолжает движение; R[${state.selectedLevel}] отстаёт на ${humanTime(lag)}`
    : "R выбранного уровня до горизонта C";
}

function renderStatus() {
  const stream = state.stream;
  if (!stream) {
    dom.sourceName.textContent = "Выберите поток или запустите новый анализ";
    dom.streamStatus.textContent = "Нет активного потока";
    dom.statusDot.dataset.status = "idle";
    dom.epoch.textContent = "";
    dom.refineSubmit.disabled = true;
    document.querySelectorAll("[data-export]").forEach((button) => { button.disabled = true; });
    setFeedback(dom.refineFeedback, "Выберите завершённый поток.");
    return;
  }
  dom.sourceName.textContent = stream.source || stream.stream_id;
  dom.sourceName.title = stream.source || stream.stream_id;
  dom.streamStatus.textContent = streamLabel(stream.status);
  dom.statusDot.dataset.status = statusTone(stream.status);
  dom.epoch.textContent = `epoch ${stream.epoch ?? 0}`;
  dom.refineSubmit.disabled = stream.status !== "completed";
  document.querySelectorAll("[data-export]").forEach((button) => { button.disabled = false; });
  if (stream.status === "completed") setFeedback(dom.refineFeedback, "Файловый проход завершён. Диапазон готов к уточнению.");
  else if (stream.status === "failed") setFeedback(dom.refineFeedback, "Поток завершился с ошибкой.", "error");
  else setFeedback(dom.refineFeedback, "Уточнение станет доступно после завершения прохода.");
  if (stream.status === "failed" && stream.error) {
    setFeedback(dom.createFeedback, stream.error, "error");
  }
}

function renderStreamList() {
  dom.streamList.replaceChildren();
  if (!state.streams.length) {
    dom.streamList.append(node("p", "empty-list", "Потоков пока нет."));
    return;
  }
  for (const stream of state.streams) {
    const button = node("button", "stream-item");
    button.type = "button";
    button.setAttribute("aria-current", String(stream.stream_id === state.stream?.stream_id));
    button.setAttribute("aria-label", `${relativePath(stream.source)}, ${streamLabel(stream.status)}`);
    const title = node("span", "stream-name", relativePath(stream.source));
    title.title = stream.source || stream.stream_id;
    const meta = node("span", "stream-meta", `${stream.stream_id} · ${humanTime(stream.source_duration_ms || 0)}`);
    const badge = node("span", "stream-pill", streamLabel(stream.status));
    badge.dataset.status = stream.status || "unknown";
    button.append(title, meta, badge);
    button.addEventListener("click", () => selectStream(stream.stream_id));
    dom.streamList.append(button);
  }
}

function makeAxis(rangeStart, rangeEnd) {
  dom.axis.replaceChildren();
  const count = rangeEnd - rangeStart;
  for (let i = 0; i <= 4; i += 1) {
    const tick = node("span", "", humanTime(rangeStart + (count * i) / 4, true));
    dom.axis.append(tick);
  }
  const minutes = Math.max(1, Math.round(count / 60_000));
  $("#window-label").textContent = `${minutes} МИН${minutes === 10 ? "" : " · МАКС. 10 МИН"}`;
  dom.rangeLabel.textContent = `${humanTime(rangeStart)} - ${humanTime(rangeEnd)}`;
}

function eventDescription(event) {
  const accepted = (event.claims || []).find((claim) => claim.text_ru) || (event.claims || [])[0];
  return event.caption_ru || accepted?.text_ru || accepted?.label || event.kind || "Событие";
}

function laneForAudio(event) {
  const text = [event.kind, ...(event.claims || []).flatMap((claim) => [claim.label, claim.text_ru])].join(" ").toLowerCase();
  if (/speech|transcript|реч|реплик|голос|говор/.test(text) || event.modality_mask?.speech) return "speech";
  if (/music|музык|мелод|песн|ритм/.test(text)) return "music";
  return "sound";
}

function eventLanes(event) {
  const lanes = new Set();
  if (event.modality_mask?.video) lanes.add("video");
  if (event.modality_mask?.audio) lanes.add(laneForAudio(event));
  if (event.modality_mask?.speech) lanes.add("speech");
  lanes.add(String(event.level || "L1").toLowerCase());
  return [...lanes];
}

const TRACKS = [
  { id: "video", label: "Video", hint: "VIS", color: "var(--color-blue-bright)" },
  { id: "music", label: "Music", hint: "AUD", color: "var(--color-violet-bright)" },
  { id: "sound", label: "Sound", hint: "AUD", color: "var(--color-green-bright)" },
  { id: "speech", label: "Speech", hint: "ASR", color: "var(--color-amber-bright)" },
  { id: "l1", label: "L1 · события", hint: "L1", color: "var(--color-blue-bright)" },
  { id: "l2", label: "L2 · состояние", hint: "L2", color: "var(--color-violet-bright)" },
  { id: "l3", label: "L3 · описание", hint: "L3", color: "var(--color-green-bright)" },
];

function appendCoverage(plot, issue, start, end) {
  const left = percentAt(issue.start_ms, start, end);
  const right = percentAt(issue.end_ms, start, end);
  if (right <= left) return;
  const bar = node("div", "coverage-bar");
  bar.dataset.status = issue.status || "missing";
  bar.style.left = `${left}%`;
  bar.style.width = `${Math.max(0.2, right - left)}%`;
  const status = issue.status || "missing";
  const modality = issue.modality || issue.level || "";
  const range = `${humanTime(issue.start_ms)}-${humanTime(issue.end_ms)}`;
  bar.setAttribute("role", "img");
  bar.setAttribute("aria-label", `${status} ${modality}, ${range}${issue.reason ? `, ${issue.reason}` : ""}`);
  bar.title = `${status} · ${modality} · ${range}${issue.reason ? ` · ${issue.reason}` : ""}`;
  if ((right - left) > 12) bar.append(node("span", "", `${status} · ${issue.reason || modality}`));
  plot.append(bar);
}

function issuesForTrack(trackId, issues) {
  if (trackId === "video") return issues.filter((issue) => issue.modality === "video");
  if (["music", "sound"].includes(trackId)) return issues.filter((issue) => issue.modality === "audio");
  if (trackId === "speech") return issues.filter((issue) => issue.modality === "speech");
  const level = trackId.toUpperCase();
  return issues.filter((issue) => issue.level === level && ["D", "R"].includes(issue.stage));
}

function modalityUnavailable(trackId) {
  const modalities = state.stream?.modalities || {};
  const unavailable = modalities.unavailable || [];
  if (trackId === "speech" && (modalities.speech === "disabled" || unavailable.includes("speech"))) return "unavailable";
  if (trackId === "video" && Array.isArray(modalities.available) && !modalities.available.includes("video")) return "unavailable";
  if (["music", "sound"].includes(trackId) && Array.isArray(modalities.available) && !modalities.available.includes("audio")) return "unavailable";
  return "";
}

function appendEvent(plot, event, start, end) {
  const left = percentAt(event.start_ms, start, end);
  const right = percentAt(event.end_ms, start, end);
  if (right <= left) return;
  const button = node("button", `event-bar level-${String(event.level || "L1").toLowerCase()}`, eventDescription(event));
  button.type = "button";
  button.dataset.state = event.state || "draft";
  button.dataset.selected = String(state.selectedEvent?.event_id === event.event_id);
  button.style.left = `${left}%`;
  button.style.width = `${Math.max(1, right - left)}%`;
  button.title = `${eventDescription(event)} · ${humanTime(event.start_ms)}-${humanTime(event.end_ms)} · ${event.state} · rev ${event.revision}`;
  button.setAttribute("aria-label", `${eventDescription(event)}, ${humanTime(event.start_ms)}-${humanTime(event.end_ms)}, ${event.state}, revision ${event.revision}`);
  button.addEventListener("click", () => showEvent(event));
  plot.append(button);
}

function appendSpeechSegment(plot, segment, start, end) {
  const left = percentAt(segment.start_ms, start, end);
  const right = percentAt(segment.end_ms, start, end);
  if (right <= left) return;
  const transcript = String(segment.text || "").trim();
  const title = transcript || segment.error || segment.status || "ASR segment";
  const bar = node("div", `speech-segment status-${segment.status || "partial"}`);
  bar.style.left = `${left}%`;
  bar.style.width = `${Math.max(0.6, right - left)}%`;
  bar.title = `${humanTime(segment.start_ms)}-${humanTime(segment.end_ms)} · ${segment.status} · ${title}`;
  bar.setAttribute("role", "img");
  bar.setAttribute("aria-label", `Речь ${humanTime(segment.start_ms)}-${humanTime(segment.end_ms)}: ${title}`);
  plot.append(bar);
}

function renderTimeline() {
  const stream = state.stream;
  dom.rows.replaceChildren();
  dom.cursorLayer.replaceChildren();
  const hasStream = Boolean(stream);
  dom.chartEmpty.hidden = hasStream;
  dom.chart.hidden = !hasStream;
  if (!hasStream) return;

  const watermarks = selectedWatermarks();
  const cursor = Number(watermarks.C || 0);
  const horizon = Math.max(0, selectedHorizon());
  const visibleSpan = Math.min(WINDOW_LIMIT_MS, Math.max(horizon > 0 ? 1_000 : 60_000, horizon));
  const rangeEnd = Math.max(visibleSpan, horizon);
  const rangeStart = Math.max(0, rangeEnd - visibleSpan);
  makeAxis(rangeStart, rangeEnd);
  const issues = Array.isArray(watermarks.issues) ? watermarks.issues : [];
  const selectedRead = Number(watermarks.R?.[state.selectedLevel] || 0);
  const selectedDraft = Number(watermarks.D?.[state.selectedLevel] || 0);
  const modalityCursors = watermarks.modality_cursors || {};

  for (const track of TRACKS) {
    const row = node("div", "track-row");
    row.dataset.track = track.id;
    const label = node("div", "track-label");
    label.style.setProperty("--track-color", track.color);
    const mark = node("i", "track-mark");
    mark.setAttribute("aria-hidden", "true");
    const title = node("strong", "", track.label);
    const hint = node("small", "", track.hint);
    label.append(mark, title, hint);
    const plot = node("div", "track-plot");
    plot.setAttribute("role", "group");
    plot.setAttribute("aria-label", `${track.label} observations`);
    plot.style.setProperty("--track-color", track.color);

    const unavailable = modalityUnavailable(track.id);
    if (unavailable) {
      appendCoverage(plot, { start_ms: rangeStart, end_ms: Math.max(rangeStart + 1, Math.min(rangeEnd, horizon || rangeEnd)), status: unavailable, modality: track.id === "speech" ? "speech" : track.id === "video" ? "video" : "audio", reason: track.id === "speech" ? "GigaAM ASR выключен" : "модальность недоступна" }, rangeStart, rangeEnd);
    }
    for (const issue of issuesForTrack(track.id, issues)) appendCoverage(plot, issue, rangeStart, rangeEnd);

    if (track.id === `l${state.selectedLevel.slice(1)}` && horizon > selectedRead) {
      appendCoverage(plot, { stage: "R", level: state.selectedLevel, start_ms: Math.max(rangeStart, selectedRead), end_ms: Math.min(rangeEnd, horizon), status: "pending", reason: "ожидание описания" }, rangeStart, rangeEnd);
    }
    const modality = track.id === "video" ? "video" : ["music", "sound"].includes(track.id) ? "audio" : track.id === "speech" ? "speech" : "";
    if (modality) {
      const modCursors = modalityCursors[modality] || {};
      const embeddedCursor = Number(modCursors.E || watermarks.E || 0);
      const captureCursor = Number(modCursors.C || watermarks.C || 0);
      if (captureCursor < horizon) appendCoverage(plot, { start_ms: Math.max(rangeStart, captureCursor), end_ms: Math.min(rangeEnd, horizon), status: "pending", modality, reason: "ожидание захвата" }, rangeStart, rangeEnd);
      if (state.showE && embeddedCursor < captureCursor) appendCoverage(plot, { start_ms: Math.max(rangeStart, embeddedCursor), end_ms: Math.min(rangeEnd, captureCursor), status: "pending", modality, reason: "ожидание эмбеддинга" }, rangeStart, rangeEnd);
    } else if (track.id.startsWith("l")) {
      const level = track.id.toUpperCase();
      const readCursor = Number(watermarks.R?.[level] || 0);
      const draftCursor = Number(watermarks.D?.[level] || 0);
      if (readCursor < horizon && level !== state.selectedLevel) appendCoverage(plot, { start_ms: Math.max(rangeStart, readCursor), end_ms: Math.min(rangeEnd, horizon), status: "pending", level, reason: `ожидание R[${level}]` }, rangeStart, rangeEnd);
      if (state.showD && draftCursor < horizon) appendCoverage(plot, { start_ms: Math.max(rangeStart, draftCursor), end_ms: Math.min(rangeEnd, horizon), status: "pending", level, reason: `ожидание D[${level}]` }, rangeStart, rangeEnd);
    }
    for (const event of state.events.values()) {
      if (event.end_ms <= rangeStart || event.start_ms >= rangeEnd) continue;
      if (eventLanes(event).includes(track.id)) appendEvent(plot, event, rangeStart, rangeEnd);
    }
    if (track.id === "speech") {
      for (const segment of state.speechSegments.values()) {
        if (segment.end_ms <= rangeStart || segment.start_ms >= rangeEnd) continue;
        appendSpeechSegment(plot, segment, rangeStart, rangeEnd);
      }
    }
    row.append(label, plot);
    dom.rows.append(row);
  }

  const cursorDefs = [
    { key: "C", value: cursor, className: "cursor-c", visible: true, name: "C" },
    { key: "R", value: selectedRead, className: "cursor-r", visible: true, name: `R ${state.selectedLevel}` },
    { key: "E", value: Number(watermarks.E || 0), className: "cursor-e", visible: state.showE, name: "E" },
    { key: "D", value: selectedDraft, className: "cursor-d", visible: state.showD, name: `D ${state.selectedLevel}` },
  ];
  for (const item of cursorDefs) {
    if (!item.visible) continue;
    const line = node("div", `cursor-line ${item.className}`);
    const x = percentAt(item.value, rangeStart, rangeEnd);
    line.style.left = `${x}%`;
    line.dataset.edge = x < 5 ? "left" : x > 95 ? "right" : "middle";
    line.append(node("span", "", `${item.name} · ${humanTime(item.value)}`));
    dom.cursorLayer.append(line);
  }
  dom.rangeLabel.textContent = `${humanTime(rangeStart)} - ${humanTime(rangeEnd)} · ${state.events.size} событий`;
  renderMetrics();
}

function claimSummary(claim) {
  const listItem = node("li", "claim-item");
  const title = node("span", "claim-title");
  const label = node("span", "", claim.label || "Наблюдение");
  const scoreValue = claim.raw_cosine;
  const score = node("span", "claim-score", scoreValue === null || scoreValue === undefined ? "оценка нет" : `cos ${Number(scoreValue).toFixed(3)} · не вероятность`);
  title.append(label, score);
  listItem.append(title);
  if (claim.text_ru) listItem.append(node("span", "claim-subtitle", claim.text_ru));
  listItem.append(node("span", "claim-subtitle", `${claim.decision || "unknown"} · margin ${claim.margin === null || claim.margin === undefined ? "-" : Number(claim.margin).toFixed(3)} · ${claim.sample_count || 1} samples`));
  return listItem;
}

function matchingCaption(event) {
  if (event.caption_ru) return event.caption_ru;
  const claimIds = new Set((event.claims || []).map((claim) => claim.claim_id));
  const match = state.captions.find((caption) => {
    const used = caption.used_claim_ids || caption.claim_ids || [];
    if (used.some((id) => claimIds.has(id))) return true;
    const range = caption.time_range || {};
    const start = Number(caption.start_ms ?? range.start_ms ?? -1);
    const end = Number(caption.end_ms ?? range.end_ms ?? -1);
    return start < event.end_ms && end > event.start_ms;
  });
  return match?.caption_ru || "Для этого события caption ещё не получен.";
}

async function showEvent(event) {
  state.selectedEvent = event;
  renderTimeline();
  dom.detailPlaceholder.hidden = true;
  dom.details.hidden = false;
  dom.details.replaceChildren(node("p", "detail-placeholder", "Загружаю историю revisions…"));
  dom.revisionBadge.textContent = `rev ${event.revision}`;
  let revisions = [event];
  try {
    const detail = await request(`${API}/${encodeURIComponent(state.stream.stream_id)}/events/${encodeURIComponent(event.event_id)}`);
    if (Array.isArray(detail.revisions) && detail.revisions.length) revisions = detail.revisions;
  } catch (error) {
    announce(`Не удалось загрузить историю события: ${error.message}`);
  }
  const latest = [...revisions].sort((a, b) => a.revision - b.revision).at(-1) || event;
  const root = document.createDocumentFragment();
  const summary = node("div", "event-summary");
  const heading = node("div");
  heading.append(node("h3", "", eventDescription(latest)));
  heading.append(node("p", "", `${humanTime(latest.start_ms)}-${humanTime(latest.end_ms)} · ${latest.kind} · ${latest.level} · epoch ${latest.epoch}`));
  const chip = node("span", "state-chip", latest.state || "unknown");
  chip.dataset.state = latest.state || "unknown";
  summary.append(heading, chip);
  root.append(summary);

  const caption = node("div", "caption-block", matchingCaption(latest));
  caption.setAttribute("aria-label", "Caption события");
  root.append(caption);

  root.append(node("p", "detail-label", `Claims · ${(latest.claims || []).length}`));
  const claims = node("ul", "claim-list");
  for (const claim of latest.claims || []) claims.append(claimSummary(claim));
  if (!claims.childElementCount) claims.append(node("li", "claim-item", "Подтверждённых claims нет."));
  root.append(claims);

  const evidence = [...new Set((latest.claims || []).flatMap((claim) => claim.evidence_refs || []))];
  root.append(node("p", "detail-label", `Evidence · ${evidence.length} ссылок`));
  const evidenceList = node("ul", "evidence-list");
  for (const ref of evidence) evidenceList.append(node("li", "evidence-item", ref));
  if (!evidence.length) evidenceList.append(node("li", "evidence-item", "Ссылки на evidence отсутствуют."));
  root.append(evidenceList);

  const revisionsTitle = node("p", "detail-label", `История · ${revisions.length} ${revisions.length === 1 ? "revision" : "revisions"}`);
  root.append(revisionsTitle);
  const revisionList = node("ol", "revision-list");
  for (const revision of [...revisions].sort((a, b) => a.revision - b.revision)) {
    const item = node("li", "revision-item");
    item.append(node("strong", "", `rev ${revision.revision} · ${revision.state}`));
    item.append(node("span", "", `${humanTime(revision.start_ms)}-${humanTime(revision.end_ms)}`));
    if (revision.supersedes_revision !== null && revision.supersedes_revision !== undefined) item.append(node("span", "", `заменяет rev ${revision.supersedes_revision}`));
    revisionList.append(item);
  }
  root.append(revisionList);

  const sourceLine = node("p", "claim-subtitle", `Источник: ${state.stream?.source || "локальный файл"}`);
  root.append(sourceLine);
  const refineButton = node("button", "button button-secondary", "Подставить интервал в refine");
  refineButton.type = "button";
  refineButton.addEventListener("click", () => {
    dom.refineStart.value = (latest.start_ms / 1000).toFixed(1);
    dom.refineEnd.value = (latest.end_ms / 1000).toFixed(1);
    dom.refineForm.scrollIntoView({ behavior: "smooth", block: "center" });
    announce("Интервал события перенесён в форму уточнения.");
  });
  root.append(refineButton);
  dom.details.replaceChildren(root);
}

function applyEvent(event) {
  if (!event?.event_id || !Number.isInteger(Number(event.revision))) return;
  const previous = state.events.get(event.event_id);
  if (!previous || Number(event.revision) > Number(previous.revision)) {
    state.events.set(event.event_id, event);
    const wasSelected = state.selectedEvent?.event_id === event.event_id;
    if (wasSelected) state.selectedEvent = event;
    renderTimeline();
    if (wasSelected) void showEvent(event);
  }
}

function applyWatermarks(record) {
  if (!record || typeof record !== "object") return;
  state.watermarks = record;
  renderTimeline();
}

function applySpeechSegment(segment) {
  if (!segment?.segment_id || !Number.isInteger(Number(segment.revision))) return;
  const previous = state.speechSegments.get(segment.segment_id);
  if (!previous || Number(segment.revision) > Number(previous.revision)) {
    state.speechSegments.set(segment.segment_id, segment);
    renderTimeline();
  }
}

async function loadSnapshot({ includeTimeline = true } = {}) {
  if (!state.stream) return;
  const streamId = state.stream.stream_id;
  const [stream, watermarkResult, timelineResult, speechResult] = await Promise.all([
    request(`${API}/${encodeURIComponent(streamId)}`),
    request(`${API}/${encodeURIComponent(streamId)}/watermarks`),
    includeTimeline ? request(`${API}/${encodeURIComponent(streamId)}/timeline?include_history=false&limit=1000`) : Promise.resolve(null),
    request(`${API}/${encodeURIComponent(streamId)}/speech`),
  ]);
  if (state.stream?.stream_id !== streamId) return;
  state.stream = stream;
  state.streams = state.streams.map((item) => item.stream_id === streamId ? stream : item);
  state.watermarks = watermarkResult.watermarks || null;
  state.speechSegments.clear();
  for (const segment of speechResult.items || []) state.speechSegments.set(segment.segment_id, segment);
  if (timelineResult) {
    state.events.clear();
    for (const event of timelineResult.items || []) state.events.set(event.event_id, event);
    state.hasSnapshot = true;
  }
  renderStatus();
  renderStreamList();
  renderTimeline();
  if (stream.error) setFeedback(dom.createFeedback, stream.error, "error");
}

async function loadStreams({ autoSelect = false } = {}) {
  try {
    const result = await request(API);
    state.streams = result.items || [];
    renderStreamList();
    dom.connection.textContent = "API подключён";
    if (autoSelect && !state.stream && state.streams.length) {
      await selectStream(state.streams[0].stream_id);
    }
    if (!state.streams.length && !state.stream) {
      dom.chartEmpty.hidden = false;
      dom.chart.hidden = true;
    }
  } catch (error) {
    dom.connection.textContent = "API недоступен";
    setFeedback(dom.createFeedback, `Не удалось подключиться к SHSD API: ${error.message}`, "error");
    dom.streamList.replaceChildren(node("p", "empty-list", "Сервер SHSD не отвечает."));
  }
}

function connectSocket(streamId) {
  if (state.socket) {
    state.socket.onclose = null;
    state.socket.close();
    state.socket = null;
  }
  if (state.reconnectTimer) window.clearTimeout(state.reconnectTimer);
  const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
  const socket = new WebSocket(`${scheme}//${window.location.host}${API}/${encodeURIComponent(streamId)}/ws?after_seq=${state.lastSequence}`);
  state.socket = socket;
  socket.onopen = () => {
    if (state.socket !== socket) return;
    state.reconnectDelay = 750;
    dom.connection.textContent = "WebSocket подключён";
  };
  socket.onmessage = async (message) => {
    let packet;
    try { packet = JSON.parse(message.data); }
    catch { return; }
    if (packet.stream_id !== state.stream?.stream_id) return;
    if (Number.isInteger(packet.sequence)) state.lastSequence = Math.max(state.lastSequence, packet.sequence);
    if (packet.type === "stream.started") {
      state.stream = { ...state.stream, status: "running" };
      renderStatus();
      renderStreamList();
    } else if (packet.type === "stream.watermarks.changed") applyWatermarks(packet.data);
    else if (["stream.event.created", "stream.event.revised", "stream.event.committed"].includes(packet.type)) applyEvent(packet.data);
    else if (["stream.speech.segment", "stream.speech.segment.revised"].includes(packet.type)) applySpeechSegment(packet.data);
    else if (packet.type === "stream.caption.ready") {
      state.captions.unshift(packet.data || {});
      state.captions = state.captions.slice(0, 100);
      if (state.selectedEvent) showEvent(state.selectedEvent);
      announce("Получен новый caption.");
    } else if (packet.type === "stream.gap_detected") {
      announce("Журнал WebSocket содержит пропуск. Обновляю данные через REST.");
      try { await loadSnapshot(); }
      catch (error) { announce(`REST backfill не завершился: ${error.message}`); }
    } else if (packet.type === "stream.error") {
      setFeedback(dom.createFeedback, packet.data?.message || packet.data?.code || "Ошибка потока", "error");
      announce("Поток сообщил об ошибке.");
    } else if (packet.type === "stream.completed" || packet.type === "stream.refine.completed") {
      try { await loadSnapshot({ includeTimeline: true }); }
      catch (error) { announce(`Не удалось обновить snapshot: ${error.message}`); }
    }
  };
  socket.onerror = () => { dom.connection.textContent = "Переподключение…"; };
  socket.onclose = () => {
    if (state.socket !== socket || state.stream?.stream_id !== streamId) return;
    dom.connection.textContent = "Связь потеряна · переподключение";
    const delay = state.reconnectDelay;
    state.reconnectDelay = Math.min(15_000, Math.round(delay * 1.8));
    state.reconnectTimer = window.setTimeout(() => connectSocket(streamId), delay);
  };
}

async function selectStream(streamId) {
  const item = state.streams.find((stream) => stream.stream_id === streamId);
  if (!item) return;
  state.stream = item;
  state.events.clear();
  state.speechSegments.clear();
  state.captions = [];
  state.selectedEvent = null;
  state.watermarks = null;
  state.lastSequence = 0;
  dom.detailPlaceholder.hidden = false;
  dom.details.hidden = true;
  dom.detailPlaceholder.textContent = "Выберите событие на дорожке, чтобы увидеть caption, evidence и историю изменений.";
  dom.revisionBadge.textContent = "-";
  renderStatus();
  renderStreamList();
  renderTimeline();
  try {
    await loadSnapshot();
    connectSocket(streamId);
    if (state.pollTimer) window.clearInterval(state.pollTimer);
    state.pollTimer = window.setInterval(async () => {
      if (state.stream?.stream_id !== streamId) return;
      try { await loadSnapshot({ includeTimeline: false }); }
      catch (error) { dom.connection.textContent = `REST polling: ${error.message}`; }
    }, 5_000);
  } catch (error) {
    dom.connection.textContent = "API недоступен";
    setFeedback(dom.createFeedback, error.message, "error");
  }
}

async function downloadExport(format) {
  if (!state.stream) return;
  const url = `${API}/${encodeURIComponent(state.stream.stream_id)}/export?format=${encodeURIComponent(format)}&include_history=true`;
  try {
    const response = await fetch(url);
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || response.statusText);
    }
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const link = node("a");
    link.href = objectUrl;
    link.download = `shsd-${state.stream.stream_id}.${format}`;
    document.body.append(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(objectUrl);
    announce(`${format.toUpperCase()} экспорт подготовлен.`);
  } catch (error) {
    setFeedback(dom.createFeedback, `Экспорт не выполнен: ${error.message}`, "error");
    announce("Не удалось скачать экспорт.");
  }
}

dom.createForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const levels = [...document.querySelectorAll('input[name="levels"]:checked')].map((input) => input.value);
  if (!levels.length) {
    setFeedback(dom.createFeedback, "Выберите хотя бы один уровень обработки.", "error");
    return;
  }
  const source = dom.source.value.trim();
  if (!source) return;
  const submit = dom.createForm.querySelector('button[type="submit"]');
  submit.disabled = true;
  setFeedback(dom.createFeedback, "Создаю локальный поток…");
  try {
    const speechEnabled = Boolean(dom.createForm.querySelector('input[name="speech_enabled"]')?.checked);
    const stream = await request(API, { method: "POST", body: JSON.stringify({ source, levels, threads: 4, window_ms: 5_000, speech_enabled: speechEnabled }) });
    state.streams = [stream, ...state.streams.filter((item) => item.stream_id !== stream.stream_id)];
    dom.source.value = "";
    setFeedback(dom.createFeedback, "Поток создан. Подключаюсь к событиям.", "success");
    await selectStream(stream.stream_id);
    announce(`Поток ${stream.stream_id} запущен.`);
  } catch (error) {
    setFeedback(dom.createFeedback, error.message, "error");
  } finally {
    submit.disabled = false;
  }
});

dom.refineForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.stream || dom.refineSubmit.disabled) return;
  const startMs = Math.round(Number(dom.refineStart.value) * 1000);
  const endMs = Math.round(Number(dom.refineEnd.value) * 1000);
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || startMs < 0 || endMs <= startMs) {
    setFeedback(dom.refineFeedback, "Конец интервала должен быть больше начала.", "error");
    return;
  }
  const duration = Number(state.stream.source_duration_ms || 0);
  if (duration && endMs > duration) {
    setFeedback(dom.refineFeedback, `Интервал выходит за длительность файла (${humanTime(duration)}).`, "error");
    return;
  }
  dom.refineSubmit.disabled = true;
  try {
    const job = await request(`${API}/${encodeURIComponent(state.stream.stream_id)}/refine`, {
      method: "POST",
      body: JSON.stringify({ start_ms: startMs, end_ms: endMs, level: dom.refineLevel.value }),
    });
    setFeedback(dom.refineFeedback, `${job.level} добавлен в очередь · ${humanTime(job.start_ms)}-${humanTime(job.end_ms)}.`, "success");
    announce(`Запрос ${job.level} поставлен в очередь.`);
  } catch (error) {
    setFeedback(dom.refineFeedback, error.message, "error");
  } finally {
    dom.refineSubmit.disabled = state.stream?.status !== "completed";
  }
});

document.querySelectorAll(".level-switcher button").forEach((button) => {
  button.addEventListener("click", () => {
    state.selectedLevel = button.dataset.level;
    document.querySelectorAll(".level-switcher button").forEach((item) => item.setAttribute("aria-pressed", String(item === button)));
    renderMetrics();
    renderTimeline();
  });
});

$("#show-e").addEventListener("change", (event) => { state.showE = event.target.checked; renderTimeline(); });
$("#show-d").addEventListener("change", (event) => { state.showD = event.target.checked; renderTimeline(); });
$("#refresh-streams").addEventListener("click", () => loadStreams());
document.querySelectorAll("[data-export]").forEach((button) => {
  button.addEventListener("click", () => downloadExport(button.dataset.export));
});

const themeToggle = $("#theme-toggle");
const storedTheme = window.localStorage.getItem("shsd-theme");
if (storedTheme === "light" || storedTheme === "dark") document.documentElement.dataset.theme = storedTheme;
themeToggle.setAttribute("aria-pressed", String(document.documentElement.dataset.theme === "dark"));
themeToggle.addEventListener("click", () => {
  const dark = document.documentElement.dataset.theme !== "dark";
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  themeToggle.setAttribute("aria-pressed", String(dark));
  $(".theme-toggle-label").textContent = dark ? "Тёмная тема" : "Светлая тема";
  window.localStorage.setItem("shsd-theme", dark ? "dark" : "light");
});

renderTimeline();
renderMetrics();
loadStreams({ autoSelect: true });
