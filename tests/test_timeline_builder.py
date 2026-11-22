from fractions import Fraction
from pathlib import Path

import pytest

from youtube_video_editing.models import VideoMetadata
from youtube_video_editing.timeline_builder import TimelineBuildError, build_timeline
from youtube_video_editing.timeline_parser import parse_plan_document
from youtube_video_editing.timeline_validator import validate_timeline


def metadata(path: Path, *, duration=120, fps=Fraction(30)):
    return VideoMetadata(
        path=path,
        duration=Fraction(duration),
        video_codec="h264",
        audio_codec="aac",
        width=1920,
        height=1080,
        frame_rate=fps,
        average_frame_rate=fps,
        nominal_frame_rate=fps,
        pixel_format="yuv420p",
        audio_sample_rate=48000,
        audio_channels=2,
        video_stream_count=1,
        audio_stream_count=1,
        appears_variable_frame_rate=False,
        format_name="mov,mp4",
    )


def test_builder_concatenates_clips_and_preserves_duplicates(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"test source placeholder")
    plan = parse_plan_document({
        "project_name": "Test",
        "sections": [
            {"id": "s1", "name": "Hook", "clips": [
                {"id": "a", "source_in": "00:00:01", "source_out": "00:00:03"}
            ]},
            {"id": "s2", "name": "Story", "clips": [
                {"id": "b", "source_in": "00:00:01", "source_out": "00:00:03"}
            ]},
        ],
    })
    timeline = build_timeline(plan, metadata(source))
    assert len(timeline.clips) == 2
    assert timeline.clips[0].source_in == timeline.clips[1].source_in
    assert timeline.clips[0].timeline_start == 0
    assert timeline.clips[1].timeline_start == 2
    assert timeline.duration == 4
    validate_timeline(timeline)


def test_builder_rejects_clip_past_source_end(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    plan = parse_plan_document({
        "sections": [{"id": "s", "name": "S", "clips": [
            {"id": "bad", "source_in": "119", "source_out": "121"}
        ]}]
    })
    with pytest.raises(TimelineBuildError, match="exceeds"):
        build_timeline(plan, metadata(source))


def test_builder_frame_aligns_source_timestamps(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    plan = parse_plan_document({
        "sections": [{"id": "s", "name": "S", "clips": [
            {"id": "a", "source_in": "0.01", "source_out": "1.01"}
        ]}]
    })
    timeline = build_timeline(plan, metadata(source))
    assert timeline.clips[0].source_in == Fraction(0)
    assert timeline.clips[0].source_out == 1
    assert timeline.warnings
