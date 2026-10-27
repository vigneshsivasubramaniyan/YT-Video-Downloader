from __future__ import annotations
import os, re, threading, uuid, subprocess
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl, Field
import yt_dlp

BASE = Path(__file__).resolve().parent
OUT = Path(os.getenv("DOWNLOAD_DIR", str(BASE / "downloads"))).resolve()
OUT.mkdir(parents=True, exist_ok=True)
app = FastAPI(title="FilmCraft YouTube Import Helper", version="0.1.0")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

jobs: dict[str, dict] = {}
lock = threading.Lock()
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtube-nocookie.com"}

class MetadataRequest(BaseModel):
    url: HttpUrl

class ImportRequest(BaseModel):
    # Import into the currently running FilmCraft project via its documented CLI bridge.
    pass

class DownloadRequest(BaseModel):
    url: HttpUrl
    format: str = Field(default="mp4", pattern="^(mp4|webm|mp3)$")
    quality: str = Field(default="1080p", pattern="^(720p|1080p|1440p|2160p|best)$")
    trim: bool = False
    start: str = "00:00:00"
    end: str = "00:00:30"


def validate_url(url: str):
    from urllib.parse import urlparse
    host = (urlparse(url).hostname or "").lower()
    if host not in YOUTUBE_HOSTS:
        raise HTTPException(status_code=400, detail="Enter a valid YouTube URL.")


def to_seconds(value: str) -> int:
    value = value.strip()
    if not re.fullmatch(r"\d{1,2}:\d{2}(?::\d{2})?", value):
        raise HTTPException(status_code=400, detail=f"Invalid time '{value}'. Use MM:SS or HH:MM:SS.")
    parts = [int(x) for x in value.split(":")]
    if len(parts) == 2:
        minutes, seconds = parts
        if seconds > 59: raise HTTPException(status_code=400, detail="Seconds must be 00–59.")
        return minutes * 60 + seconds
    hours, minutes, seconds = parts
    if minutes > 59 or seconds > 59: raise HTTPException(status_code=400, detail="Minutes and seconds must be 00–59 in HH:MM:SS.")
    return hours * 3600 + minutes * 60 + seconds


def base_opts():
    return {"quiet": True, "no_warnings": True, "noplaylist": True, "socket_timeout": 20}

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "FilmCraft YouTube Export Helper"}

@app.get("/")
def home():
    return FileResponse(BASE / "static" / "index.html")

@app.post("/api/metadata")
def metadata(req: MetadataRequest):
    validate_url(str(req.url))
    try:
        with yt_dlp.YoutubeDL({**base_opts(), "skip_download": True}) as ydl:
            info = ydl.extract_info(str(req.url), download=False)
        return {"id": info.get("id"), "title": info.get("title", "Untitled video"),
                "channel": info.get("channel") or info.get("uploader"), "duration": info.get("duration"),
                "duration_text": info.get("duration_string"), "thumbnail": info.get("thumbnail"),
                "webpage_url": info.get("webpage_url"), "description": (info.get("description") or "")[:300]}
    except HTTPException: raise
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not read video metadata: {str(e)[:300]}")

@app.post("/api/download")
def download(req: DownloadRequest):
    url = str(req.url); validate_url(url)
    start = end = None
    if req.trim:
        start, end = to_seconds(req.start), to_seconds(req.end)
        if end <= start: raise HTTPException(status_code=400, detail="End time must be greater than start time.")
        if end - start > 4 * 3600: raise HTTPException(status_code=400, detail="Trim range cannot exceed 4 hours.")
    job_id = uuid.uuid4().hex[:12]
    with lock:
        jobs[job_id] = {"id": job_id, "status": "queued", "progress": 0, "message": "Queued", "filename": None, "error": None}
    thread = threading.Thread(target=run_download, args=(job_id, req, start, end), daemon=True)
    thread.start()
    return {"job_id": job_id, "status": "queued"}


