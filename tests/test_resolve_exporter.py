import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path

from youtube_video_editing.ask_studio_parser import load_ask_studio_text
from youtube_video_editing.models import VideoMetadata
from youtube_video_editing.report_generator import write_edit_report
from youtube_video_editing.resolve_exporter import export_fcpxml, export_otio
from youtube_video_editing.timecode_utils import parse_fcpxml_time
from youtube_video_editing.timeline_builder import build_timeline
from youtube_video_editing.timeline_parser import parse_plan_document
from youtube_video_editing.timeline_validator import validate_fcpxml, validate_timeline


ROOT = Path(__file__).resolve().parents[1]


def test_otio_export_contains_synchronized_video_and_audio_tracks(tmp_path):
    import opentimelineio as otio

    source = tmp_path / "otio source.mp4"
    source.write_bytes(b"source")
    fps = Fraction(30)
    metadata = VideoMetadata(
        path=source, duration=Fraction(30), video_codec="h264", audio_codec="aac",
        width=1280, height=720, frame_rate=fps, average_frame_rate=fps,
        nominal_frame_rate=fps, pixel_format="yuv420p", audio_sample_rate=48000,
        audio_channels=2, video_stream_count=1, audio_stream_count=1,
        appears_variable_frame_rate=False, format_name="mp4",
    )
    plan = parse_plan_document({
        "sequence_name": "OTIO Test",
        "sections": [{"id": "s", "name": "Section", "clips": [
            {"id": "a", "source_in": "2", "source_out": "5"},
            {"id": "b", "source_in": "10", "source_out": "12"},
        ]}],
    })
    timeline = build_timeline(plan, metadata)
    out = export_otio(timeline, tmp_path / "edit.otio")
    reopened = otio.adapters.read_from_file(str(out))
    assert len(reopened.tracks) == 2
    assert len(reopened.tracks[0]) == 2
    assert len(reopened.tracks[1]) == 2
    assert reopened.tracks[0][0].name.startswith("a -")
    assert reopened.tracks[1][1].metadata["youtube_video_editing"]["clip_id"] == "b"


def test_full_ask_studio_plan_exports_every_clip_and_target_aligned_section(tmp_path):
    source = tmp_path / "full source.mp4"
    source.write_bytes(b"synthetic media placeholder")
    fps = Fraction(30)
    metadata = VideoMetadata(
        path=source, duration=Fraction(71011, 10), video_codec="h264", audio_codec="aac",
        width=1920, height=1080, frame_rate=fps, average_frame_rate=fps,
        nominal_frame_rate=fps, pixel_format="yuv420p", audio_sample_rate=48000,
        audio_channels=2, video_stream_count=1, audio_stream_count=1,
        appears_variable_frame_rate=False, format_name="mp4",
    )
    plan = load_ask_studio_text(ROOT / "plans" / "ask_studio_daily_vlog.md")
    assert len(plan.sections) == 10
    assert [len(section.clips) for section in plan.sections] == [3, 1, 4, 1, 1, 3, 1, 3, 1, 2]
    expected_ids = [
        "1A", "1B", "1C", "2A", "3A", "3B", "3C", "3D", "4A", "5A",
        "6A", "6B", "6C", "7A", "8A", "8B", "8C", "9A", "10A", "10B",
    ]
    assert [clip.clip_id for section in plan.sections for clip in section.clips] == expected_ids

    timeline = build_timeline(plan, metadata)
    validate_timeline(timeline)
    assert len(timeline.clips) == 20
    assert [section.actual_start for section in timeline.sections] == [
        0, 21, 88, 270, 360, 452, 570, 645, 765, 825
    ]
    assert [section.actual_end for section in timeline.sections] == [
        21, 88, 204, 349, 452, 539, 605, 717, 821, 875
    ]
    assert timeline.duration == 900

    output = export_fcpxml(timeline, tmp_path / "complete.fcpxml")
    validate_fcpxml(output, timeline)
    root = ET.parse(output).getroot()
    sequence = root.find("./library/event/project/sequence")
    spine = sequence.find("./spine")
    xml_clips = spine.findall("./asset-clip")
    xml_gaps = spine.findall("./gap")
    assert len(xml_clips) == 20
    assert [node.attrib["name"].split(" - ", 1)[0] for node in xml_clips] == expected_ids
    assert len(root.findall(".//marker")) == 10
    assert len(xml_gaps) == 7
    assert all("format" not in gap.attrib for gap in xml_gaps)
    assert all(set(gap.attrib).issubset({"name", "offset", "start", "duration", "enabled"}) for gap in xml_gaps)
    assert [parse_fcpxml_time(gap.attrib["duration"]) for gap in xml_gaps] == [
        66, 11, 31, 40, 48, 4, 25
    ]
    assert [marker.attrib["value"] for marker in root.findall(".//marker")] == [
        f"Section: {section.name}" for section in timeline.sections
    ]

    report = write_edit_report(timeline, tmp_path / "complete_report.md").read_text()
    assert "Explicit timeline gaps" in report
    assert "00:15:00.000" in report
    for section in plan.sections:
        assert section.name in report


