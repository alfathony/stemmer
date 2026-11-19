import { createJob, stemUrl, waitForJob, type Job, type Mode } from "./api";
import { Mixer, type Track } from "./mixer";
import { computePeaks, drawWaveform } from "./waveform";
import { makeZip } from "./zip";

// Stem colours, matching the logo. Lane backgrounds are a tint of the same colour.
const STEM_COLORS: Record<string, string> = {
  vocals: "#8b7dff",
  drums: "#ff5c84",
  bass: "#f7e35a",
  guitar: "#ff9f4a",
  piano: "#4cc9f0",
  other: "#2de39a",
};
const STEM_ORDER = ["vocals", "drums", "bass", "guitar", "piano", "other"];
const stemColor = (name: string) => STEM_COLORS[name] ?? "#a0a3b5";

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const sections = { upload: $("upload"), progress: $("progress"), mixer: $("mixer") };

let mixer: Mixer | null = null;
let lanes: { track: Track; strip: HTMLElement; lane: HTMLElement; canvas: HTMLCanvasElement; peaks: Float32Array }[] = [];
let songName = "";

function show(name: keyof typeof sections) {
  for (const [k, el] of Object.entries(sections)) el.hidden = k !== name;
  const inMixer = name === "mixer";
  $("song-meta").hidden = !inMixer;
  $("top-actions").hidden = !inMixer;
  $("transport").hidden = !inMixer;
}

// ---------- upload ----------

const fileInput = $<HTMLInputElement>("file");
const drop = $("drop");

$("browse").onclick = () => fileInput.click();
fileInput.onchange = () => fileInput.files?.[0] && start(fileInput.files[0]);
// The whole window accepts drops on the home screen, not just the box.
document.addEventListener("dragover", (e) => {
  if (sections.upload.hidden) return;
  e.preventDefault();
  drop.classList.add("over");
});
document.addEventListener("dragleave", (e) => {
  if (!e.relatedTarget) drop.classList.remove("over");
});
document.addEventListener("drop", (e) => {
  if (sections.upload.hidden) return;
  e.preventDefault();
  drop.classList.remove("over");
  const file = e.dataTransfer?.files[0];
  if (file) start(file);
});

// ---------- progress ----------

const STAGES: { label: string; statuses: (Job["status"] | "upload" | "load")[] }[] = [
  { label: "Uploading to the local engine", statuses: ["upload"] },
  { label: "Reading audio", statuses: ["queued", "extracting"] },
  { label: "Separating stems with AI", statuses: ["processing"] },
  { label: "Encoding stems", statuses: ["encoding"] },
  { label: "Detecting tempo and time signature", statuses: ["analyzing"] },
  { label: "Loading the mixer", statuses: ["done", "load"] },
];

function setProgress(status: Job["status"] | "upload" | "load", label: string, fraction: number) {
  const pct = Math.round(fraction * 100);
  $("progress-label").textContent = label;
  $("progress-fill").style.width = `${pct}%`;
  $("progress-pct").textContent = `${pct}%`;
  const current = STAGES.findIndex((s) => s.statuses.includes(status));
  $("stages").innerHTML = "";
  STAGES.forEach((s, i) => {
    const li = document.createElement("li");
    li.textContent = s.label;
    if (i < current) li.className = "done";
    else if (i === current) li.className = "active";
    $("stages").appendChild(li);
  });
}

const STATUS_LABEL: Record<Job["status"], string> = {
  queued: "Waiting in queue",
  extracting: "Reading audio",
  processing: "Separating with AI",
  encoding: "Encoding stems",
  analyzing: "Detecting tempo",
  done: "Loading stems",
  error: "Failed",
};

async function start(file: File) {
  const mode = document.querySelector<HTMLInputElement>('input[name="mode"]:checked')!.value as Mode;
  songName = file.name;
  $("progress-name").textContent = file.name;
  $("progress-error").hidden = true;
  $("retry").hidden = true;
  show("progress");

  try {
    // Overall bar: upload 0–10%, separation 10–90%, downloading stems 90–100%.
    setProgress("upload", "Uploading file", 0);
    const job = await createJob(file, mode, (f) => setProgress("upload", `Uploading file ${Math.round(f * 100)}%`, f * 0.1));
    const done = await waitForJob(job.id, (j) => {
      const pct = j.status === "processing" ? ` ${Math.round(j.progress * 100)}%` : "";
      setProgress(j.status, STATUS_LABEL[j.status] + pct, 0.1 + j.progress * 0.8);
    });
    await loadStems(done, (f) => setProgress("load", "Loading stems", 0.9 + f * 0.1));
    showAnalysis(done.analysis);
    show("mixer");
    renderLanes();
  } catch (err) {
    $("progress-error").textContent = (err as Error).message;
    $("progress-error").hidden = false;
    $("retry").hidden = false;
  } finally {
    fileInput.value = "";
  }
}

