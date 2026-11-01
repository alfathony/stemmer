import { createJob, stemUrl, waitForJob, type Job, type Mode } from "./api";
import { Mixer, type Track } from "./mixer";
import { computePeaks, drawWaveform } from "./waveform";
import { makeZip } from "./zip";

// Lane colours: [background, waveform]
const STEM_COLORS: Record<string, [string, string]> = {
  vocals: ["#3b3670", "#8b7dff"],
  drums: ["#5a2738", "#ff5c84"],
  bass: ["#6b6a24", "#f4f000"],
  other: ["#22704b", "#2dff9a"],
  guitar: ["#6e4520", "#ffa24c"],
  piano: ["#1f5a6b", "#56d9ff"],
};
const STEM_ORDER = ["vocals", "drums", "bass", "guitar", "piano", "other"];
const CTRL_WIDTH = () => (window.innerWidth <= 640 ? 160 : 240);

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const sections = { upload: $("upload"), progress: $("progress"), mixer: $("mixer") };

let mixer: Mixer | null = null;
let lanes: { track: Track; el: HTMLElement; canvas: HTMLCanvasElement; peaks: Float32Array }[] = [];
let songName = "";

function show(name: keyof typeof sections) {
  for (const [k, el] of Object.entries(sections)) el.hidden = k !== name;
}

// ---------- upload ----------

const fileInput = $<HTMLInputElement>("file");
const drop = $("drop");

$("browse").onclick = () => fileInput.click();
fileInput.onchange = () => fileInput.files?.[0] && start(fileInput.files[0]);
drop.ondragover = (e) => {
  e.preventDefault();
  drop.classList.add("over");
};
drop.ondragleave = () => drop.classList.remove("over");
drop.ondrop = (e) => {
  e.preventDefault();
  drop.classList.remove("over");
  const file = e.dataTransfer?.files[0];
  if (file) start(file);
};

