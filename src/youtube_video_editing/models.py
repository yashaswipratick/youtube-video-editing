"""Typed domain models shared by the timeline pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ClipPlan:
    clip_id: str
    source_in_requested: Fraction
    source_out_requested: Fraction
    description: str


@dataclass(frozen=True)
class SectionPlan:
    section_id: str
    name: str
    target_start: Fraction | None
    target_end: Fraction | None
    purpose: str
    clips: tuple[ClipPlan, ...]

    @property
    def target_duration(self) -> Fraction | None:
        if self.target_start is None or self.target_end is None:
            return None
        return self.target_end - self.target_start


@dataclass(frozen=True)
class EditPlan:
    project_name: str
    sequence_name: str
    timeline_fps: Fraction | None
    sections: tuple[SectionPlan, ...]
    selected_outro_variant: str
    source_document: dict[str, Any] = field(repr=False)


@dataclass(frozen=True)
class VideoMetadata:
    path: Path
    duration: Fraction
    video_codec: str | None
    audio_codec: str | None
    width: int | None
    height: int | None
    frame_rate: Fraction
    average_frame_rate: Fraction | None
    nominal_frame_rate: Fraction | None
    pixel_format: str | None
    audio_sample_rate: int | None
    audio_channels: int | None
    video_stream_count: int
    audio_stream_count: int
    appears_variable_frame_rate: bool
    format_name: str | None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["path"] = str(self.path)
        for key in (
            "duration",
            "frame_rate",
            "average_frame_rate",
            "nominal_frame_rate",
        ):
            value = result[key]
            result[key] = None if value is None else str(value)
        return result


@dataclass(frozen=True)
class TimelineClip:
    clip_id: str
    section_id: str
    section_name: str
    description: str
    source_in_requested: Fraction
    source_out_requested: Fraction
    source_in_frame: int
    source_out_frame: int
    source_in: Fraction
    source_out: Fraction
    duration: Fraction
    timeline_start: Fraction
    timeline_end: Fraction


@dataclass(frozen=True)
class TimelineSection:
    section_id: str
    name: str
    purpose: str
    target_start: Fraction | None
    target_end: Fraction | None
    target_duration: Fraction | None
    actual_start: Fraction
    actual_end: Fraction
    actual_duration: Fraction
    clips: tuple[TimelineClip, ...]

    @property
    def duration_difference(self) -> Fraction | None:
        if self.target_duration is None:
            return None
        return self.actual_duration - self.target_duration

    @property
    def start_offset_difference(self) -> Fraction | None:
        if self.target_start is None:
            return None
        return self.actual_start - self.target_start

    @property
    def end_offset_difference(self) -> Fraction | None:
        if self.target_end is None:
            return None
        return self.actual_end - self.target_end


@dataclass(frozen=True)
class BuiltTimeline:
    source: VideoMetadata
    source_path: Path
    project_name: str
    sequence_name: str
    frame_rate: Fraction
    sections: tuple[TimelineSection, ...]
    clips: tuple[TimelineClip, ...]
    duration: Fraction
    outro_variant: str
    warnings: tuple[str, ...] = ()

    def timeline_gaps(self) -> list[dict[str, str | None]]:
        """Return explicit black/silent timeline gaps introduced to honor target starts."""
        from .timecode_utils import rational_text

        gaps: list[dict[str, str | None]] = []
        cursor = Fraction(0)
        for section in self.sections:
            if section.actual_start > cursor:
                gaps.append({
                    "before_section_id": section.section_id,
                    "before_section_name": section.name,
                    "start": rational_text(cursor),
                    "end": rational_text(section.actual_start),
                    "duration": rational_text(section.actual_start - cursor),
                })
            cursor = section.actual_end
        if self.duration > cursor:
            gaps.append({
                "before_section_id": None,
                "before_section_name": "End of timeline",
                "start": rational_text(cursor),
                "end": rational_text(self.duration),
                "duration": rational_text(self.duration - cursor),
            })
        return gaps

    def to_validated_plan_dict(self) -> dict[str, Any]:
        from .timecode_utils import format_timestamp

        def clip_data(clip: TimelineClip) -> dict[str, Any]:
            return {
                "id": clip.clip_id,
                "section_id": clip.section_id,
                "section_name": clip.section_name,
                "description": clip.description,
                "source_in_requested": str(clip.source_in_requested),
                "source_out_requested": str(clip.source_out_requested),
                "source_in_frame": clip.source_in_frame,
                "source_out_frame": clip.source_out_frame,
                "source_in": str(clip.source_in),
                "source_out": str(clip.source_out),
                "duration": str(clip.duration),
                "timeline_start": str(clip.timeline_start),
                "timeline_end": str(clip.timeline_end),
            }

        return {
            "project_name": self.project_name,
            "sequence_name": self.sequence_name,
            "source": self.source.to_dict(),
            "timeline_frame_rate": str(self.frame_rate),
            "selected_outro_variant": self.outro_variant,
            "timeline_duration": str(self.duration),
            "timeline_duration_display": format_timestamp(self.duration),
            "clip_count": len(self.clips),
            "section_count": len(self.sections),
            "timeline_gaps": self.timeline_gaps(),
            "warnings": list(self.warnings),
            "sections": [
                {
                    "id": section.section_id,
                    "name": section.name,
                    "target_start": None if section.target_start is None else str(section.target_start),
                    "target_end": None if section.target_end is None else str(section.target_end),
                    "target_duration": None if section.target_duration is None else str(section.target_duration),
                    "actual_start": str(section.actual_start),
                    "actual_end": str(section.actual_end),
                    "actual_duration": str(section.actual_duration),
                    "duration_difference": None if section.duration_difference is None else str(section.duration_difference),
                    "start_offset_difference": None if section.start_offset_difference is None else str(section.start_offset_difference),
                    "end_offset_difference": None if section.end_offset_difference is None else str(section.end_offset_difference),
                    "clips": [clip_data(clip) for clip in section.clips],
                }
                for section in self.sections
            ],
            "clips": [clip_data(clip) for clip in self.clips],
        }