$("retry").onclick = () => show("upload");

function showAnalysis(a: Job["analysis"]) {
  const box = $("analysis");
  box.hidden = !a?.bpm;
  if (!a?.bpm) return;
  $("bpm").textContent = String(Math.round(a.bpm));
  $("meter").textContent = a.time_signature ?? "–";
  box.title = `${a.bpm.toFixed(1)} BPM. Both values are estimated from the drums.`;
}

// ---------- mixer ----------

async function loadStems(job: Job, onProgress: (f: number) => void) {
  await mixer?.close();
  mixer = new Mixer();
  mixer.onEnded = updatePlayButton;
  const names = [...job.stems].sort((a, b) => STEM_ORDER.indexOf(a) - STEM_ORDER.indexOf(b));
  let loaded = 0;
  const buffers = await Promise.all(
    names.map(async (name) => {
      const res = await fetch(stemUrl(job.id, name));
      if (!res.ok) throw new Error(`Couldn't download ${name} (${res.status})`);
      const buffer = await mixer!.ctx.decodeAudioData(await res.arrayBuffer());
      onProgress(++loaded / names.length);
      return buffer;
    }),
  );
  names.forEach((name, i) => mixer!.addTrack(name, buffers[i]));
}

const ICON_DOWNLOAD =
  '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M10 3v9m0 0-3.5-3.5M10 12l3.5-3.5M4 14v2h12v-2"/></svg>';

function tint(hex: string, alpha: number) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${n >> 16}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

function renderLanes() {
  const strips = $("strips");
  const lanesEl = $("lanes");
  strips.querySelectorAll(".strip").forEach((el) => el.remove());
  lanesEl.innerHTML = "";
  lanes = [];
  $("song-name").textContent = songName;
  $("duration").textContent = fmt(mixer!.duration);
  $("total").textContent = fmt(mixer!.duration);

  fitLanes();
  for (const track of mixer!.tracks) {
    const color = stemColor(track.name);
    const strip = document.createElement("div");
    strip.className = "strip";
    strip.style.setProperty("--c", color);
    strip.innerHTML = `
      <span class="strip-name"></span>
      <span class="strip-btns">
        <button class="mute" aria-pressed="false" title="Mute">M</button>
        <button class="solo" aria-pressed="false" title="Solo">S</button>
        <button class="download" title="Download this stem as WAV">${ICON_DOWNLOAD}</button>
      </span>
      <label class="vol"><input type="range" min="0" max="1.5" step="0.01" value="1" /><output>100%</output></label>`;
    strip.querySelector(".strip-name")!.textContent = track.name;

    const slider = strip.querySelector<HTMLInputElement>("input")!;
    const out = strip.querySelector("output")!;
    slider.setAttribute("aria-label", `${track.name} volume`);
    slider.oninput = () => {
      track.volume = Number(slider.value);
      out.textContent = `${Math.round(track.volume * 100)}%`;
      refreshGains();
    };
    slider.ondblclick = () => {
      slider.value = "1";
      slider.dispatchEvent(new Event("input"));
    };
    for (const cls of ["mute", "solo"] as const) {
      const btn = strip.querySelector<HTMLButtonElement>(`.${cls}`)!;
      btn.setAttribute("aria-label", `${cls === "mute" ? "Mute" : "Solo"} ${track.name}`);
      btn.onclick = () => {
        if (cls === "mute") track.muted = !track.muted;
        else track.solo = !track.solo;
        btn.setAttribute("aria-pressed", String(cls === "mute" ? track.muted : track.solo));
        refreshGains();
      };
    }
    const dl = strip.querySelector<HTMLButtonElement>(".download")!;
    dl.setAttribute("aria-label", `Download ${track.name} as WAV`);
    dl.onclick = () =>
      busy(dl, "…", async () => download(await mixer!.exportTrack(track), `${baseName()} - ${track.name}.wav`));
    strips.appendChild(strip);

    const lane = document.createElement("div");
    lane.className = "lane";
    lane.style.background = `linear-gradient(180deg, ${tint(color, 0.1)}, ${tint(color, 0.05)})`;
    lane.innerHTML = "<canvas></canvas>";
    lanesEl.appendChild(lane);
    const canvas = lane.querySelector("canvas")!;
    const peaks = computePeaks(track.buffer, 1600);
    drawWaveform(canvas, peaks, color);
    lanes.push({ track, strip, lane, canvas, peaks });
  }
  drawRuler();
  refreshGains();
  updatePlayButton();
}

