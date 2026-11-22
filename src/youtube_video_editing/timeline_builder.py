"""Build a sequential edit from validated source ranges."""

from __future__ import annotations

from fractions import Fraction

from .models import (
    BuiltTimeline,
    EditPlan,
    TimelineClip,
    TimelineSection,
    VideoMetadata,
)
from .timecode_utils import frames_to_seconds, seconds_to_frames


class TimelineBuildError(ValueError):
    pass


def build_timeline(
    plan: EditPlan,
    source: VideoMetadata,
    *,
    timeline_fps: Fraction | None = None,
) -> BuiltTimeline:
    fps = timeline_fps or plan.timeline_fps or source.frame_rate
    if fps <= 0:
        raise TimelineBuildError("Timeline frame rate must be greater than zero")
    if source.frame_rate <= 0:
        raise TimelineBuildError("Source frame rate must be greater than zero")

    cursor = Fraction(0)
    timeline_clips: list[TimelineClip] = []
    sections: list[TimelineSection] = []
    warnings: list[str] = []

    for section in plan.sections:
        section_clips: list[TimelineClip] = []
        if section.target_start is not None:
            if section.target_start > cursor:
                gap_duration = section.target_start - cursor
                warnings.append(
                    f"Inserted a {gap_duration}s black/silent placeholder before "
                    f"{section.name} to honor its target start."
                )
                cursor = section.target_start
            elif section.target_start < cursor:
                delay = cursor - section.target_start
                warnings.append(
                    f"{section.name} starts {delay}s after its target start because "
                    "preceding source footage runs long; no source clips were removed."
                )
        section_start = cursor
        for clip in section.clips:
            requested_in = clip.source_in_requested
            requested_out = clip.source_out_requested
            if requested_in >= source.duration:
                raise TimelineBuildError(
                    f"Clip {clip.clip_id}: source In {requested_in}s is at or beyond "
                    f"the source duration {source.duration}s"
                )
            if requested_out > source.duration:
                raise TimelineBuildError(
                    f"Clip {clip.clip_id}: source Out {requested_out}s exceeds "
                    f"the source duration {source.duration}s"
                )

            in_frame = seconds_to_frames(requested_in, source.frame_rate)
            out_frame = seconds_to_frames(requested_out, source.frame_rate)
            source_in = frames_to_seconds(in_frame, source.frame_rate)
            source_out = frames_to_seconds(out_frame, source.frame_rate)
            if source_out > source.duration:
                # An endpoint at EOF may round one frame beyond a container duration.
                out_frame = int(source.duration * source.frame_rate)
                source_out = frames_to_seconds(out_frame, source.frame_rate)
            if source_in >= source.duration or source_out > source.duration:
                raise TimelineBuildError(
                    f"Clip {clip.clip_id}: frame-aligned source range lies outside media duration"
                )
            if out_frame <= in_frame or source_out <= source_in:
                raise TimelineBuildError(
                    f"Clip {clip.clip_id}: source range collapses to zero frames at "
                    f"{source.frame_rate} fps"
                )

            duration = source_out - source_in
            timeline_clip = TimelineClip(
                clip_id=clip.clip_id,
                section_id=section.section_id,
                section_name=section.name,
                description=clip.description,
                source_in_requested=requested_in,
                source_out_requested=requested_out,
                source_in_frame=in_frame,
                source_out_frame=out_frame,
                source_in=source_in,
                source_out=source_out,
                duration=duration,
                timeline_start=cursor,
                timeline_end=cursor + duration,
            )
            timeline_clips.append(timeline_clip)
            section_clips.append(timeline_clip)
            cursor += duration

            if source_in != requested_in or source_out != requested_out:
                warnings.append(
                    f"Clip {clip.clip_id}: requested source range "
                    f"{requested_in}s–{requested_out}s was frame-aligned to "
                    f"{source_in}s–{source_out}s at {source.frame_rate} fps."
                )

        actual_duration = cursor - section_start
        section = TimelineSection(
            section_id=section.section_id,
            name=section.name,
            purpose=section.purpose,
            target_start=section.target_start,
            target_end=section.target_end,
            target_duration=section.target_duration,
            actual_start=section_start,
            actual_end=cursor,
            actual_duration=actual_duration,
            clips=tuple(section_clips),
        )
        sections.append(section)
        if section.target_duration is not None:
            difference = actual_duration - section.target_duration
            if difference > Fraction(1, 1) / fps:
                warnings.append(
                    f"Section {section.name}: source clips exceed the target slot by "
                    f"{difference}s; all source ranges are preserved and following "
                    "sections are delayed when necessary."
                )
            elif difference < -Fraction(1, 1) / fps:
                warnings.append(
                    f"Section {section.name}: source clips use {abs(difference)}s less "
                    "than the target slot; the unused interval remains a black/silent "
                    "placeholder before the next target-aligned section."
                )

    if not timeline_clips:
        raise TimelineBuildError("The plan produced an empty timeline")
    if source.appears_variable_frame_rate:
        warnings.append(
            "FFprobe's average and nominal frame rates differ; the source may be variable-frame-rate. "
            "Source timestamp alignment uses the probed average frame rate."
        )
    if fps != source.frame_rate:
        warnings.append(
            f"Timeline frame rate ({fps} fps) differs from source average frame rate "
            f"({source.frame_rate} fps); the interchange timeline preserves rational "
            "source durations and may require frame-rate conforming in Resolve."
        )

    timeline_duration = cursor
    if plan.sections[-1].target_end is not None and plan.sections[-1].target_end > cursor:
        trailing_gap = plan.sections[-1].target_end - cursor
        warnings.append(
            f"Added a {trailing_gap}s black/silent placeholder at the end to reach "
            "the final section target end."
        )
        timeline_duration = plan.sections[-1].target_end

    return BuiltTimeline(
        source=source,
        source_path=source.path,
        project_name=plan.project_name,
        sequence_name=plan.sequence_name,
        frame_rate=fps,
        sections=tuple(sections),
        clips=tuple(timeline_clips),
        duration=timeline_duration,
        outro_variant=plan.selected_outro_variant,
        warnings=tuple(warnings),
    )