def test_otio_export_preserves_target_alignment_gaps(tmp_path):
    import opentimelineio as otio

    source = tmp_path / "gapped source.mp4"
    source.write_bytes(b"source")
    fps = Fraction(30)
    metadata = VideoMetadata(
        path=source, duration=Fraction(30), video_codec="h264", audio_codec="aac",
        width=1280, height=720, frame_rate=fps, average_frame_rate=fps,
        nominal_frame_rate=fps, pixel_format="yuv420p", audio_sample_rate=48000,
        audio_channels=2, video_stream_count=1, audio_stream_count=1,
        appears_variable_frame_rate=False, format_name="mp4",
    )
    plan = parse_plan_document({
        "sequence_name": "Gapped",
        "sections": [
            {"id": "s1", "name": "First", "target_start": "0", "target_end": "3",
             "clips": [{"id": "a", "source_in": "0", "source_out": "1"}]},
            {"id": "s2", "name": "Second", "target_start": "5", "target_end": "7",
             "clips": [{"id": "b", "source_in": "2", "source_out": "3"}]},
        ],
    })
    timeline = build_timeline(plan, metadata)
    out = export_otio(timeline, tmp_path / "gapped.otio")
    reopened = otio.adapters.read_from_file(str(out))
    for track in reopened.tracks:
        assert [type(child).__name__ for child in track] == ["Clip", "Gap", "Clip", "Gap"]
        assert track.duration().value == 210


def test_fcpxml_has_rational_sequential_clips_markers_and_linked_av(tmp_path):
    source = tmp_path / "original with spaces.mp4"
    source.write_bytes(b"test media")
    fps = Fraction(30000, 1001)
    metadata = VideoMetadata(
        path=source, duration=Fraction(100), video_codec="h264", audio_codec="aac",
        width=1920, height=1080, frame_rate=fps, average_frame_rate=fps,
        nominal_frame_rate=fps, pixel_format="yuv420p", audio_sample_rate=48000,
        audio_channels=2, video_stream_count=1, audio_stream_count=1,
        appears_variable_frame_rate=False, format_name="mov,mp4",
    )
    plan = parse_plan_document({
        "project_name": "XML Test",
        "sections": [
            {"id": "s1", "name": "Hook", "clips": [
                {"id": "a", "source_in": "1", "source_out": "3", "description": "First"}
            ]},
            {"id": "s2", "name": "Story", "clips": [
                {"id": "b", "source_in": "4", "source_out": "5", "description": "Second"}
            ]},
        ],
    })
    timeline = build_timeline(plan, metadata)
    out = export_fcpxml(timeline, tmp_path / "edit.fcpxml")
    root = ET.parse(out).getroot()
    assert root.attrib["version"] == "1.10"
    asset = root.find("./resources/asset")
    assert asset is not None and asset.attrib["hasAudio"] == "1"
    media = root.find("./resources/asset/media-rep")
    assert media.attrib["src"] == source.as_uri()
    assert "%20" in media.attrib["src"]
    sequence = root.find("./library/event/project/sequence")
    clips = sequence.findall("./spine/asset-clip")
    assert len(clips) == 2
    assert len(sequence.findall(".//marker")) == 2
    assert parse_fcpxml_time(clips[1].attrib["offset"]) == timeline.clips[1].timeline_start
    assert clips[0].attrib["audioRole"] == "dialogue"
    assert all(clip.attrib["format"] == sequence.attrib["format"] for clip in clips)
    validate_fcpxml(out, timeline)


def test_fcp_xml_source_reuse_is_not_deduplicated(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    fps = Fraction(30)
    metadata = VideoMetadata(
        path=source, duration=Fraction(10), video_codec="h264", audio_codec=None,
        width=1280, height=720, frame_rate=fps, average_frame_rate=fps,
        nominal_frame_rate=fps, pixel_format="yuv420p", audio_sample_rate=None,
        audio_channels=None, video_stream_count=1, audio_stream_count=0,
        appears_variable_frame_rate=False, format_name="mp4",
    )
    plan = parse_plan_document({
        "sections": [{"id": "s", "name": "Repeated", "clips": [
            {"id": "one", "source_in": "1", "source_out": "2"},
            {"id": "two", "source_in": "1", "source_out": "2"},
        ]}]
    })
    timeline = build_timeline(plan, metadata)
    out = export_fcpxml(timeline, tmp_path / "repeat.fcpxml")
    root = ET.parse(out).getroot()
    assert len(root.findall("./library/event/project/sequence/spine/asset-clip")) == 2