// Click or drag anywhere on the timeline to seek.
const timeline = $("timeline");
let dragging = false;
function seekToPointer(e: PointerEvent) {
  if (!mixer) return;
  const rect = timeline.getBoundingClientRect();
  const f = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
  mixer.seek(f * mixer.duration);
  tick();
}
timeline.addEventListener("pointerdown", (e) => {
  dragging = true;
  timeline.setPointerCapture(e.pointerId);
  seekToPointer(e);
});
timeline.addEventListener("pointermove", (e) => dragging && seekToPointer(e));
timeline.addEventListener("pointerup", () => (dragging = false));

/** Stretch lanes to fill the window (72–140 px each), so few stems don't leave a gap. */
function fitLanes() {
  if (!mixer || sections.mixer.hidden) return;
  const pane = sections.mixer;
  const style = getComputedStyle(pane);
  const ruler = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--ruler-h"));
  const free = pane.clientHeight - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom) - ruler - 2;
  const h = Math.max(72, Math.min(140, Math.floor(free / mixer.tracks.length)));
  document.querySelector<HTMLElement>(".tracks")!.style.setProperty("--lane-h", `${h}px`);
}

function drawRuler() {
  const ruler = $("ruler");
  ruler.innerHTML = "";
  if (!mixer) return;
  const width = ruler.clientWidth;
  const dur = mixer.duration;
  // Pick a tick spacing that keeps labels at least ~70 px apart.
  const step = [1, 2, 5, 10, 15, 30, 60, 120].find((s) => (s / dur) * width >= 70) ?? 300;
  // Stop before the last ~40 px so the final label isn't cut off at the edge.
  for (let t = 0; (t / dur) * width < width - 40; t += step) {
    const span = document.createElement("span");
    span.style.left = `${(t / dur) * 100}%`;
    span.textContent = fmt(t);
    ruler.appendChild(span);
  }
}

function refreshGains() {
  mixer!.updateGains();
  for (const { track, strip, lane } of lanes) {
    const silent = mixer!.effectiveGain(track) === 0;
    strip.classList.toggle("silent", silent);
    lane.classList.toggle("silent", silent);
  }
}

const fmt = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
const fmtPrecise = (s: number) => `${fmt(s)}.${Math.floor((s % 1) * 10)}`;

const scrub = $<HTMLInputElement>("scrub");
let scrubbing = false;
scrub.addEventListener("pointerdown", () => (scrubbing = true));
scrub.addEventListener("pointerup", () => (scrubbing = false));
scrub.addEventListener("input", () => {
  if (!mixer) return;
  mixer.seek((Number(scrub.value) / 1000) * mixer.duration);
  tick();
});

function tick() {
  if (!mixer) return;
  const t = mixer.currentTime;
  const f = mixer.duration ? t / mixer.duration : 0;
  $("time").textContent = fmtPrecise(t);
  $("playhead").style.left = `${f * 100}%`;
  $("unplayed").style.left = `${f * 100}%`;
  if (!scrubbing) scrub.value = String(Math.round(f * 1000));
}

(function loop() {
  if ((mixer as Mixer | null)?.playing) tick();
  requestAnimationFrame(loop);
})();

function updatePlayButton() {
  const btn = $("play");
  const playing = mixer?.playing ?? false;
  btn.classList.toggle("playing", playing);
  btn.setAttribute("aria-label", playing ? "Pause" : "Play");
  tick();
}

