"""FCPXML 1.10 and optional OpenTimelineIO exporters."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path

from .models import BuiltTimeline
from .timecode_utils import fcpxml_time, rational_text


FCPXML_VERSION = "1.10"


def _fps_suffix(fps: Fraction) -> str:
    known = {
        Fraction(24000, 1001): "2398",
        Fraction(24, 1): "24",
        Fraction(25, 1): "25",
        Fraction(30000, 1001): "2997",
        Fraction(30, 1): "30",
        Fraction(50, 1): "50",
        Fraction(60000, 1001): "5994",
        Fraction(60, 1): "60",
    }
    return known.get(fps, str(round(float(fps))).replace(".", ""))


def _format_name(width: int, height: int, fps: Fraction) -> str:
    suffix = _fps_suffix(fps)
    if width == 3840 and height == 2160:
        return f"FFVideoFormatRateUHD2160p{suffix}"
    if width == 4096 and height == 2160:
        return f"FFVideoFormatRate4096x2160p{suffix}"
    if width == 1920 and height == 1080:
        return f"FFVideoFormat1080p{suffix}"
    if width == 1280 and height == 720:
        return f"FFVideoFormat720p{suffix}"
    return f"Custom_{width}x{height}_{suffix}fps"


def export_fcpxml(timeline: BuiltTimeline, output_path: str | Path) -> Path:
    """Write an editable FCPXML primary storyline with synchronized source A/V."""
    if not timeline.source.width or not timeline.source.height:
        raise ValueError("FCPXML video export requires source width and height metadata")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    root = ET.Element("fcpxml", {"version": FCPXML_VERSION})
    resources = ET.SubElement(root, "resources")
    frame_duration = Fraction(1, 1) / timeline.frame_rate
    format_id = "r1"
    ET.SubElement(
        resources,
        "format",
        {
            "id": format_id,
            "name": _format_name(
                timeline.source.width, timeline.source.height, timeline.frame_rate
            ),
            "frameDuration": fcpxml_time(frame_duration),
            "width": str(timeline.source.width),
            "height": str(timeline.source.height),
        },
    )

    source_format_id = format_id
    if timeline.source.frame_rate != timeline.frame_rate:
        source_format_id = "r2"
        ET.SubElement(
            resources,
            "format",
            {
                "id": source_format_id,
                "name": _format_name(
                    timeline.source.width, timeline.source.height, timeline.source.frame_rate
                ),
                "frameDuration": fcpxml_time(Fraction(1, 1) / timeline.source.frame_rate),
                "width": str(timeline.source.width),
                "height": str(timeline.source.height),
            },
        )

    asset_id = "r3" if source_format_id != format_id else "r2"
    asset_attributes = {
        "id": asset_id,
        "name": timeline.source_path.name,
        "start": "0s",
        "duration": fcpxml_time(timeline.source.duration),
        "hasVideo": "1",
        "hasAudio": "1" if timeline.source.audio_stream_count else "0",
        "format": source_format_id,
        "videoSources": "1",
    }
    if timeline.source.audio_stream_count:
        asset_attributes["audioSources"] = str(timeline.source.audio_stream_count)
        asset_attributes["audioChannels"] = str(timeline.source.audio_channels or 2)
        asset_attributes["audioRate"] = str(timeline.source.audio_sample_rate or 48000)
    asset = ET.SubElement(resources, "asset", asset_attributes)
    ET.SubElement(
        asset,
        "media-rep",
        {"kind": "original-media", "src": timeline.source_path.as_uri()},
    )

    library = ET.SubElement(root, "library")
    event = ET.SubElement(library, "event", {"name": timeline.project_name})
    project = ET.SubElement(event, "project", {"name": timeline.project_name})
    sequence_attributes = {
        "format": format_id,
        "duration": fcpxml_time(timeline.duration),
        "tcStart": "0s",
        "tcFormat": "NDF",
    }
    if timeline.source.audio_stream_count:
        channels = timeline.source.audio_channels or 2
        if channels == 1:
            sequence_attributes["audioLayout"] = "mono"
        elif channels == 2:
            sequence_attributes["audioLayout"] = "stereo"
        sequence_attributes["audioRate"] = "48k"
    sequence = ET.SubElement(project, "sequence", sequence_attributes)
    spine = ET.SubElement(sequence, "spine")

    first_clip_by_section = {
        section.section_id: section.clips[0].clip_id for section in timeline.sections if section.clips
    }
    spine_cursor = Fraction(0)
    section_names = {section.section_id: section.name for section in timeline.sections}
    for clip in timeline.clips:
        if clip.timeline_start < spine_cursor:
            raise ValueError(
                f"Clip {clip.clip_id} overlaps the preceding FCPXML storyline item"
            )
        if clip.timeline_start > spine_cursor:
            gap_duration = clip.timeline_start - spine_cursor
            ET.SubElement(
                spine,
                "gap",
                {
                    "name": f"Gap before {section_names[clip.section_id]}",
                    "offset": fcpxml_time(spine_cursor),
                    "start": "0s",
                    "duration": fcpxml_time(gap_duration),
                },
            )
            spine_cursor += gap_duration
        attributes = {
            "name": f"{clip.clip_id} - {clip.description}",
            "ref": asset_id,
            "format": format_id,
            "offset": fcpxml_time(clip.timeline_start),
            "start": fcpxml_time(clip.source_in),
            "duration": fcpxml_time(clip.duration),
            "tcFormat": "NDF",
        }
        if timeline.source.audio_stream_count:
            attributes["audioRole"] = "dialogue"
        asset_clip = ET.SubElement(spine, "asset-clip", attributes)
        if first_clip_by_section.get(clip.section_id) == clip.clip_id:
            ET.SubElement(
                asset_clip,
                "marker",
                {
                    "start": "0s",
                    "duration": fcpxml_time(frame_duration),
                    "value": f"Section: {clip.section_name}",
                },
            )
        spine_cursor = clip.timeline_end

    if timeline.duration > spine_cursor:
        ET.SubElement(
            spine,
            "gap",
            {
                "name": "End padding",
                "offset": fcpxml_time(spine_cursor),
                "start": "0s",
                "duration": fcpxml_time(timeline.duration - spine_cursor),
            },
        )

    ET.indent(root, space="  ")
    tree = ET.ElementTree(root)
    tree.write(output, encoding="utf-8", xml_declaration=True)
    return output


def export_otio(timeline: BuiltTimeline, output_path: str | Path) -> Path:
    """Write an OTIO timeline with matching video/audio tracks when OTIO is installed."""
    try:
        import opentimelineio as otio
    except ImportError as exc:
        raise RuntimeError(
            "OpenTimelineIO is optional. Install it with: "
            "python -m pip install '.[otio]'"
        ) from exc

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    fps = float(timeline.frame_rate)
    source_duration = float(timeline.source.duration)
    media_url = timeline.source_path.as_uri()

    otio_timeline = otio.schema.Timeline(name=timeline.sequence_name)
    otio_timeline.global_start_time = otio.opentime.RationalTime(0, fps)
    video_track = otio.schema.Track(
        name="V1", kind=otio.schema.TrackKind.Video
    )
    audio_track = otio.schema.Track(
        name="A1", kind=otio.schema.TrackKind.Audio
    ) if timeline.source.audio_stream_count else None

    track_cursors = {video_track: Fraction(0)}
    if audio_track is not None:
        track_cursors[audio_track] = Fraction(0)

    for clip in timeline.clips:
        for track in (video_track, audio_track):
            if track is None:
                continue
            track_cursor = track_cursors[track]
            if clip.timeline_start < track_cursor:
                raise ValueError(
                    f"Clip {clip.clip_id} overlaps the preceding OTIO track item"
                )
            if clip.timeline_start > track_cursor:
                gap_duration = clip.timeline_start - track_cursor
                track.append(
                    otio.schema.Gap(
                        name=f"Gap before {clip.section_name}",
                        source_range=otio.opentime.TimeRange(
                            otio.opentime.RationalTime(0, fps),
                            otio.opentime.RationalTime(float(gap_duration) * fps, fps),
                        ),
                    )
                )
                track_cursor += gap_duration
            media_ref = otio.schema.ExternalReference(
                target_url=media_url,
                available_range=otio.opentime.TimeRange(
                    otio.opentime.RationalTime(0, 1),
                    otio.opentime.RationalTime(source_duration, 1),
                ),
            )
            otio_clip = otio.schema.Clip(
                name=f"{clip.clip_id} - {clip.description}",
                media_reference=media_ref,
                source_range=otio.opentime.TimeRange(
                    otio.opentime.RationalTime(
                        clip.source_in_frame, float(timeline.source.frame_rate)
                    ),
                    otio.opentime.RationalTime(
                        clip.source_out_frame - clip.source_in_frame,
                        float(timeline.source.frame_rate),
                    ),
                ),
            )
            otio_clip.metadata["youtube_video_editing"] = {
                "clip_id": clip.clip_id,
                "section_id": clip.section_id,
                "source_in_exact": rational_text(clip.source_in),
                "source_out_exact": rational_text(clip.source_out),
                "timeline_start_exact": rational_text(clip.timeline_start),
                "timeline_duration_exact": rational_text(clip.duration),
                "media_streams": "audio" if track.kind == otio.schema.TrackKind.Audio else "video",
            }
            first_clip = next(
                section.clips[0].clip_id
                for section in timeline.sections
                if section.section_id == clip.section_id
            )
            if track.kind == otio.schema.TrackKind.Video and clip.clip_id == first_clip:
                otio_clip.markers.append(
                    otio.schema.Marker(
                        name=f"Section: {clip.section_name}",
                        marked_range=otio.opentime.TimeRange(
                            otio.opentime.RationalTime(0, 1),
                            otio.opentime.RationalTime(1 / fps, 1),
                        ),
                    )
                )
            track.append(otio_clip)
            track_cursors[track] = clip.timeline_end

    for track, track_cursor in track_cursors.items():
        if timeline.duration > track_cursor:
            gap_duration = timeline.duration - track_cursor
            track.append(
                otio.schema.Gap(
                    name="End padding",
                    source_range=otio.opentime.TimeRange(
                        otio.opentime.RationalTime(0, fps),
                        otio.opentime.RationalTime(float(gap_duration) * fps, fps),
                    ),
                )
            )
    otio_timeline.tracks.append(video_track)
    if audio_track is not None:
        otio_timeline.tracks.append(audio_track)
    otio.adapters.write_to_file(otio_timeline, str(output))
    return output
