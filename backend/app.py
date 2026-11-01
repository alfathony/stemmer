"""Stemmer API: upload a song, get separated stems back.

Run: uvicorn app:app --port 8000
"""
import os
import shutil
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from analysis import analyze
from separator import MODELS, NO_WINDOW, separate

# The desktop app points these at Application Support and the bundled UI.
DATA_DIR = Path(os.environ.get("STEMMER_DATA_DIR", Path(__file__).parent / "data"))
STATIC_DIR = os.environ.get("STEMMER_STATIC_DIR")
MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # videos are much bigger than audio
JOB_TTL_SECONDS = 6 * 60 * 60
AUDIO_EXT = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".aiff"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm"}
ALLOWED_EXT = AUDIO_EXT | VIDEO_EXT

app = FastAPI(title="Stemmer")
# One GPU job at a time; everything else waits in the queue.
worker = ThreadPoolExecutor(max_workers=1)


@dataclass
class Job:
    id: str
    name: str
    mode: str
    status: str = "queued"  # queued | extracting | processing | encoding | analyzing | done | error
    progress: float = 0.0
    error: str | None = None
    stems: dict[str, Path] = field(default_factory=dict)
    analysis: dict | None = None
    created: float = field(default_factory=time.time)

    def public(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "mode": self.mode,
            "status": self.status,
            "progress": round(self.progress, 3),
            "error": self.error,
            "stems": list(self.stems),
            "analysis": self.analysis,
        }


jobs: dict[str, Job] = {}


def extract_audio(src: Path) -> Path:
    """Decode any audio or video file to a stereo 44.1 kHz WAV."""
    dst = src.with_name("audio.wav")
    result = subprocess.run(
        ["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-i", str(src),
         "-vn", "-ac", "2", "-ar", "44100", str(dst)],
        capture_output=True, text=True, creationflags=NO_WINDOW,
    )
    if result.returncode != 0 or not dst.exists():
        raise RuntimeError(f"Couldn't read audio from this file. {result.stderr.strip()[-300:]}")
    return dst


def run_job(job: Job, src: Path) -> None:
    def on_progress(p: float) -> None:
        job.progress = p
        job.status = "encoding" if p >= 1 else "processing"

    try:
        job.status = "extracting"
        audio = extract_audio(src)
        src.unlink()  # a video upload can be hundreds of MB
        job.status = "processing"
        job.stems = separate(audio, audio.parent, job.mode, on_progress)
        job.status = "analyzing"
        try:
            job.analysis = analyze(audio, job.stems.get("drums"))
        except Exception as e:  # stems are still useful without tempo info
            job.analysis = {"bpm": None, "time_signature": None, "error": str(e)}
        job.progress, job.status = 1.0, "done"
    except Exception as e:  # surface the failure to the client
        job.status, job.error = "error", str(e)


@app.post("/api/jobs")
async def create_job(file: UploadFile = File(...), mode: str = Form("4stems")):
    if mode not in MODELS:
        raise HTTPException(400, f"mode must be one of {list(MODELS)}")
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"unsupported file type {ext or '(none)'}")

    job = Job(id=uuid.uuid4().hex, name=file.filename or "song", mode=mode)
    job_dir = DATA_DIR / job.id
    job_dir.mkdir(parents=True)
    src = job_dir / f"input{ext}"

    size = 0
    with src.open("wb") as f:
        while chunk := await file.read(1 << 20):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                f.close()
                shutil.rmtree(job_dir, ignore_errors=True)
                raise HTTPException(413, "file too large (max 500 MB)")
            f.write(chunk)

    jobs[job.id] = job
    worker.submit(run_job, job, src)
    return job.public()


def get_job(job_id: str) -> Job:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return job


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    return get_job(job_id).public()


@app.get("/api/jobs/{job_id}/stems/{stem}.mp3")
def job_stem(job_id: str, stem: str):
    job = get_job(job_id)
    path = job.stems.get(stem)
    if job.status != "done" or not path:
        raise HTTPException(404, "stem not ready")
    return FileResponse(path, media_type="audio/mpeg", filename=f"{stem}.mp3")


# Desktop app only: paths the user picked in a native Save dialog. The web
# view can't save blob downloads itself, so the page streams the file here.
# Only paths the user just chose can be written, each once.
approved_save_paths: set[str] = set()


@app.post("/api/desktop/save")
async def desktop_save(request: Request, path: str):
    if path not in approved_save_paths:
        raise HTTPException(403, "path was not chosen in a save dialog")
    approved_save_paths.discard(path)
    with open(path, "wb") as f:
        async for chunk in request.stream():
            f.write(chunk)
    return {"saved": path}


def cleanup_loop() -> None:
    while True:
        cutoff = time.time() - JOB_TTL_SECONDS
        for job in list(jobs.values()):
            if job.created < cutoff and job.status in ("done", "error"):
                shutil.rmtree(DATA_DIR / job.id, ignore_errors=True)
                jobs.pop(job.id, None)
        time.sleep(600)


@app.on_event("startup")
def startup() -> None:
    # Jobs live in memory, so anything left on disk from a previous run is orphaned.
    shutil.rmtree(DATA_DIR, ignore_errors=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    threading.Thread(target=cleanup_loop, daemon=True).start()


# Serve the built frontend from the same origin. Mounted last so /api wins.
if STATIC_DIR:
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="ui")
