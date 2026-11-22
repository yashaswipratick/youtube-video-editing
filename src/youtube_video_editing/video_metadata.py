"""FFprobe-backed source-media inspection."""

from __future__ import annotations

import json
import shutil
import subprocess
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path
from typing import Any

from .models import VideoMetadata


class MetadataError(RuntimeError):
    pass


def _fraction(value: Any) -> Fraction | None:
    if value in (None, "", "N/A", "0/0"):
        return None
    try:
        if "/" in str(value):
            result = Fraction(str(value))
        else:
            result = Fraction(Decimal(str(value)))
        return result if result > 0 else None
    except (ValueError, ZeroDivisionError, InvalidOperation):
        return None


def _int(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "", "N/A") else None
    except (TypeError, ValueError):
        return None


def probe_video(path: str | Path, *, ffprobe: str | None = None) -> VideoMetadata:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise MetadataError(f"Source video does not exist or is not a file: {source}")
    executable = ffprobe or shutil.which("ffprobe")
    if not executable:
        raise MetadataError("FFprobe was not found. Install FFmpeg and ensure ffprobe is on PATH.")

    command = [
        executable,
        "-v", "error",
        "-show_streams",
        "-show_format",
        "-of", "json",
        str(source),
    ]
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
    except OSError as exc:
        raise MetadataError(f"Unable to start FFprobe: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "unknown FFprobe error"
        raise MetadataError(f"FFprobe could not inspect {source}: {detail}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise MetadataError(f"FFprobe returned invalid JSON for {source}") from exc

    streams = payload.get("streams", [])
    video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
    audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
    if not video_streams:
        raise MetadataError(f"No video stream was found in source media: {source}")
    video = video_streams[0]
    audio = audio_streams[0] if audio_streams else {}

    average_rate = _fraction(video.get("avg_frame_rate"))
    nominal_rate = _fraction(video.get("r_frame_rate"))
    frame_rate = average_rate or nominal_rate
    if frame_rate is None:
        raise MetadataError(f"FFprobe did not provide a usable video frame rate for {source}")

    duration = _fraction(video.get("duration")) or _fraction(payload.get("format", {}).get("duration"))
    if duration is None:
        duration = _fraction(audio.get("duration"))
    if duration is None:
        raise MetadataError(f"FFprobe did not provide a usable media duration for {source}")

    vfr = bool(
        average_rate
        and nominal_rate
        and abs(average_rate - nominal_rate) > Fraction(1, 1000)
    )
    return VideoMetadata(
        path=source,
        duration=duration,
        video_codec=video.get("codec_name"),
        audio_codec=audio.get("codec_name") if audio else None,
        width=_int(video.get("width")),
        height=_int(video.get("height")),
        frame_rate=frame_rate,
        average_frame_rate=average_rate,
        nominal_frame_rate=nominal_rate,
        pixel_format=video.get("pix_fmt"),
        audio_sample_rate=_int(audio.get("sample_rate")) if audio else None,
        audio_channels=_int(audio.get("channels")) if audio else None,
        video_stream_count=len(video_streams),
        audio_stream_count=len(audio_streams),
        appears_variable_frame_rate=vfr,
        format_name=payload.get("format", {}).get("format_name"),
    )