def run_download(job_id: str, req: DownloadRequest, start: Optional[int], end: Optional[int]):
    def hook(data):
        with lock:
            job = jobs[job_id]
            status = data.get("status")
            if status == "downloading":
                total = data.get("total_bytes") or data.get("total_bytes_estimate")
                done = data.get("downloaded_bytes", 0)
                job["status"] = "downloading"
                job["progress"] = min(95, int(done * 95 / total)) if total else job.get("progress", 0)
                job["message"] = "Downloading media…"
            elif status == "finished":
                job["progress"] = 96; job["message"] = "Processing output…"
    try:
        fmt = req.format
        if fmt == "mp3":
            format_selector = "bestaudio/best"
            postprocessors = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "320"}]
            ext = "mp3"
        else:
            height = {"720p": 720, "1080p": 1080, "1440p": 1440, "2160p": 2160}.get(req.quality)
            if fmt == "webm":
                format_selector = (f"bestvideo[height<={height}]+bestaudio/best[height<={height}]" if height else "bestvideo+bestaudio/best")
                postprocessors = []
            else:
                # Prefer H.264/AAC for broad editing compatibility; merge/transcode to MP4 when needed.
                format_selector = (f"bestvideo[height<={height}][vcodec^=avc1]+bestaudio[ext=m4a]/best[height<={height}][ext=mp4]/best" if height else "bestvideo[vcodec^=avc1]+bestaudio[ext=m4a]/best[ext=mp4]/best")
                postprocessors = [{"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}]
            ext = fmt
        opts = {**base_opts(), "format": format_selector, "outtmpl": str(OUT / f"{job_id}_%(title).100s.%(ext)s"),
                "progress_hooks": [hook], "postprocessors": postprocessors, "merge_output_format": "mp4" if fmt == "mp4" else None,
                "windowsfilenames": True, "restrictfilenames": True}
        if req.trim:
            # The Python API uses download_ranges; --download-sections is a CLI option.
            from yt_dlp.utils import download_range_func
            opts["download_ranges"] = download_range_func(None, [(start, end)])
            opts["force_keyframes_at_cuts"] = True
        if fmt == "mp3": opts["postprocessors_args"] = ["-b:a", "320k"]
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([str(req.url)])
        # Locate this job's output, ignoring partial files.
        candidates = [p for p in OUT.glob(f"{job_id}_*") if p.is_file() and not p.name.endswith((".part", ".ytdl"))]
        if not candidates: raise RuntimeError("Download finished but no output file was found. Check FFmpeg installation and format availability.")
        result = max(candidates, key=lambda p: p.stat().st_mtime)
        with lock:
            jobs[job_id].update(status="completed", progress=100, message="Export ready", filename=result.name)
    except Exception as e:
        with lock:
            jobs[job_id].update(status="failed", message="Export failed", error=str(e)[:500])


def filmcraft_cli_path() -> str:
    configured = os.getenv("FILMCRAFT_CLI_PATH", "").strip()
    if configured:
        return configured
    default = Path(r"C:\Program Files\FilmCraft\filmcraft-cli.exe")
    if default.is_file():
        return str(default)
    raise HTTPException(status_code=503, detail="FilmCraft CLI not found. Set FILMCRAFT_CLI_PATH to filmcraft-cli.exe and launch FilmCraft with its authenticated control channel enabled.")


@app.post("/api/import/{job_id}")
def import_to_filmcraft(job_id: str):
    with lock:
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Export job not found")
        filename = job.get("filename")
        status = job.get("status")
    if status != "completed" or not filename:
        raise HTTPException(status_code=409, detail="Export must finish before importing")
    path = (OUT / filename).resolve()
    if path.parent != OUT or not path.is_file():
        raise HTTPException(status_code=404, detail="Export file not found")

    token = os.getenv("FILMCRAFT_CONTROL_TOKEN", "").strip()
    if not re.fullmatch(r"[0-9a-fA-F]{64}", token):
        raise HTTPException(status_code=503, detail="FILMCRAFT_CONTROL_TOKEN must be the same 64-character token used by the running FilmCraft control server.")
    bridge = os.getenv("FILMCRAFT_CONTROL_ADDRESS", "127.0.0.1:9876").strip()
    cli = filmcraft_cli_path()
    try:
        result = subprocess.run(
            [cli, "--bridge", bridge, "import", str(path)],
            capture_output=True, text=True, timeout=90, check=False,
            env={**os.environ, "FILMCRAFT_CONTROL_TOKEN": token},
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="FilmCraft import timed out. Check that FilmCraft is running with --control and the bridge token matches.")
    except OSError as e:
        raise HTTPException(status_code=503, detail=f"Could not start FilmCraft CLI: {e}")
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "FilmCraft CLI import failed").strip()[-1200:]
        raise HTTPException(status_code=502, detail=detail)
    return {"status": "imported", "filename": path.name, "message": "Media imported into the active FilmCraft project.", "result": result.stdout.strip()[-1200:]}

@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    with lock:
        job = jobs.get(job_id)
        if not job: raise HTTPException(status_code=404, detail="Job not found")
        return dict(job)

@app.get("/api/files/{job_id}")
def get_file(job_id: str):
    with lock:
        job = jobs.get(job_id)
        if not job: raise HTTPException(status_code=404, detail="Job not found")
        filename = job.get("filename")
    if not filename: raise HTTPException(status_code=409, detail="Export is not ready")
    path = (OUT / filename).resolve()
    if path.parent != OUT or not path.is_file(): raise HTTPException(status_code=404, detail="Export file not found")
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")
