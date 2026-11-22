"""Structural and semantic timeline validation."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path

from .models import BuiltTimeline
from .timecode_utils import parse_fcpxml_time


class TimelineValidationError(RuntimeError):
    pass


def validate_timeline(timeline: BuiltTimeline) -> None:
    if not timeline.source_path.is_file():
        raise TimelineValidationError(
            f"Source media no longer exists: {timeline.source_path}"
        )
    if not timeline.clips:
        raise TimelineValidationError("Timeline has no clips")
    cursor = Fraction(0)
    seen_ids: set[str] = set()
    for clip in timeline.clips:
        if clip.clip_id in seen_ids:
            raise TimelineValidationError(f"Duplicate clip identifier: {clip.clip_id}")
        seen_ids.add(clip.clip_id)
        if clip.source_in < 0 or clip.source_out > timeline.source.duration:
            raise TimelineValidationError(
                f"Clip {clip.clip_id} has source range outside media duration"
            )
        if clip.duration <= 0 or clip.duration != clip.source_out - clip.source_in:
            raise TimelineValidationError(
                f"Clip {clip.clip_id} has invalid source duration"
            )
        if clip.timeline_start < cursor or clip.timeline_end != clip.timeline_start + clip.duration:
            raise TimelineValidationError(
                f"Clip {clip.clip_id} overlaps another clip or has an invalid timeline duration"
            )
        cursor = clip.timeline_end
    if cursor > timeline.duration:
        raise TimelineValidationError(
            f"Last clip ends at {cursor}, beyond timeline duration {timeline.duration}"
        )
    previous_end = Fraction(0)
    for section in timeline.sections:
        expected_start = max(previous_end, section.target_start or Fraction(0))
        if section.actual_start != expected_start:
            raise TimelineValidationError(
                f"Section {section.name} starts at {section.actual_start}; "
                f"expected target-aligned start {expected_start}"
            )
        if not section.clips:
            raise TimelineValidationError(f"Section {section.name} has no clips")
        if section.clips[0].timeline_start != section.actual_start:
            raise TimelineValidationError(
                f"Section {section.name} actual start does not match its first clip"
            )
        if section.clips[-1].timeline_end != section.actual_end:
            raise TimelineValidationError(
                f"Section {section.name} actual end does not match its last clip"
            )
        previous_end = section.actual_end


def validate_fcpxml(path: str | Path, timeline: BuiltTimeline) -> None:
    xml_path = Path(path)
    try:
        root = ET.parse(xml_path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise TimelineValidationError(f"FCPXML is not well-formed: {exc}") from exc
    if root.tag != "fcpxml" or root.attrib.get("version") != "1.10":
        raise TimelineValidationError("Expected an FCPXML 1.10 document")
    resource = root.find("./resources/asset")
    media_rep = root.find("./resources/asset/media-rep")
    if resource is None or media_rep is None:
        raise TimelineValidationError("FCPXML is missing the source asset/media-rep")
    expected_uri = timeline.source_path.as_uri()
    if media_rep.attrib.get("src") != expected_uri:
        raise TimelineValidationError("FCPXML media-rep does not reference the source video")
    if not timeline.source_path.is_file():
        raise TimelineValidationError("Referenced source media path does not resolve")

    sequence = root.find("./library/event/project/sequence")
    if sequence is None:
        raise TimelineValidationError("FCPXML is missing the project sequence")
    if parse_fcpxml_time(sequence.attrib.get("duration", "0s")) != timeline.duration:
        raise TimelineValidationError("FCPXML sequence duration does not match the edit")
    elements = sequence.findall("./spine/asset-clip")
    if len(elements) != len(timeline.clips):
        raise TimelineValidationError(
            f"FCPXML has {len(elements)} clips; expected {len(timeline.clips)}"
        )
    spine = sequence.find("./spine")
    if spine is None:
        raise TimelineValidationError("FCPXML sequence is missing its primary storyline")
    cursor = Fraction(0)
    clip_index = 0
    for element in list(spine):
        offset = parse_fcpxml_time(element.attrib.get("offset", "0s"))
        if offset != cursor:
            raise TimelineValidationError(
                f"FCPXML storyline item {element.tag} starts at {offset}; expected {cursor}"
            )
        duration = parse_fcpxml_time(element.attrib.get("duration", "0s"))
        if duration <= 0:
            raise TimelineValidationError("FCPXML storyline contains a non-positive duration")
        if element.tag == "gap":
            allowed_gap_attributes = {"name", "offset", "start", "duration", "enabled"}
            unexpected = set(element.attrib) - allowed_gap_attributes
            if unexpected:
                raise TimelineValidationError(
                    f"FCPXML gap has unsupported attributes: {sorted(unexpected)}"
                )
            cursor += duration
            continue
        if element.tag != "asset-clip":
            raise TimelineValidationError(
                f"Unsupported primary-storyline element: {element.tag}"
            )
        if clip_index >= len(timeline.clips):
            raise TimelineValidationError("FCPXML contains more clips than the edit plan")
        clip = timeline.clips[clip_index]
        if element.attrib.get("ref") != resource.attrib.get("id"):
            raise TimelineValidationError(f"Clip {clip.clip_id} references an unknown asset")
        if element.attrib.get("format") != sequence.attrib.get("format"):
            raise TimelineValidationError(f"Clip {clip.clip_id} has an incorrect sequence format")
        if offset != clip.timeline_start:
            raise TimelineValidationError(f"Clip {clip.clip_id} has an incorrect timeline offset")
        if parse_fcpxml_time(element.attrib["start"]) != clip.source_in:
            raise TimelineValidationError(f"Clip {clip.clip_id} has an incorrect source In")
        if duration != clip.duration:
            raise TimelineValidationError(f"Clip {clip.clip_id} has an incorrect duration")
        if element.attrib.get("name", "").split(" - ", 1)[0] != clip.clip_id:
            raise TimelineValidationError(f"FCPXML clip order/identity mismatch at {clip.clip_id}")
        cursor += duration
        clip_index += 1
    if clip_index != len(timeline.clips):
        raise TimelineValidationError(
            f"FCPXML has {clip_index} clips; expected {len(timeline.clips)}"
        )
    if cursor != timeline.duration:
        raise TimelineValidationError(
            f"FCPXML storyline ends at {cursor}; expected sequence duration {timeline.duration}"
        )
