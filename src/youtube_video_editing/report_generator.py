"""Human-readable report, EDL, and normalized plan outputs."""

from __future__ import annotations

import csv
import json
from fractions import Fraction
from pathlib import Path

from .models import BuiltTimeline
from .timecode_utils import format_timestamp, rational_text


def write_edl_csv(timeline: BuiltTimeline, output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "order", "section_id", "section_name", "clip_id", "description",
        "source_in", "source_out", "source_duration",
        "timeline_in", "timeline_out", "timeline_duration",
        "source_in_frame", "source_out_frame",
    ]
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index, clip in enumerate(timeline.clips, start=1):
            writer.writerow(
                {
                    "order": index,
                    "section_id": clip.section_id,
                    "section_name": clip.section_name,
                    "clip_id": clip.clip_id,
                    "description": clip.description,
                    "source_in": rational_text(clip.source_in),
                    "source_out": rational_text(clip.source_out),
                    "source_duration": rational_text(clip.duration),
                    "timeline_in": rational_text(clip.timeline_start),
                    "timeline_out": rational_text(clip.timeline_end),
                    "timeline_duration": rational_text(clip.duration),
                    "source_in_frame": clip.source_in_frame,
                    "source_out_frame": clip.source_out_frame,
                }
            )
    return output


def write_validated_plan(timeline: BuiltTimeline, output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(timeline.to_validated_plan_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return output


def write_edit_report(
    timeline: BuiltTimeline,
    output_path: str | Path,
    *,
    optional_export_notes: tuple[str, ...] = (),
) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    metadata = timeline.source
    lines = [
        f"# Edit report — {timeline.project_name}",
        "",
        "## Source media",
        "",
        f"- File: {timeline.source_path}",
        f"- Duration: {format_timestamp(metadata.duration)} ({rational_text(metadata.duration)} s)",
        f"- Video: {metadata.video_codec or 'unknown'}, {metadata.width}×{metadata.height}",
        f"- Audio: {metadata.audio_codec or 'none'}, "
        f"{metadata.audio_channels or 0} channel(s), "
        f"{metadata.audio_sample_rate or 'n/a'} Hz",
        f"- Frame rate: {metadata.frame_rate} fps "
        f"(average={metadata.average_frame_rate}, nominal={metadata.nominal_frame_rate})",
        f"- Pixel format: {metadata.pixel_format or 'unknown'}",
        f"- Streams: {metadata.video_stream_count} video, {metadata.audio_stream_count} audio",
        f"- Variable-frame-rate heuristic: {'possible' if metadata.appears_variable_frame_rate else 'not detected'}",
        "",
        "## Timeline summary",
        "",
        f"- Sequence: {timeline.sequence_name}",
        f"- Timeline frame rate: {timeline.frame_rate} fps",
        f"- Clip range selection: {timeline.outro_variant}",
        f"- Sections: {len(timeline.sections)}",
        f"- Clips: {len(timeline.clips)}",
        f"- Final duration: {format_timestamp(timeline.duration)} "
        f"({rational_text(timeline.duration)} s)",
        "",
        "## Section timing",
        "",
        "| Section | Target window | Actual window | Source duration | Start offset | Clips |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for section in timeline.sections:
        target_window = (
            "—"
            if section.target_start is None or section.target_end is None
            else f"{format_timestamp(section.target_start)}–{format_timestamp(section.target_end)}"
        )
        actual_window = (
            f"{format_timestamp(section.actual_start)}–{format_timestamp(section.actual_end)}"
        )
        start_offset = "—"
        if section.start_offset_difference is not None:
            offset_value = rational_text(section.start_offset_difference)
            if section.start_offset_difference > 0:
                offset_value = f"+{offset_value}"
            start_offset = f"{offset_value} s"
        lines.append(
            f"| {section.name} | {target_window} | {actual_window} | "
            f"{format_timestamp(section.actual_duration)} | {start_offset} | "
            f"{len(section.clips)} |"
        )
    gaps = timeline.timeline_gaps()
    lines.extend(["", "## Explicit timeline gaps", ""])
    if gaps:
        lines.extend([
            "These black/silent intervals preserve the requested target positions; "
            "they are not missing source clips.",
            "",
            "| Gap | Before section | Timeline range | Duration |",
            "|---:|---|---:|---:|",
        ])
        for index, gap in enumerate(gaps, start=1):
            lines.append(
                f"| {index} | {gap['before_section_name']} | "
                f"{format_timestamp(Fraction(gap['start']))}–"
                f"{format_timestamp(Fraction(gap['end']))} | "
                f"{format_timestamp(Fraction(gap['duration']))} |"
            )
    else:
        lines.append("No timeline gaps.")
    lines.extend(["", "## Clip decisions", ""])
    for index, clip in enumerate(timeline.clips, start=1):
        lines.extend(
            [
                f"### {index}. {clip.clip_id} — {clip.description}",
                "",
                f"- Section: {clip.section_name}",
                f"- Source In/Out: {format_timestamp(clip.source_in)} – "
                f"{format_timestamp(clip.source_out)} "
                f"({rational_text(clip.source_in)} s – {rational_text(clip.source_out)} s)",
                f"- Source frames: [{clip.source_in_frame}, {clip.source_out_frame})",
                f"- Actual timeline In/Out: {format_timestamp(clip.timeline_start)} – "
                f"{format_timestamp(clip.timeline_end)}",
                f"- Duration: {format_timestamp(clip.duration)}",
                "",
            ]
        )
    lines.extend(["## Warnings and validation", ""])
    all_warnings = list(timeline.warnings) + list(optional_export_notes)
    if all_warnings:
        lines.extend(f"- {warning}" for warning in all_warnings)
    else:
        lines.append("- No warnings.")
    lines.extend(
        [
            "",
            "Validation confirms every parsed source clip is represented in the exported "
            "storyline, clip order and source ranges are preserved, explicit gap elements "
            "represent target-alignment time, section placement is checked against target "
            "starts, and FCPXML resource references and durations are internally consistent. "
            "A successful structural validation is not the same as an import test in "
            "DaVinci Resolve.",
            "",
        ]
    )
    output.write_text("\n".join(lines), encoding="utf-8")
    return output