async function togglePlay() {
  if (!mixer) return;
  if (mixer.playing) mixer.pause();
  else await mixer.play();
  updatePlayButton();
}

$("play").onclick = togglePlay;
$("rewind").onclick = () => {
  mixer?.seek(0);
  tick();
};
document.addEventListener("keydown", (e) => {
  if (sections.mixer.hidden || !mixer) return;
  const on = (sel: string) => e.target instanceof Element && e.target.matches(sel);
  if (on("input:not([type=range]), textarea")) return;
  if (e.code === "Space") {
    if (on("button")) return;
    e.preventDefault();
    void togglePlay();
  } else if (e.code === "ArrowLeft" || e.code === "ArrowRight") {
    if (on("input[type=range]")) return;
    e.preventDefault();
    mixer.seek(mixer.currentTime + (e.code === "ArrowLeft" ? -5 : 5));
    tick();
  } else if (e.code === "Home") {
    mixer.seek(0);
    tick();
  }
});

const baseName = () => songName.replace(/\.[^.]+$/, "");

interface DesktopApi {
  choose_save_path(filename: string): Promise<string | null>;
}
const desktopApi = () => (window as { pywebview?: { api?: DesktopApi } }).pywebview?.api;

async function download(blob: Blob, filename: string) {
  // The desktop app's web view can't save blob downloads, so ask it for a
  // native Save dialog and stream the file to the local backend instead.
  const api = desktopApi();
  if (api) {
    const path = await api.choose_save_path(filename);
    if (!path) return;
    const res = await fetch(`/api/desktop/save?path=${encodeURIComponent(path)}`, { method: "POST", body: blob });
    if (!res.ok) throw new Error(`Couldn't save the file (${res.status})`);
    return;
  }
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 60_000);
}

/** Disable a button and show `label` while `work` runs. */
async function busy(btn: HTMLButtonElement, label: string, work: () => Promise<void>) {
  const original = btn.innerHTML;
  btn.disabled = true;
  btn.textContent = label;
  try {
    await work();
  } catch (err) {
    alert(`Export failed: ${(err as Error).message}`);
  } finally {
    btn.disabled = false;
    btn.innerHTML = original;
  }
}

// Export menu
const exportMenu = $<HTMLButtonElement>("export-menu");
const exportList = $("export-list");
function setMenu(open: boolean) {
  exportList.hidden = !open;
  exportMenu.setAttribute("aria-expanded", String(open));
}
exportMenu.onclick = (e) => {
  e.stopPropagation();
  setMenu(exportList.hidden);
};
document.addEventListener("click", (e) => {
  if (!exportList.contains(e.target as Node)) setMenu(false);
});
document.addEventListener("keydown", (e) => e.key === "Escape" && setMenu(false));

/** Run an export, showing progress on the Export button while the menu is closed. */
function exportTask(label: string, work: (status: (s: string) => void) => Promise<void>) {
  setMenu(false);
  const original = exportMenu.innerHTML;
  exportMenu.disabled = true;
  exportMenu.textContent = label;
  return work((s) => (exportMenu.textContent = s))
    .catch((err) => alert(`Export failed: ${(err as Error).message}`))
    .finally(() => {
      exportMenu.disabled = false;
      exportMenu.innerHTML = original;
    });
}

$("export").onclick = () =>
  exportTask("Rendering mix…", async () => download(await mixer!.exportMix(), `${baseName()} (mix).wav`));

$("export-stems").onclick = () =>
  exportTask("Rendering…", async (status) => {
    const files = [];
    for (const [i, track] of mixer!.tracks.entries()) {
      status(`Rendering ${i + 1}/${mixer!.tracks.length}…`);
      files.push({ name: `${baseName()} - ${track.name}.wav`, blob: await mixer!.exportTrack(track) });
    }
    status("Zipping…");
    await download(await makeZip(files), `${baseName()} (stems).zip`);
  });

async function newSong() {
  await mixer?.close();
  mixer = null;
  show("upload");
}
$("new").onclick = newSong;
$("home-link").onclick = (e) => {
  e.preventDefault();
  if (sections.progress.hidden) void newSong();
};

window.addEventListener("resize", () => {
  fitLanes();
  for (const { canvas, peaks, track } of lanes) drawWaveform(canvas, peaks, stemColor(track.name));
  drawRuler();
  tick();
});

show("upload");