function setProgress(label: string, fraction: number) {
  $("progress-label").textContent = label;
  $("progress-fill").style.width = `${Math.round(fraction * 100)}%`;
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
  const mode = (document.querySelector<HTMLInputElement>('input[name="mode"]:checked')!.value) as Mode;
  songName = file.name;
  $("progress-name").textContent = file.name;
  $("progress-error").hidden = true;
  $("retry").hidden = true;
  show("progress");

  try {
    // Overall bar: upload 0–10%, separation 10–90%, downloading stems 90–100%.
    setProgress("Uploading file", 0);
    const job = await createJob(file, mode, (f) => setProgress(`Uploading file ${Math.round(f * 100)}%`, f * 0.1));
    const done = await waitForJob(job.id, (j) => {
      const pct = j.status === "processing" ? ` ${Math.round(j.progress * 100)}%` : "";
      setProgress(STATUS_LABEL[j.status] + pct, 0.1 + j.progress * 0.8);
    });
    await loadStems(done, (f) => setProgress("Loading stems", 0.9 + f * 0.1));
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

function renderLanes() {
  const container = $("lanes");
  container.querySelectorAll(".lane").forEach((el) => el.remove());
  lanes = [];
  $("song-name").textContent = songName;

  for (const track of mixer!.tracks) {
    const [bg, fg] = STEM_COLORS[track.name] ?? ["#333", "#aaa"];
    const el = document.createElement("div");
    el.className = "lane";
    el.innerHTML = `
      <div class="lane-ctrl">
        <span class="lane-name"></span>
        <span class="lane-btns">
          <button class="mute" aria-pressed="false" title="Mute">M</button>
          <button class="solo" aria-pressed="false" title="Solo">S</button>
          <button class="download" title="Download as WAV">⤓</button>
        </span>
        <input type="range" min="0" max="1.5" step="0.01" value="1" />
      </div>
      <div class="lane-wave" style="background:${bg}"><canvas></canvas></div>`;
    el.querySelector(".lane-name")!.textContent = track.name;
    const slider = el.querySelector<HTMLInputElement>("input")!;
    slider.setAttribute("aria-label", `${track.name} volume`);
    slider.oninput = () => {
      track.volume = Number(slider.value);
      refreshGains();
    };
    const toggle = (cls: "mute" | "solo") => {
      const btn = el.querySelector<HTMLButtonElement>(`.${cls}`)!;
      btn.onclick = () => {
        if (cls === "mute") track.muted = !track.muted;
        else track.solo = !track.solo;
        btn.setAttribute("aria-pressed", String(cls === "mute" ? track.muted : track.solo));
        refreshGains();
      };
    };
    toggle("mute");
    toggle("solo");
    const dl = el.querySelector<HTMLButtonElement>(".download")!;
    dl.setAttribute("aria-label", `Download ${track.name} as WAV`);
    dl.onclick = () =>
      busy(dl, "…", async () => download(await mixer!.exportTrack(track), `${baseName()} - ${track.name}.wav`));

    const wave = el.querySelector<HTMLElement>(".lane-wave")!;
    wave.onclick = (e) => {
      const rect = wave.getBoundingClientRect();
      mixer!.seek(((e.clientX - rect.left) / rect.width) * mixer!.duration);
      tick();
    };

    container.appendChild(el);
    const canvas = el.querySelector("canvas")!;
    const peaks = computePeaks(track.buffer, 1200);
    drawWaveform(canvas, peaks, fg);
    lanes.push({ track, el, canvas, peaks });
  }
  updatePlayButton();
  tick();
}

function refreshGains() {
  mixer!.updateGains();
  for (const { track, el } of lanes) el.classList.toggle("silent", mixer!.effectiveGain(track) === 0);
}

const fmt = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

function tick() {
  if (!mixer) return;
  const t = mixer.currentTime;
  $("time").textContent = `${fmt(t)} / ${fmt(mixer.duration)}`;
  const waveWidth = $("lanes").clientWidth - CTRL_WIDTH();
  $("playhead").style.left = `${CTRL_WIDTH() + (t / mixer.duration) * waveWidth}px`;
}

(function loop() {
  if ((mixer as Mixer | null)?.playing) tick();
  requestAnimationFrame(loop);
})();

function updatePlayButton() {
  const btn = $("play");
  const playing = mixer?.playing ?? false;
  btn.textContent = playing ? "❚❚" : "▶";
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
document.addEventListener("keydown", (e) => {
  if (e.code !== "Space" || sections.mixer.hidden) return;
  if ((e.target as HTMLElement).matches("input, button")) return;
  e.preventDefault();
  void togglePlay();
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
  const original = btn.textContent;
  btn.disabled = true;
  btn.textContent = label;
  try {
    await work();
  } catch (err) {
    alert(`Export failed: ${(err as Error).message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = original;
  }
}

$("export").onclick = () =>
  busy($("export"), "Rendering…", async () => download(await mixer!.exportMix(), `${baseName()} (mix).wav`));

$("export-stems").onclick = () => {
  const btn = $<HTMLButtonElement>("export-stems");
  return busy(btn, "Rendering…", async () => {
    const files = [];
    for (const [i, track] of mixer!.tracks.entries()) {
      btn.textContent = `Rendering ${i + 1}/${mixer!.tracks.length}…`;
      files.push({ name: `${baseName()} - ${track.name}.wav`, blob: await mixer!.exportTrack(track) });
    }
    btn.textContent = "Zipping…";
    await download(await makeZip(files), `${baseName()} (stems).zip`);
  });
};

$("new").onclick = async () => {
  await mixer?.close();
  mixer = null;
  show("upload");
};

window.addEventListener("resize", () => {
  for (const { canvas, peaks, track } of lanes) {
    drawWaveform(canvas, peaks, (STEM_COLORS[track.name] ?? ["", "#aaa"])[1]);
  }
  tick();
});
