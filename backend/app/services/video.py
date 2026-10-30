"""Video checks and frame extraction with FFmpeg / ffprobe (blueprint §5 video mode)."""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".3gp"}
MAX_DURATION_S = 2 * 3600
MAX_UPLOAD_BYTES = 4 * 1024**3  # 4 GB
FRAME_WIDTH = 640  # blueprint §5: photos about 640 px wide

# Tags in which phones store a recording location. A single location for the whole file is not a per-frame GPS track.
LOCATION_TAGS = ("location", "location-eng", "com.apple.quicktime.location.ISO6709")


class VideoError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def probe(path: Path) -> dict:
    """Read a video's details. Raises VideoError for unsupported or unreadable files."""
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise VideoError("unsupported_format", f"'{path.suffix or 'no extension'}' videos are not supported. Use MP4, MOV, MKV, WEBM, AVI or 3GP.")
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=60, check=True,
        )
        info = json.loads(out.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        raise VideoError("unreadable", "This file could not be read as a video. It may be damaged or not really a video.")
    except subprocess.TimeoutExpired:
        raise VideoError("unreadable", "Reading this video took too long.")

    video = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    if not video:
        raise VideoError("no_video_stream", "This file has no video picture (it may be audio only).")
    try:
        duration = float(info.get("format", {}).get("duration") or video.get("duration"))
    except (TypeError, ValueError):
        raise VideoError("no_duration", "The length of this video could not be read.")
    if duration <= 0:
        raise VideoError("no_duration", "This video has no length.")
    if duration > MAX_DURATION_S:
        raise VideoError("too_long", "Videos longer than 2 hours are not supported. Please split the ride.")

    tags = {**(info.get("format", {}).get("tags") or {}), **(video.get("tags") or {})}
    location_tag = next((tags[t] for t in LOCATION_TAGS if tags.get(t)), None)
    created = tags.get("creation_time")
    created_utc = None
    if created:
        try:
            created_utc = datetime.fromisoformat(created.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)
        except ValueError:
            created_utc = None
    rotation = (video.get("tags") or {}).get("rotate")
    for sd in video.get("side_data_list") or []:
        if "rotation" in sd:
            rotation = sd["rotation"]
    return {
        "duration_s": round(duration, 2),
        "codec": video.get("codec_name"),
        "width": video.get("width"),
        "height": video.get("height"),
        "rotation": rotation,
        "size_bytes": int(info.get("format", {}).get("size") or path.stat().st_size),
        "format": info.get("format", {}).get("format_name"),
        # Only a single location for the file, if any. Never used as a per-frame position.
        "location_tag": location_tag,
        "creation_time_utc": created_utc.isoformat() if created_utc else None,
    }


def frame_times(duration_s: float, interval_s: float, start_s: float = 0.0, end_s: float | None = None) -> list[float]:
    """Seconds at which to take a frame: one every `interval_s`, centred in each interval, within [start, end]."""
    end = duration_s if end_s is None else min(end_s, duration_s)
    times, t = [], start_s + interval_s / 2
    while t < end:
        times.append(round(t, 2))
        t += interval_s
    return times


def extract_frame(src: Path, t: float, out: Path) -> None:
    """Save the frame at second `t` as a JPEG about 640 px wide (rotation from the phone is applied by FFmpeg)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(src), "-frames:v", "1",
        "-vf", f"scale='min({FRAME_WIDTH},iw)':-2", "-q:v", "4", str(out),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if res.returncode != 0 or not out.exists() or out.stat().st_size == 0:
        raise VideoError("frame_failed", f"Could not read the frame at {t:.1f} s.")
